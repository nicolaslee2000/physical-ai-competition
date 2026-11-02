#!/usr/bin/env python3
"""Offline DROID joint-position session qualification; JSON stdout, no credentials.

Run only against an explicitly prepared isolated policy endpoint, under start-job.sh
and (for internal Docker addresses) the same daemon namespace as local_eval.py.
Example: python qualify_sessions.py --url ws://172.25.0.2:8000 --image IMAGE_DIGEST
  --recordings ROOT/experiments/results/SMOKE/baseline/episodes --sessions 12

Reads ONLY recorded public development indices 0..4. Uses the actual handshake's
v1/v2/v3 declared client stack and Executor Runtime, not guessed wire observations.
V1 qualifies separate client connections; server session IDs and close acknowledgments
are unsupported and explicitly null. V2/V3 require unique server IDs and close ACKs.
Two synchronized waves open new connections, perform >=2 inference calls each,
validate native DROID commands, and check protocol-appropriate connection close.
Reopening creates a fresh client stack/runtime (reset); it does not prove model
state isolation. Queue-inclusive client round trips are timed; no robot is driven.
"""
import argparse
import json
import math
import os
import uuid
import multiprocessing as mp
from pathlib import Path
import queue
import signal
import time
from urllib.parse import urlparse


class CheckFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_identity(url, image):
    parsed = urlparse(url)
    if parsed.scheme != 'ws' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Use an explicit credential-free ws://HOST:PORT endpoint')
    import re
    if not re.fullmatch(r'(?:[A-Za-z0-9./:_-]+@)?sha256:[a-f0-9]{64}', image):
        raise ValueError('Use an immutable local config ID or registry manifest digest')
    return parsed.hostname, parsed.port or 8000


def validate_commands(commands, keys, joint_type, np):
    if keys.ROBOT_COMMAND not in commands or keys.TARGET_GRIP not in commands:
        raise ValueError('Expected DROID arm and gripper command channels')
    arm = commands[keys.ROBOT_COMMAND]
    if not isinstance(arm, joint_type):
        raise ValueError('DROID arm command must be native JointPosition')
    joints = np.asarray(arm.positions)
    grip = np.asarray(commands[keys.TARGET_GRIP])
    if joints.shape != (7,) or not np.isfinite(joints).all():
        raise ValueError('Expected seven finite joint targets')
    if grip.size != 1 or not np.isfinite(grip).all() or not 0 <= float(grip.reshape(-1)[0]) <= 1:
        raise ValueError('Expected finite gripper target in [0,1]')


def load_development(root):
    import numpy as np
    from positronic import keys
    from positronic.dataset.local_dataset import LocalDataset
    from positronic.dataset import Time
    dataset = LocalDataset(Path(root))
    chosen = next((episode for episode in dataset if episode.static.get('molmo.episode_index') in range(5)), None)
    if chosen is None:
        raise ValueError('No public development recording (indices 0..4)')
    required = (keys.JOINTS, keys.GRIP, keys.EXTERIOR_IMAGE, keys.WRIST_IMAGE)
    if keys.EXTERIOR_IMAGE_2 in chosen.signals:
        required += (keys.EXTERIOR_IMAGE_2,)
    signals = {name: chosen.signals[name] for name in required}
    common = set.intersection(*(set(value.timelines) for value in signals.values()))
    if not common:
        raise ValueError('No shared observation timeline')
    timeline = sorted(common)[0]
    instant = max(value.bounds((timeline,)).start[timeline] for value in signals.values())
    obs = {name: value.time[Time(**{timeline: instant})][0] for name, value in signals.items()}
    obs[keys.TASK] = chosen.static[keys.TASK]
    if not isinstance(obs[keys.TASK], str) or not obs[keys.TASK]:
        raise ValueError('Missing recorded task instruction')
    if np.asarray(obs[keys.JOINTS]).shape != (7,) or not np.isfinite(obs[keys.JOINTS]).all():
        raise ValueError('Invalid recorded joints')
    for name in (key for key in required if key.startswith(keys.IMAGE_PREFIX)):
        value = np.asarray(obs[name])
        if value.ndim != 3 or value.shape[-1] != 3 or value.dtype != np.uint8:
            raise ValueError('Recorded RGB camera frame must be uint8 HxWx3')
    return obs, int(chosen.static['molmo.episode_index'])


