#!/usr/bin/env python3
"""Sequential offline image qualification; inspect a plan unless --execute is given.

Launch only through control/start-job.sh after evaluation releases eval.lock.
Example: python experiments/qualify_images.py --plan experiments/plan-horizon-validation.json
  --recordings /opt/hderc-internal/nick/physical-ai-competition/experiments/results/SMOKE/baseline/episodes
  [--execute]

Uses 2 sessions first, then 12 only after a passing 2-session report. Each client
process has an independent 180s bound and runs inside the dedicated daemon network
namespace. Resource samples refer only to the owned policy container and assigned
GPU card; card-wide memory includes any other users and is not process attribution.
"""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

import local_eval as h


def validated_plan(config, recordings):
    policies = config['policies']
    if len(policies) != 2 or policies[0]['name'] != 'baseline':
        raise ValueError('Provide exactly baseline then one finalist')
    names = [row['name'] for row in policies]
    if len(set(names)) != 2 or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', value) for value in names):
        raise ValueError('Unique lowercase policy slugs required')
    for row in policies:
        row['identity_type'] = h.image_identity(row['image'])
    ready = config.get('ready_timeout_s', 600)
    if not isinstance(ready, int) or not 10 <= ready <= 1200:
        raise ValueError('Readiness timeout must be 10..1200 seconds')
    repo = h.owned(config.get('repo', str(h.ROOT / 'positronic')))
    python = h.owned(config.get('python', str(repo / '.venv/bin/python')))
    return {'policies': policies, 'recordings': str(h.owned(recordings)), 'repo': str(repo), 'python': str(python),
            'ready_timeout_s': ready, 'stages': [2, 12], 'client_timeout_s': 180,
            'worst_case_seconds': len(policies) * (ready + 600) + 90,
            'gpu': h.GPU, 'eval_from_input_plan_ignored': True}


def container_command(docker, name, network, image):
    return [*docker, 'run', '-d', '--rm', '--pull=never', '--name', name,
            '--device', f'nvidia.com/gpu={h.GPU}', '--network', network,
            '--memory=28g', '--memory-swap=28g',
            '-e', 'XLA_PYTHON_CLIENT_PREALLOCATE=false', '-e', 'XLA_PYTHON_CLIENT_MEM_FRACTION=0.16',
            '--tmpfs', '/tmp:rw,nosuid,size=4g', image]


def client_command(python, address, image, recordings, sessions):
    return h.namespace_command([python, str(h.ROOT / 'experiments/qualify_sessions.py'),
                                '--url', f'ws://{address}:8000', '--image', image,
                                '--recordings', recordings, '--sessions', str(sessions), '--calls', '2'])


def checked_report(path, sessions):
    result = json.loads(path.read_text())
    if result.get('passed') is not True or result.get('sessions_per_wave') != sessions or result.get('distinct_client_connections_verified') is not True or not (result.get('distinct_session_ids_verified') is True or result.get('protocol_versions') == [1] and result.get('distinct_session_ids_verified') is None and result.get('server_session_ids_supported') is False):
        raise ValueError('Qualification stage did not pass with the requested coverage')
    return result



def run_stages(plan, address, image, directory, env, guard):
    stages = {}
    for sessions in plan['stages']:
        guard(directory / f'guard-{sessions}.log')
        path = directory / f'qualification-{sessions}.json'
        h.bounded(client_command(plan['python'], address, image, plan['recordings'], sessions), path,
                  env, plan['client_timeout_s'], Path(plan['repo']))
        stages[str(sessions)] = checked_report(path, sessions)
    return stages


def monitor_resources(docker, name, env, destination, stop):
    with destination.open('w') as stream:
        while not stop.is_set():
            sample = {'unix_time': time.time()}
            for key, command in (
                ('owned_container', [*docker, 'stats', '--no-stream', '--format', '{{json .}}', name]),
                ('gpu_card', ['/usr/bin/nvidia-smi', f'--id={h.GPU}', '--query-gpu=uuid,memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'])):
                try:
                    response = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
                    sample[key] = {'returncode': response.returncode, 'sample': response.stdout.strip()}
                except (OSError, subprocess.TimeoutExpired) as exc:
                    sample[key] = {'error_type': type(exc).__name__}
            stream.write(json.dumps(sample) + '\n')
            stream.flush()
            stop.wait(2)


