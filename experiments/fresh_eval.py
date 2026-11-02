#!/usr/bin/env python3
"""Frozen fresh-public-cohort runner. Dry run default; launch --execute only via start-job.sh.

Requires --plan pinned models, --cohort frozen JSON, --cohort-sha256 exact SHA,
--blocklist upstream right_view_blocked.json. No official evaluation/submission.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import local_eval as h
from qualify_images import container_command, validated_plan
from summarize_fresh import frozen_cohort


def eval_command(binary, address, rows, output):
    seeds = {row['eval_seed'] for row in rows}
    if len(seeds) != 1:
        raise ValueError('One explicit seed per cohort invocation')
    return [binary, 'eval', 'run', '--eval=.sim.molmo.benchmarks',
            '--eval.episode_paths=' + repr([row['episode_path'] for row in rows]),
            f'--eval.seed={next(iter(seeds))}', '--eval.trial_count=1', '--policy=.remote',
            f'--policy.address.host={address}', '--policy.address.port=8000', '--timing', f'--output_dir={output}']


@contextmanager
def policy(docker, row, directory, env, ready):
    name = 'physical-ai-fresh-' + uuid.uuid4().hex[:12]
    network = name + '-internal'
    state = {'container': name, 'network': network}
    try:
        h.bounded([*docker, 'network', 'create', '--internal', network], directory / 'network.log', env, 15, h.ROOT)
        h.bounded(container_command(docker, name, network, row['image']), directory / 'container.log', env, 30, h.ROOT)
        address = h.policy_address(docker, name, network, env)
        deadline = time.monotonic() + ready
        while not h.policy_ready(address, env):
            if time.monotonic() >= deadline:
                raise TimeoutError('Actual policy readiness timeout')
            time.sleep(2)
        yield address
    finally:
        try:
            h.bounded([*docker, 'logs', name], directory / 'policy.log', env, 10, h.ROOT)
        except Exception as exc:
            state['log_error_type'] = type(exc).__name__
        failed = False
        for key, command in (('container', [*docker, 'rm', '-f', name]), ('network', [*docker, 'network', 'rm', network])):
            try:
                response = subprocess.run(command, env=env, capture_output=True, timeout=20)
                state[key + '_cleanup_code'] = response.returncode
                failed |= response.returncode != 0
            except (OSError, subprocess.TimeoutExpired) as exc:
                state[key + '_cleanup_error'] = type(exc).__name__
                failed = True
        (directory / 'cleanup.json').write_text(json.dumps(state, indent=2) + '\n')
        if failed:
            raise RuntimeError('Owned container/network cleanup failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--cohort-sha256', required=True)
    parser.add_argument('--blocklist', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raw_plan = args.plan.read_bytes()
    config = json.loads(raw_plan)
    plan = validated_plan(config, h.ROOT / 'unused')
    cohort = frozen_cohort(args.cohort, args.cohort_sha256, json.loads(args.blocklist.read_text()))
    cohort_bytes = args.cohort.read_bytes()
    if hashlib.sha256(cohort_bytes).hexdigest() != args.cohort_sha256:
        raise ValueError('Cohort changed while freezing plan')
    timeout = config.get('eval_timeout_s', 3600)
    if type(timeout) is not int or not 60 <= timeout <= 7200:
        raise ValueError('Cohort timeout must be 60..7200 seconds')
    plan.update(cohort_sha256=args.cohort_sha256, model_plan_sha256=hashlib.sha256(raw_plan).hexdigest(),
                scope='fresh local public pick-only validation; not official competition',
                worst_case_seconds=2 * (plan['ready_timeout_s'] + 2 * timeout + 480) + 120)
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return
    if sys.platform != 'linux' or Path(__file__).resolve().parent != h.ROOT / 'experiments':
        raise ValueError('Execute only in isolated Linux task checkout')
    if time.time() + plan['worst_case_seconds'] >= h.DEADLINE - 120:
        raise ValueError('Conservative batch bound exceeds deadline reserve')
    for path in (args.plan, args.cohort, args.blocklist):
        h.owned(path)
    manifest = h.owned(cohort['manifest']['server_path'])
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != cohort['manifest']['sha256']:
        raise ValueError('Benchmark manifest SHA mismatch')
    env = dict(h.environment(), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    python, repo = plan['python'], Path(plan['repo'])
    binary = str(h.owned(config.get('positronic', str(repo / '.venv/bin/positronic'))))
    docker = ['bash', str(h.ROOT / 'docker/engine.sh')]
    def guard(log):
        h.bounded([python, str(h.ROOT / 'control/guard.py'), 'check'], log, env, 10, h.ROOT)
    with (h.ROOT / 'experiments/eval.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        guard(h.ROOT / 'experiments/fresh-guard.log')
        info = subprocess.run([*docker, 'info', '--format', '{{json .SecurityOptions}}'], env=env, capture_output=True, text=True, timeout=30, check=True)
        if 'rootless' not in info.stdout:
            raise ValueError('Dedicated engine must be rootless')
        batch = h.ROOT / 'experiments/results' / ('fresh-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        batch.mkdir(parents=True)
        (batch / 'cohort.json').write_bytes(cohort_bytes)
        (batch / 'model-plan.json').write_bytes(raw_plan)
        (batch / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        def interrupted(signum, frame):
            raise KeyboardInterrupt()
        previous = signal.signal(signal.SIGTERM, interrupted)
        try:
            for row in plan['policies']:
                directory = batch / row['name']
                directory.mkdir()
                result = {**row, 'status': 'failed', 'cohort_sha256': args.cohort_sha256}
                try:
                    guard(directory / 'guard.log')
                    with policy(docker, row, directory, env, plan['ready_timeout_s']) as address:
                        for seed in (0, 1):
                            output = directory / f'seed-{seed}'
                            output.mkdir()
                            guard(output / 'guard.log')
                            rows = [value for value in cohort['episodes'] if value['eval_seed'] == seed]
                            command = eval_command(binary, address, rows, output / 'episodes')
                            (output / 'command.json').write_text(json.dumps(command) + '\n')
                            h.bounded(h.namespace_command(command), output / 'eval.log', env, timeout, repo)
                            h.bounded(h.namespace_command([binary, 'eval', 'timing-report', f'--run_dir={output / "episodes"}']), output / 'timing.log', env, 60, repo)
                    h.bounded([python, str(h.ROOT / 'experiments/summarize_fresh.py'), '--run-dir', str(directory), '--cohort', str(batch / 'cohort.json'), '--cohort-sha256', args.cohort_sha256, '--blocklist', str(args.blocklist)], directory / 'metrics.json', env, 120, repo)
                    result.update(status='complete', metrics=json.loads((directory / 'metrics.json').read_text()))
                except BaseException as exc:
                    result['error_type'] = type(exc).__name__
                    raise
                finally:
                    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        finally:
            signal.signal(signal.SIGTERM, previous)
        print(json.dumps({'batch': str(batch)}))


if __name__ == '__main__':
    main()