def worker(index, host, port, recordings, calls_requested, barrier, output):
    result = {'worker': index, 'waves': [], 'passed': False, 'stage': 'dependencies'}
    connection_objects = []
    session = runtime = run = None
    def expired(signum, frame):
        raise TimeoutError('15-second session wave deadline')
    try:
        import numpy as np
        from positronic import keys
        from positronic.offboard.client import InferenceClient
        from positronic_wire import registry, wire
        from positronic.policy.remote import declared_stack, round_trip, RemotePolicy
        from positronic.policy.base import Step
        from positronic.policy.executor import Executor
        from positronic.policy import keys as policy_keys
        from positronic.drivers.roboarm.command import JointPosition
        from positronic_model_server.protocol import ProtocolVersion
        from positronic_model_server.serialization import DEFAULT_JPEG_QUALITY
        result['stage'] = 'observation'
        observation, episode = load_development(recordings)
        result['development_episode_index'] = episode
        client = InferenceClient(registry.client_wire('websocket'), wire.HostPortAddress(host, port, wire.SESSION_PATH, ''),
                                 open_timeout=3, connect_deadline=10, infer_timeout=15)
        signal.signal(signal.SIGALRM, expired)
        for wave in range(2):
            signal.alarm(15)
            result['stage'] = 'open'
            session = client.new_session()
            result['stage'] = 'handshake'
            version = int(session.protocol_version.value)
            sid = session.session_id
            connection = session._conn  # Actual connection created by InferenceClient.new_session.
            if any(connection is previous for previous in connection_objects):
                raise CheckFailure('reused_client_connection')
            connection_objects.append(connection)
            wave_result = {'wave': wave, 'protocol_version': version, 'session_id': sid,
                           'connection_audit_id': uuid.uuid4().hex, 'connection_object_id': f'{os.getpid()}:{id(connection)}',
                           'synchronized_open_connection': False, 'connection_closed': False,
                           'end_session_acknowledged': None, 'infer_ms': [], 'validated_command_steps': 0}
            result['waves'].append(wave_result)
            if version not in (1, 2, 3):
                raise CheckFailure('unsupported_protocol')
            if version != 1 and (not isinstance(sid, str) or not sid):
                raise CheckFailure('missing_server_session_id')
            result['stage'] = 'declared_stack'
            stack = declared_stack(session.metadata, session.protocol_version)
            now, durations, valid_steps = [0], wave_result['infer_ms'], 0
            def infer(obs):
                started = time.monotonic()
                answer = round_trip(session, obs, session.protocol_version is not ProtocolVersion.V3 and bool(session.metadata.get(policy_keys.COMPRESS_IMAGES)), DEFAULT_JPEG_QUALITY)
                elapsed = (time.monotonic() - started) * 1000
                if session._conn is not connection:
                    raise CheckFailure('client_connection_changed')
                if version != 1 and session.session_id != sid:
                    raise CheckFailure('server_session_identity_changed')
                if elapsed > 15000:
                    raise CheckFailure('inference_exceeded_15s')
                durations.append(elapsed)
                return answer
            runtime = Executor(lambda: now[0], simulated=True, charge_inference_time=False)
            run = runtime.start(stack, infer)
            result['stage'] = 'synchronize'
            barrier.wait(timeout=10)
            wave_result['synchronized_open_connection'] = True
            result['stage'] = 'inference'
            while len(durations) < calls_requested or valid_steps < 2:
                step = run.send(observation)
                if not isinstance(step, Step):
                    raise CheckFailure('declared_stack_output_not_step')
                result['stage'] = 'command_validation'
                RemotePolicy._require_robot_commands(step)
                if step.commands:
                    try:
                        validate_commands(step.commands, keys, JointPosition, np)
                    except (ValueError, TypeError) as error:
                        raise CheckFailure('invalid_droid_commands') from None
                    valid_steps += 1
                    wave_result['validated_command_steps'] = valid_steps
                result['stage'] = 'inference'
                if runtime.has_pending:
                    runtime.wait(timeout_sec=1)
                else:
                    now[0] = max(now[0] + 1_000_000, step.resume_at_ns)
            result['stage'] = 'runtime_close'
            runtime.close()
            run.close()
            runtime = run = None
            result['stage'] = 'session_close'
            session.close()  # V1 closes transport; V2/V3 verifies exact END_SESSION acknowledgment.
            wave_result['connection_closed'] = True
            wave_result['end_session_acknowledged'] = True if version != 1 else None
            session = None
            signal.alarm(0)
            wave_result['stage'] = 'complete'
        result['passed'] = True
        result['stage'] = 'complete'
    except BaseException as exc:
        result['error_phase'] = result['stage']
        result['validation_error_code'] = exc.code if isinstance(exc, CheckFailure) else 'operation_failed'
        result['error_type'] = type(exc).__name__  # No server errors, metadata, observations or keys printed.
        barrier.abort()
    finally:
        signal.alarm(0)
        output.put(result)
        # Parent enforces process teardown even when transport/runtime cleanup stalls.
        if runtime is not None:
            runtime.close()
        if run is not None:
            run.close()
        if session is not None:
            session.close()