def execute(plan):
    if sys.platform != 'linux' or Path(__file__).resolve().parent != h.ROOT / 'experiments':
        raise ValueError('Execute only from the isolated Linux task checkout')
    h.check_batch_deadline(plan['worst_case_seconds'])
    env = dict(h.environment(), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    docker = ['bash', str(h.ROOT / 'docker/engine.sh')]
    python, repo = plan['python'], Path(plan['repo'])
    for path in (Path(python), repo, Path(plan['recordings']), h.ROOT / 'experiments/qualify_sessions.py'):
        if not path.exists():
            raise ValueError(f'Missing prerequisite: {path}')
    with (h.ROOT / 'experiments/eval.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def guard(destination):
            h.bounded([python, str(h.ROOT / 'control/guard.py'), 'check'], destination, env, 10, h.ROOT)
        guard(h.ROOT / 'experiments/qualification-guard.log')
        info = subprocess.run([*docker, 'info', '--format', '{{json .SecurityOptions}}'], env=env,
                              capture_output=True, text=True, check=True, timeout=30)
        if 'rootless' not in info.stdout:
            raise ValueError('Dedicated engine must report rootless')
        batch = h.ROOT / 'experiments/results' / ('qualification-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        batch.mkdir(parents=True)
        (batch / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        results = []
        def interrupted(signum, frame):
            raise KeyboardInterrupt()
        previous = signal.signal(signal.SIGTERM, interrupted)
        try:
            for row in plan['policies']:
                directory = batch / row['name']
                directory.mkdir()
                guard(directory / 'guard.log')
                name = 'physical-ai-qualify-' + uuid.uuid4().hex[:12]
                network = name + '-internal'
                result = {**row, 'status': 'failed', 'container_name': name, 'network_name': network, 'stages': {}}
                stop = threading.Event()
                monitor = None
                try:
                    h.bounded([*docker, 'network', 'create', '--internal', network], directory / 'network.log', env, 15, h.ROOT)
                    h.bounded(container_command(docker, name, network, row['image']), directory / 'container-start.log', env, 30, h.ROOT)
                    monitor = threading.Thread(target=monitor_resources, args=(docker, name, env, directory / 'resources.jsonl', stop), daemon=True)
                    monitor.start()
                    address = h.policy_address(docker, name, network, env)
                    result['policy_address'] = address
                    until = time.monotonic() + plan['ready_timeout_s']
                    while not h.policy_ready(address, env):
                        if time.monotonic() >= until:
                            raise TimeoutError('Actual policy readiness timeout')
                        time.sleep(2)
                    result['stages'] = run_stages(plan, address, row['image'], directory, env, guard)
                    result['status'] = 'passed'
                except BaseException as exc:
                    result['error_type'] = type(exc).__name__
                    raise
                finally:
                    stop.set()
                    if monitor is not None:
                        monitor.join(timeout=12)
                    try:
                        h.bounded([*docker, 'logs', name], directory / 'policy.log', env, 10, h.ROOT)
                    except Exception as exc:
                        result['policy_log_error_type'] = type(exc).__name__
                    for key, command in (('container', [*docker, 'rm', '-f', name]), ('network', [*docker, 'network', 'rm', network])):
                        try:
                            response = subprocess.run(command, env=env, capture_output=True, timeout=20)
                            result[key + '_cleanup_returncode'] = response.returncode
                            if response.returncode:
                                result['status'] = 'cleanup_failed'
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            result[key + '_cleanup_error_type'] = type(exc).__name__
                            result['status'] = 'cleanup_failed'
                    (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
                    results.append(result)
                    (batch / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
                if result['status'] != 'passed':
                    raise RuntimeError('Qualification cleanup failed; stop before next image')
        finally:
            signal.signal(signal.SIGTERM, previous)
    return batch / 'results.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--recordings', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = validated_plan(json.loads(args.plan.read_text()), args.recordings)
    print(json.dumps(plan, indent=2), flush=True)
    if args.execute:
        print(json.dumps({'results': str(execute(plan))}))


if __name__ == '__main__':
    main()
