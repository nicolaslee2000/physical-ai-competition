#!/usr/bin/env python3
"""Bounded local-only policy comparison; a plan is printed unless --execute is given."""
import argparse
import datetime as dt
import fcntl
import json
import ipaddress
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
GPU = 'GPU-7c4310dd-d211-6c65-506c-2a74f693fe8b'
DEADLINE = dt.datetime(2026, 11, 3, 7, 30, tzinfo=dt.timezone.utc).timestamp()


def owned(path):
    path = Path(path)
    if not path.is_absolute() or not path.resolve().is_relative_to(ROOT):
        raise ValueError(f'Path must remain under {ROOT}: {path}')
    return path


def environment():
    # Do not propagate API keys, cloud credentials, SSH agent or user's Docker context.
    env = {'PATH': f'{ROOT}/bin:{ROOT}/positronic/.venv/bin:/usr/local/bin:/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'PHYSICAL_AI_CACHE_DIR': str(ROOT / 'cache/positronic'), 'XDG_CACHE_HOME': str(ROOT / 'cache'),
           'XDG_CONFIG_HOME': str(ROOT / 'config'), 'XDG_DATA_HOME': str(ROOT / 'data'),
           'TMPDIR': str(ROOT / 'tmp'), 'UV_CACHE_DIR': str(ROOT / 'cache/uv'),
           'CUDA_CACHE_PATH': str(ROOT / 'cache/cuda'), 'TORCH_HOME': str(ROOT / 'cache/torch'),
           'NUMBA_CACHE_DIR': str(ROOT / 'cache/numba'), 'JAX_COMPILATION_CACHE_DIR': str(ROOT / 'cache/jax'),
           'UV_PYTHON_INSTALL_DIR': str(ROOT / 'data/uv/python'), 'HF_HOME': str(ROOT / 'models/huggingface'),
           'MLSPACES_ASSETS_DIR': str(ROOT / 'models/molmospaces/assets'),
           'MLSPACES_CACHE_DIR': str(ROOT / 'cache/molmospaces'), 'CUDA_VISIBLE_DEVICES': GPU,
           'MUJOCO_GL': 'egl', 'EGL_PLATFORM': 'surfaceless', 'LIBGL_ALWAYS_SOFTWARE': '1'}
    return env


def bounded(cmd, log, env, timeout, cwd):
    with log.open('w') as stream:
        proc = subprocess.Popen(cmd, stdout=stream, stderr=subprocess.STDOUT, env=env, cwd=cwd, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
            if code:
                raise RuntimeError(f'Command failed ({code}); inspect {log}')
        finally:
            # Includes simulator grandchildren; prevent a timed-out process from lingering.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                time.sleep(1)
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            finally:
                proc.wait()



def image_identity(image):
    if re.fullmatch(r'sha256:[a-f0-9]{64}', image):
        return 'local-config-id'
    if re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}', image):
        return 'registry-manifest-digest'
    raise ValueError('Use a pinned registry manifest digest or exact local sha256 image ID')


def namespace_command(command):
    """Enter only this task engine's user/mount namespace, then its network namespace."""
    runtime = ROOT / 'runtime/dockerd-rootless'
    child_pid = (runtime / 'child_pid').read_text().strip()
    if not child_pid.isdecimal() or int(child_pid) <= 1:
        raise ValueError('Invalid dedicated rootless daemon child PID')
    return ['/usr/bin/nsenter', f'--user=/proc/{child_pid}/ns/user',
            f'--mount=/proc/{child_pid}/ns/mnt', '--preserve-credentials',
            '/usr/bin/nsenter', f'--net={runtime / "netns"}', *command]


def policy_address(docker, name, network, env):
    inspected = subprocess.run([*docker, 'inspect', '--format', '{{json .NetworkSettings.Networks}}', name],
                               env=env, capture_output=True, text=True, check=True, timeout=10)
    address = ipaddress.ip_address(json.loads(inspected.stdout)[network]['IPAddress'])
    if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError('Policy has no private IPv4 address on its own internal network')
    return str(address)


