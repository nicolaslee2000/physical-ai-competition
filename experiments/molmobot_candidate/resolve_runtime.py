"""Resolve and freeze a separate MolmoBot serving environment in the pinned base.

Run only through control/resolve-molmobot-runtime.sh. No model construction/GPU.
The base Torch/CUDA inventory is fixed; upstream application pins are constraints.
"""
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import venv

ROOT = Path('/opt/hderc-internal/nick/physical-ai-competition')
STAGE = ROOT / 'packaging/molmobot'


def run(args, *, timeout=900):
    subprocess.run([str(x) for x in args], check=True, timeout=timeout, cwd=STAGE)


def main():
    assert sys.version_info[:2] == (3, 11)
    import torch
    assert torch.__version__.startswith('2.8.') and torch.version.cuda == '12.8'
    assert 'sm_120' in torch.cuda.get_arch_list() if torch.cuda.is_available() else True
    inventory = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in md.distributions()}
    (STAGE / 'base-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    env_path = STAGE / 'venv'
    if not env_path.exists():
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(env_path)
    python = env_path / 'bin/python'
    pip = [python, '-m', 'pip', '--disable-pip-version-check']
    wheelhouse = STAGE / 'wheelhouse'
    if '--validate-only' in sys.argv:
        assert (STAGE / 'requirements.lock').is_file()
        finish(python, pip, wheelhouse)
        return
    upstream = tomllib.loads((STAGE / 'src/MolmoBot/MolmoBot/uv.lock').read_text())
    # CUDA libraries and Torch are inherited from the immutable base. Never resolve
    # its older upstream Torch2.7 stack on the Blackwell target.
    pins = {}
    for p in upstream['package']:
        name = p['name']
        if name.startswith('nvidia-') or name in ('torch', 'torchvision', 'torchaudio', 'triton'):
            continue
        if p.get('version') and p.get('source', {}).get('registry'):
            if name in pins and pins[name] != p['version']:
                raise ValueError('Multi-version upstream constraint needs explicit review: ' + name)
            pins[name] = p['version']
    for name, version in inventory.items():
        if name.startswith('nvidia-') or name in ('torch', 'torchvision', 'torchaudio', 'triton'):
            pins[name] = version
    constraints = STAGE / 'constraints.txt'
    constraints.write_text(''.join(f'{k}=={v}\n' for k, v in sorted(pins.items())))
    sources = [STAGE / 'src/MolmoBot/MolmoBot']
    pos = STAGE / 'src/positronic'
    sources += [pos / name for name in ('wire', 'model_server', 'client', 'vocabulary', 'evals')]
    sources += [pos]
    source_dir = STAGE / 'source-wheels'
    source_dir.mkdir(exist_ok=True)
    run([*pip, 'wheel', '--no-deps', '--wheel-dir', source_dir, *sources], timeout=300)
    source_wheels = sorted(source_dir.glob('*.whl'))
    assert len(source_wheels) == 7, 'Use a clean source-wheel stage on first resolution'
    import shutil
    for wheel in source_wheels:
        shutil.copyfile(wheel, wheelhouse / wheel.name)
    report = STAGE / 'resolve-report.json'
    run([*pip, 'install', '--dry-run', '--report', report, '--constraint', constraints,
         '--find-links', wheelhouse, *source_wheels, 'torchmetrics==1.9.0'], timeout=900)
    resolution = json.loads(report.read_text())
    wanted = []
    for row in resolution['install']:
        info = row['download_info']
        metadata = row['metadata']
        name = metadata['name'].lower().replace('_', '-')
        if name.startswith('nvidia-') or name in ('torch', 'torchvision', 'torchaudio', 'triton'):
            raise ValueError('Resolver tried to replace immutable base GPU packages: ' + name)
        wanted.append(f"{metadata['name']}=={metadata['version']}")
    (STAGE / 'resolved-requirements.txt').write_text('\n'.join(wanted) + '\n')
    # Build any required sdist into a wheel now; inference/build runs will be offline.
    if wanted:
        run([*pip, 'wheel', '--no-deps', '--constraint', constraints, '--find-links', wheelhouse,
             '--wheel-dir', wheelhouse, '-r', STAGE / 'resolved-requirements.txt'], timeout=900)
    finish(python, pip, wheelhouse)


def finish(python, pip, wheelhouse):
    import zipfile
    from email.parser import BytesParser
    requirements = []
    for path in sorted(wheelhouse.glob('*.whl')):
        with zipfile.ZipFile(path) as z:
            # Vendored projects (for example setuptools/_vendor) can carry their
            # own METADATA. Only the wheel's top-level dist-info describes it.
            names = [n for n in z.namelist() if n.count('/') == 1 and n.endswith('.dist-info/METADATA')]
            assert len(names) == 1
            metadata = BytesParser().parsebytes(z.read(names[0]))
        requirements.append(f"{metadata['Name']}=={metadata['Version']} --hash=sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    (STAGE / 'requirements.lock').write_text('\n'.join(sorted(requirements)) + '\n')
    run([*pip, 'install', '--no-index', '--no-deps', '--require-hashes', '--find-links', wheelhouse,
         '-r', STAGE / 'requirements.lock'], timeout=600)
    run([*pip, 'check'], timeout=60)
    # Import checks reach the loader/model configs and native declaration without
    # constructing weights, opening sockets or touching an evaluator environment.
    run([python, '-c', '''import torch,json
from olmo.models.molmobot.inference_wrapper import SynthManipMolmoInferenceWrapper
from olmo.models.model_config import BaseModelConfig
from olmo.train.checkpointer import load_model_state
from positronic.offboard.server import serve_model
from molmobot_candidate.native import deployment
from positronic.policy.spec import from_spec
p=deployment()
from_spec(p.local.to_spec())
import yaml
from pathlib import Path
from molmobot_candidate.serve import local_tokenizer_config
stage=Path('/opt/hderc-internal/nick/physical-ai-competition/packaging/molmobot')
data=yaml.safe_load((stage/'checkpoint-config.yaml').read_text())
data=local_tokenizer_config(data,Path('/opt/hderc-internal/nick/physical-ai-competition/artifacts/molmobot/tokenizer'),stage/'cache/huggingface')
(stage/'checkpoint-config-local.yaml').write_text(yaml.safe_dump(data,sort_keys=False))
config=BaseModelConfig.load(stage/'checkpoint-config-local.yaml',key='model')
with torch.device('meta'):
    model=config.build_model()
assert all(p.device.type=='meta' for p in model.parameters())
print(json.dumps({'imports':'passed','torch':torch.__version__,'cuda':torch.version.cuda,'model_loaded':False,'meta_model_constructed':True}))
'''], timeout=90)
    manifest = {'stage': 'resolved_and_imported', 'model_loaded': False,
                'base': json.loads((ROOT / 'experiments/molmobot_candidate/packaging-pins.json').read_text())['base']['reference'],
                'lock_sha256': hashlib.sha256((STAGE / 'requirements.lock').read_bytes()).hexdigest(),
                'wheels': [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                           for p in sorted(wheelhouse.glob('*.whl'))]}
    (STAGE / 'runtime-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'stage': manifest['stage'], 'wheels': len(manifest['wheels'])}), flush=True)


if __name__ == '__main__':
    main()
