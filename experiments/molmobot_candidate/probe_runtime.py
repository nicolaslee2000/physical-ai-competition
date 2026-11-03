"""Offline runtime feasibility only; no simulator score, socket or task execution."""
import hashlib
import json
from pathlib import Path
import resource
import time

from .serve import ROOT, PINS, offline_environment, verify_artifacts, build_model

STAGE = ROOT / 'packaging/molmobot'


def main():
    offline_environment()
    import numpy as np
    import torch
    output = STAGE / 'probe/result.json'
    result = {'scope': 'offline one-process feasibility, not task success or concurrency qualification',
              'status': 'started', 'calls': [], 'history_values': 'repeated development frame, shape test only'}
    model = None
    started = time.monotonic()
    def memory():
        peak = Path('/sys/fs/cgroup/memory.peak')
        free, total = torch.cuda.mem_get_info()
        return {'cuda_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                'cuda_peak_reserved_bytes': torch.cuda.max_memory_reserved(),
                'cuda_current_allocated_bytes': torch.cuda.memory_allocated(),
                'cuda_current_reserved_bytes': torch.cuda.memory_reserved(),
                'card_used_at_sample_bytes': total-free,
                'cgroup_host_peak_bytes': int(peak.read_text()) if peak.exists() else None,
                'process_host_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
    try:
        pins = json.loads(PINS.read_text())
        result['artifacts'] = verify_artifacts(ROOT / 'artifacts/molmobot', pins)
        assert torch.cuda.is_available() and 'sm_120' in torch.cuda.get_arch_list()
        total = torch.cuda.get_device_properties(0).total_memory
        # Allocator-only ceiling: this does not emulate MIG compute or cap driver memory.
        torch.cuda.set_per_process_memory_fraction(21_000_000_000 / total)
        torch.cuda.reset_peak_memory_stats()
        result['gpu'] = {'name': torch.cuda.get_device_name(), 'total_bytes': total,
                         'allocator_ceiling_bytes': 21_000_000_000,
                         'torch': torch.__version__, 'cuda_build': torch.version.cuda}
        result['status'] = 'loading'
        output.write_text(json.dumps(result, indent=2) + '\n')
        load_start = time.monotonic()
        model = build_model(ROOT / 'artifacts/molmobot', 'client_stack')
        torch.cuda.synchronize()
        result['load_s'] = time.monotonic()-load_start
        result['after_load'] = memory()
        obs = np.load(STAGE / 'probe/observation.npz', allow_pickle=False)
        state = np.concatenate([obs['joints'], [0.824033 * float(np.clip(obs['grip'].item(),0,1))]]).astype(np.float32)
        prompt = str(obs['task'].item())
        exo, wrist = obs['exterior'], obs['wrist']
        tasks = [prompt, ' '.join(['pick the small object and place it in the bowl']*10)]
        for case, (frames, task) in enumerate([(1,tasks[0]),(2,tasks[0]),(2,tasks[1]),(1,tasks[0])]):
            images = [exo,wrist] if frames == 1 else [exo,exo,wrist,wrist]
            for repeat in range(3):
                torch.manual_seed(20261103+case*10+repeat)
                np.random.seed(20261103+case*10+repeat)
                torch.cuda.synchronize()
                tick = time.monotonic()
                action = np.asarray(model.model.get_action_chunk(images=images,task_description=task,state=state))
                torch.cuda.synchronize()
                elapsed = time.monotonic()-tick
                assert action.shape == (16,8) and np.isfinite(action).all()
                row = {'case':case,'repeat':repeat,'frames_per_camera':frames,'latency_ms':elapsed*1000,
                       'prompt_sha256':hashlib.sha256(task.encode()).hexdigest(),
                       'action_sha256':hashlib.sha256(action.tobytes()).hexdigest(), 'memory':memory()}
                result['calls'].append(row)
                output.write_text(json.dumps(result, indent=2) + '\n')
        latencies = [row['latency_ms'] for row in result['calls']]
        result['latency_ms'] = {'first':latencies[0],'p50':float(np.percentile(latencies,50)),
                                'p95':float(np.percentile(latencies,95)),'max':max(latencies)}
        result['peak'] = memory()
        result['status'] = 'single_process_passed'
        result['limitations'] = ['No native RPC/session load tested', 'No task success measured',
                                'Allocator peaks are instrumented; driver/card values are boundary samples, not a total-process peak',
                                'Full-card compute; no quarter-slice throughput guarantee']
    except BaseException as exc:
        result.update(status='failed', error_type=type(exc).__name__, error=str(exc)[:1000])
        raise
    finally:
        result['elapsed_s'] = time.monotonic()-started
        output.write_text(json.dumps(result, indent=2) + '\n')
        if model is not None:
            model.close()
        print(json.dumps({'status':result['status'],'calls':len(result['calls']),'result':str(output)}),flush=True)


if __name__ == '__main__':
    main()