def policy_ready(address, env):
    """Probe the actual policy IP from the dedicated daemon namespace; require HTTP 200 + valid JSON."""
    command = namespace_command(['/usr/bin/curl', '--silent', '--show-error', '--noproxy', '*',
                                 '--max-time', '3', '--request', 'POST', '--write-out', '\n%{http_code}',
                                 f'http://{address}:8000/api/v1/keepalive'])
    try:
        response = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
        body, status = response.stdout.rsplit('\n', 1)
        payload = json.loads(body)
        if not isinstance(payload, dict) or 'alive_seconds' not in payload:
            return False
        alive = payload['alive_seconds']
        return response.returncode == 0 and status == '200' and (alive is None or type(alive) is int and alive >= 0)
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('plan.json'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    repo = owned(config.get('repo', str(ROOT / 'positronic')))
    binary = owned(config.get('positronic', str(repo / '.venv/bin/positronic')))
    python = owned(config.get('python', str(repo / '.venv/bin/python')))
    engine = ROOT / 'docker/engine.sh'
    docker = ['bash', str(engine)]
    eval_name = config.get('eval', 'molmo.franka_pick_mini')
    if eval_name not in ('molmo.franka_pick_mini_smoke', 'molmo.franka_pick_mini'):
        raise ValueError('Only the two public Molmo practice evals are allowed')
    candidates = config['policies']
    if not 2 <= len(candidates) <= 5 or candidates[0]['name'] != 'baseline':
        raise ValueError('Provide baseline first and 1–4 candidates')
    names = [row['name'] for row in candidates]
    if len(set(names)) != len(names) or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', name) for name in names):
        raise ValueError('Policy names must be unique lowercase slugs')
    for row in candidates:
        row['identity_type'] = image_identity(row['image'])
    timeout = config.get('eval_timeout_s', 3600)
    ready_timeout = config.get('ready_timeout_s', 600)
    if not 60 <= timeout <= 7200 or not 10 <= ready_timeout <= 1200:
        raise ValueError('Timeouts outside allowed bounds')
    plan = {'root': str(ROOT), 'gpu': GPU, 'policies': candidates,
            'eval': eval_name, 'holdout': [5, *range(7, 21)] if eval_name == 'molmo.franka_pick_mini' else [],
            'worst_case_seconds': len(candidates) * (timeout + ready_timeout + 240)}
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return
    if sys.platform != 'linux' or Path(__file__).resolve().parent != ROOT / 'experiments':
        raise ValueError('Execution requires the isolated Linux task checkout')
    if time.time() + plan['worst_case_seconds'] >= DEADLINE:
        raise ValueError('The bounded plan cannot finish before the experiment deadline')
    env = environment()
    for key in ('PHYSICAL_AI_CACHE_DIR', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'TMPDIR', 'UV_CACHE_DIR',
                'UV_PYTHON_INSTALL_DIR', 'HF_HOME', 'MLSPACES_ASSETS_DIR', 'MLSPACES_CACHE_DIR'):
        owned(env[key]).mkdir(parents=True, exist_ok=True)
    for path in (engine, binary, python, repo):
        if not path.exists():
            raise ValueError(f'Missing prerequisite: {path}')
    with (ROOT / 'experiments/eval.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from prepare_cache_patch import PATCHES
        for relative, (_, expected) in PATCHES.items():
            if expected not in (repo / relative).read_text():
                raise ValueError('Prepare task cache redirects and an editable install first')
        bounded([str(python), '-c', "from pathlib import Path; from positronic.simulator.molmo_spaces.launcher import _MOLMO_SRC; from positronic.simulator.env_server.launcher import _PORT_LOCKS; root=Path('/opt/hderc-internal/nick/physical-ai-competition'); assert _MOLMO_SRC.resolve().is_relative_to(root) and _PORT_LOCKS.resolve().is_relative_to(root)"], ROOT / 'experiments/cache-check.log', env, 15, repo)
        bounded([str(python), str(ROOT / 'control/guard.py'), 'check'], ROOT / 'experiments/guard.log', env, 10, ROOT)
        # The engine wrapper is the only Docker entry point. Require rootless explicitly.
        check = subprocess.run([*docker, 'info', '--format', '{{json .SecurityOptions}}'], env=env,
                               capture_output=True, text=True, check=True, timeout=30)
        if 'rootless' not in check.stdout:
            raise ValueError('Dedicated Docker engine is not rootless')
        batch = ROOT / 'experiments/results' / (dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        batch.mkdir(parents=True)
        revision = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], env=env, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        plan['positronic_revision'] = revision
        (batch / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        results = []
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
        for row in candidates:
            run = batch / row['name']
            run.mkdir()
            bounded([str(python), str(ROOT / 'control/guard.py'), 'check'], run / 'guard.log', env, 10, ROOT)
            name = 'physical-ai-eval-' + uuid.uuid4().hex[:12]
            network = name + '-internal'
            status = {'name': row['name'], 'image': row['image'], 'status': 'failed',
                      'container_name': name, 'network_name': network, 'identity_type': row['identity_type']}
            try:
                bounded([*docker, 'network', 'create', '--internal', network], run / 'network.log', env, 15, ROOT)
                cmd = [*docker, 'run', '-d', '--rm', '--pull=never', '--name', name,
                       '--device', f'nvidia.com/gpu={GPU}', '--network', network,
                       '--memory=28g', '--memory-swap=28g',
                       '-e', 'XLA_PYTHON_CLIENT_PREALLOCATE=false',
                       '-e', 'XLA_PYTHON_CLIENT_MEM_FRACTION=0.16',
                       '--tmpfs', '/tmp:rw,nosuid,size=4g', row['image']]
                bounded(cmd, run / 'container-start.log', env, 30, ROOT)
                address = policy_address(docker, name, network, env)
                status['policy_address'] = address
                status['container_name'] = name
                until = time.monotonic() + ready_timeout
                while not policy_ready(address, env):
                    if time.monotonic() >= until:
                        raise TimeoutError('Actual policy container readiness timeout')
                    time.sleep(2)
                bounded(namespace_command([str(binary), 'eval', 'run', f'--eval={eval_name}', '--policy=.remote',
                         f'--policy.address.host={address}', '--policy.address.port=8000', '--timing',
                         f'--output_dir={run / "episodes"}']), run / 'eval.log', env, timeout, repo)
                bounded(namespace_command([str(binary), 'eval', 'timing-report', f'--run_dir={run / "episodes"}']), run / 'timing.log', env, 60, repo)
                bounded([str(python), str(ROOT / 'experiments/summarize_recordings.py'), '--repo', str(repo), '--run-dir', str(run), '--eval', eval_name],
                        run / 'validation.log', env, 60, repo)
                status.update(status='complete', metrics=json.loads((run / 'metrics.json').read_text()))
            except (Exception, KeyboardInterrupt) as error:
                status['error_type'] = type(error).__name__
                raise
            finally:
                try:
                    bounded([*docker, 'logs', name], run / 'policy.log', env, 10, ROOT)
                finally:
                    cleanup = subprocess.run([*docker, 'rm', '-f', name], env=env, capture_output=True, timeout=20)
                    network_cleanup = subprocess.run([*docker, 'network', 'rm', network], env=env, capture_output=True, timeout=15)
                    status['network_cleanup_returncode'] = network_cleanup.returncode
                    status['container_cleanup_returncode'] = cleanup.returncode
                    if cleanup.returncode or network_cleanup.returncode:
                        status['status'] = 'cleanup_failed'
                    (run / 'result.json').write_text(json.dumps(status, indent=2) + '\n')
                    results.append(status)
                    (batch / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
            if status['status'] == 'cleanup_failed':
                raise RuntimeError(f'Container cleanup failed; inspect {run}')
        print(f'Results: {batch / "results.json"}')


if __name__ == '__main__':
    main()
