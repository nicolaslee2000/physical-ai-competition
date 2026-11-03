"""Executable native serving entrypoint; requires pre-staged, pinned local artifacts.

`python -m molmobot_candidate.serve --verify-only` hashes inputs without importing
Torch, loading a model, binding a socket, or downloading anything.
"""
import argparse
import copy
import math
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
PINS = Path(__file__).with_name('packaging-pins.json')


def owned(path, root=ROOT):
    path = Path(path)
    if not path.is_absolute() or not path.resolve().is_relative_to(root):
        raise ValueError('Artifacts/runtime paths must stay inside the task root')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Symlink in artifact/runtime path')
        if parent == root:
            break
    return path


def verify_artifacts(directory, pins, root=ROOT):
    directory = owned(directory, root)
    for row in pins['artifacts']:
        relative = row['path']
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Invalid pinned artifact path')
        path = owned(directory / relative, root)
        if path.stat().st_size != row['size']:
            raise ValueError('Pinned artifact size mismatch')
        sha256 = hashlib.sha256()
        git_sha = hashlib.sha1(f'blob {row["size"]}\0'.encode())
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                sha256.update(chunk);git_sha.update(chunk)
        if 'sha256' in row and sha256.hexdigest() != row['sha256'] or 'git_blob_sha1' in row and git_sha.hexdigest() != row['git_blob_sha1']:
            raise ValueError('Pinned artifact hash mismatch')
    expected = {row['path'] for row in pins['artifacts']}
    actual = set()
    for path in directory.rglob('*'):
        owned(path, root)
        if path.is_file():
            actual.add(str(path.relative_to(directory)))
    if actual != expected:
        raise ValueError('Artifact directory contains unpinned extra files')
    return {'verified_artifacts': len(pins['artifacts']), 'weights_revision': pins['weights_revision'],
            'tokenizer_revision': pins['tokenizer']['revision']}


def offline_environment():
    values = {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
              'HF_HUB_DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1',
              'TMPDIR': str(ROOT / 'tmp'), 'HF_HOME': str(ROOT / 'cache/huggingface'),
              'XDG_CACHE_HOME': str(ROOT / 'cache'), 'TORCH_HOME': str(ROOT / 'cache/torch'),
              'TORCH_EXTENSIONS_DIR': str(ROOT / 'cache/torch-extensions'), 'TRITON_CACHE_DIR': str(ROOT / 'cache/triton'),
              'CUDA_CACHE_PATH': str(ROOT / 'cache/cuda'), 'TOKENIZERS_PARALLELISM': 'false',
              'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
    os.environ.update(values)
    # Offline anonymous artifact loading must not consult inherited Hub credential variables.
    for key in ('HF_ACCESS_TOKEN', 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        os.environ.pop(key, None)
    for key in ('TMPDIR', 'HF_HOME', 'XDG_CACHE_HOME', 'TORCH_HOME', 'TORCH_EXTENSIONS_DIR', 'TRITON_CACHE_DIR', 'CUDA_CACHE_PATH'):
        owned(values[key]).mkdir(parents=True, exist_ok=True)



def local_tokenizer_config(config, tokenizer_dir, cache_dir):
    result = copy.deepcopy(config)
    tokenizer = result['model']['llm']['tokenizer']
    if tokenizer['identifier'] != 'Qwen/Qwen3-4B-Instruct-2507':
        raise ValueError('Unexpected source tokenizer configuration')
    tokenizer['identifier'] = str(tokenizer_dir)
    tokenizer['tokenizer_dir'] = str(cache_dir)
    return result


def build_model(artifacts, history_mode):
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required; CPU fallback is not qualified')
    if tuple(int(value) for value in torch.__version__.split('.')[:2]) < (2, 8) or not torch.version.cuda or tuple(map(int, torch.version.cuda.split('.')[:2])) < (12, 8):
        raise RuntimeError('Require reviewed PyTorch>=2.8/CUDA>=12.8 runtime')
    import yaml
    from olmo.models.molmobot.inference_wrapper import SynthManipMolmoInferenceWrapper
    from .adapter import MolmoBotAdapter
    from positronic.offboard.spec import Model
    runtime = tempfile.TemporaryDirectory(prefix='molmobot-config-', dir=ROOT / 'tmp')
    directory = Path(runtime.name)
    try:
        config = yaml.safe_load((artifacts / 'checkpoint/config.yaml').read_text())
        # Upstream tokenizer_dir is a cache setting; identifier itself must be local.
        config = local_tokenizer_config(config, artifacts / 'tokenizer', ROOT / 'cache/huggingface')
        (directory / 'config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
        (directory / 'model.pt').symlink_to(artifacts / 'checkpoint/model.pt')
        wrapper = SynthManipMolmoInferenceWrapper(checkpoint_path=str(directory), device='cuda',
                                                 use_bfloat16=True, compile_model=False, states_mode='cross_attn')
        class NativeModel(MolmoBotAdapter, Model):
            def meta(self):
                return {**super().meta(), 'type': 'molmobot', 'status': 'loaded_unqualified',
                        'checkpoint_revision': 'cbe6ec358958d07ddfb20d3aa54e560e9e1b18c9'}
            def close(self):
                super().close()
                self.model = None
                runtime.cleanup()
        return NativeModel(wrapper, history_mode=history_mode)
    except BaseException:
        runtime.cleanup()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts/molmobot')
    parser.add_argument('--history-mode', choices=('client_stack', 'server_rpc'), default='client_stack')
    parser.add_argument('--fps', type=float, default=15.0)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.fps) or args.fps <= 0 or not 1 <= args.port <= 65535:
        parser.error('Require positive finite fps and valid port')
    pins = json.loads(PINS.read_text())
    artifacts = owned(args.artifacts)
    result = verify_artifacts(artifacts, pins)
    print(json.dumps(result), flush=True)
    if args.verify_only:
        return
    offline_environment()
    from positronic.offboard.server import serve_model, websocket
    from .native import deployment
    pipeline = deployment(fps=args.fps, history_mode=args.history_mode)
    wire = websocket.override(**{'served_address.host': '0.0.0.0', 'served_address.port': args.port}).instantiate()
    serve_model(lambda: build_model(artifacts, args.history_mode), pipeline, [wire], idle_timeout_min=None)


if __name__ == '__main__':
    main()
