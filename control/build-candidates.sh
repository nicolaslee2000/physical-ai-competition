#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$task_root/experiments/candidates"
for horizon in 6of15 10of15; do
  python3 "$task_root/control/guard.py" check
  bash "$task_root/docker/engine.sh" buildx build --platform linux/amd64 \
    --provenance=false --sbom=false --network=none --load \
    -f "Dockerfile.horizon-$horizon" -t "nick/physical-ai:horizon-$horizon" .
done
python3 - "$task_root" <<'PY'
import json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); rows=[]
for h in ('6of15','10of15'):
    tag='nick/physical-ai:horizon-'+h
    image=subprocess.check_output(['bash',str(root/'docker/engine.sh'),'image','inspect',tag,'--format','{{.Id}}'],text=True).strip()
    rows.append({'name':'horizon-'+h,'image':image,'local_tag':tag,'identity_kind':'local_docker_config_sha256'})
(root/'state/candidate-images.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Local candidate image IDs recorded; no official submission performed.')
PY