def aggregate(rows, expected):
    waves = [wave for row in rows for wave in row['waves']]
    identities = [wave.get('session_id') for wave in waves]
    protocols = {wave.get('protocol_version') for wave in waves}
    audit_ids = [wave.get('connection_audit_id') for wave in waves]
    object_ids = [wave.get('connection_object_id') for wave in waves]
    values = sorted(value for row in rows for wave in row['waves'] for value in wave['infer_ms'])
    def quantile(q):
        if not values:
            return None
        position = (len(values) - 1) * q
        lo, hi = math.floor(position), math.ceil(position)
        return values[lo] + (values[hi] - values[lo]) * (position - lo)
    connections_unique = all(audit_ids) and all(object_ids) and len(set(audit_ids)) == len(set(object_ids)) == expected * 2
    server_unique = all(isinstance(value, str) and value for value in identities) and len(set(identities)) == expected * 2
    modern = protocols.issubset({2, 3}) and bool(protocols)
    legacy = protocols == {1}
    protocol_valid = (modern and server_unique) or legacy
    lifecycle_valid = all(len(row['waves']) == 2 and all(
        wave.get('connection_closed') is True and wave.get('synchronized_open_connection') is True and
        (wave.get('protocol_version') == 1 and wave.get('end_session_acknowledged') is None or
         wave.get('protocol_version') in (2, 3) and wave.get('end_session_acknowledged') is True) and
        wave.get('validated_command_steps', 0) >= 2 and len(wave['infer_ms']) >= 2 for wave in row['waves']) for row in rows)
    finite = all(math.isfinite(value) and 0 <= value <= 15000 for value in values)
    passed = len(rows) == expected and connections_unique and protocol_valid and lifecycle_valid and all(row['passed'] for row in rows) and bool(values) and finite
    return {'passed': passed, 'distinct_session_ids_verified': bool(server_unique) if modern else None,
            'server_session_ids_supported': modern if modern or legacy else None,
            'distinct_client_connections_verified': bool(connections_unique), 'protocol_versions': sorted(value for value in protocols if value is not None), 'sessions_per_wave': expected,
            'waves': 2, 'calls': len(values), 'p50_ms': quantile(.5), 'p95_ms': quantile(.95), 'max_ms': max(values) if values else None,
            'workers': rows, 'scope': 'observed client round trips incl server queue; synchronized open sessions, scheduling overlap not guaranteed',
            'limitation': 'fresh runtime/stack and separate client connection objects check close/reopen; V1 exposes no server IDs or END_SESSION acknowledgment; V2/V3 require both; cannot prove absence of model state leaks or official hardware compliance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--recordings', type=Path, required=True)
    parser.add_argument('--sessions', type=int, default=2)
    parser.add_argument('--calls', type=int, default=2)
    args = parser.parse_args()
    host, port = validate_identity(args.url, args.image)
    root = Path('/opt/hderc-internal/nick/physical-ai-competition')
    if not args.recordings.resolve().is_relative_to(root):
        parser.error('Recordings must be inside the isolated task root')
    if not 1 <= args.sessions <= 12 or not 2 <= args.calls <= 5:
        parser.error('Require 1..12 sessions and 2..5 inference calls per session wave')
    context = mp.get_context('spawn')
    barrier, output = context.Barrier(args.sessions), context.Queue()
    processes = [context.Process(target=worker, args=(i, host, port, str(args.recordings), args.calls, barrier, output)) for i in range(args.sessions)]
    rows = []
    try:
        for process in processes:
            process.start()
        deadline = time.monotonic() + 90  # Includes read/import plus two 15s waves.
        while len(rows) < args.sessions:
            try:
                rows.append(output.get(timeout=max(.01, deadline - time.monotonic())))
            except queue.Empty:
                break
        for process in processes:
            process.join(timeout=max(0, deadline - time.monotonic()))
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
    result = aggregate(rows, args.sessions)
    result['worker_exitcodes'] = [process.exitcode for process in processes]
    result['passed'] = result['passed'] and all(process.exitcode == 0 for process in processes)
    result.update(image=args.image, recordings=str(args.recordings), endpoint_host=host, endpoint_port=port)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
