"""Native1/2/12session lifecycle and mixed-prompt qualification, ten RPCs per wave.

Uses consumed development observations and virtual uncharged client time. This
tests schema/lifecycle/load; it does NOT establish physical15Hz delivered cadence.
"""
import argparse
import json
from pathlib import Path

import qualify_images as images
import qualify_sessions as sessions
from qualify_prompts import synthetic_prompt, prompt_metadata


def stages(plan, address, image, directory, env, guard):
    reports = {}
    for count in (1, 2, 12):
        guard(directory / f'guard-{count}.log')
        output = directory / f'mixed-{count}.json'
        command = images.h.namespace_command([
            plan['python'], str(images.h.ROOT / 'experiments/qualify_molmobot.py'), '--client',
            '--sessions', str(count), '--url', f'ws://{address}:8000', '--image', image,
            '--recordings', plan['recordings']])
        images.h.bounded(command, output, env, 180, Path(plan['repo']))
        report = images.checked_report(output, count)
        assert report['prompts'] == [prompt_metadata(i) for i in range(count)]
        assert all(wave.get('validated_inference_results',0) >= 10
                   for worker in report['workers'] for wave in worker['waves'])
        reports[str(count)] = report
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--recordings', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--client', action='store_true')
    parser.add_argument('--sessions', type=int, choices=(1,2,12))
    parser.add_argument('--url')
    parser.add_argument('--image')
    args = parser.parse_args()
    images.h.owned(args.recordings)
    if args.client:
        assert not args.execute and args.sessions is not None
        host,port=sessions.validate_identity(args.url,args.image)
        report=sessions.qualify(host,port,args.recordings,args.sessions,10,
                                task_override=[synthetic_prompt(i) for i in range(args.sessions)])
        report.update(prompts=[prompt_metadata(i) for i in range(args.sessions)],image=args.image,
                      requested_rpc_per_session_per_wave=10,
                      scope='Native protocol and load; virtual uncharged client clock; delivered15Hz cadence unmeasured')
        print(json.dumps(report,indent=2,allow_nan=False))
        return 0 if report['passed'] else 2
    assert args.plan is not None
    plan=images.validated_plan(json.loads(args.plan.read_text()),args.recordings)
    plan.update(stages=[1,2,12],rpc_calls_per_wave=10,
                worst_case_seconds=2*(plan['ready_timeout_s']+3*180+360)+90)
    print(json.dumps(plan,indent=2))
    if args.execute:
        path=images.execute(plan,stage_runner=stages)
        print(json.dumps({'results':str(path)}))
        return 0 if all(row['status']=='passed' for row in json.loads(path.read_text())) else 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
