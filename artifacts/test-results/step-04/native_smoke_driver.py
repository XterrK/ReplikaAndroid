#!/usr/bin/env python3
"""One short actual C2 Worker smoke. Never a corpus/quality acceptance gate.

Only audio/id/hash and global automatic policy enter the existing test bridge.
Keep every output, including failed attempts. No app-data wipe or model staging.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--audio-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-summary', type=Path, default=Path('artifacts/test-results/step-04/build-c2-v1/summary.json'))
    args = parser.parse_args()
    repo = Path.cwd()
    assert not args.output.exists(), 'Fresh output required'
    case_id = 'dev-mono-s'
    manifest = json.loads((repo / 'benchmark/eval/manifest.json').read_text())
    case = next(c for c in manifest['files'] if c['id'] == case_id)
    audio = (args.audio_root / case['audio']).resolve()
    assert audio.is_relative_to(args.audio_root.resolve()) and sha(audio) == case['audio_sha256']
    build_path = repo / args.build_summary
    build = json.loads(build_path.read_text())
    assert build['status'] == 'PASS'
    for name in ('debug', 'androidTest'):
        assert sha(repo / build['apks'][name]['path']) == build['apks'][name]['sha256']
    args.output.mkdir()
    commands = []
    run_id = 'c2smoke' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    remote = 'files/evaluation/' + run_id
    report = {'status': 'STAGING', 'run': run_id, 'case': case_id,
              'scope': 'Single actual Android C2 functional smoke; no corpus, quality, speed or ARM acceptance',
              'reference_text_or_counts_staged': False, 'inference_requested': False,
              'driver_source_sha256': sha(Path(__file__)), 'build_summary_sha256': sha(build_path),
              'apk_sha256': {k: v['sha256'] for k, v in build['apks'].items()}}
    def save():
        (args.output / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
    def adb(*words, check=True):
        command = [args.adb, '-s', args.serial, *map(str, words)]
        cp = subprocess.run(command, capture_output=True)
        commands.append({'at': datetime.now(timezone.utc).isoformat(), 'argv': command, 'returncode': cp.returncode})
        (args.output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        if check and cp.returncode:
            raise RuntimeError(str(command) + '\n' + cp.stdout.decode(errors='replace') + cp.stderr.decode(errors='replace'))
        return cp
    old = None
    save()
    try:
        assert adb('shell', 'getprop', 'ro.kernel.qemu').stdout.strip() == b'1', 'Dedicated emulator only'
        old = adb('shell', 'settings', 'get', 'global', 'stay_on_while_plugged_in').stdout.decode().strip()
        adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
        adb('shell', 'wm', 'dismiss-keyguard')
        adb('shell', 'svc', 'power', 'stayon', 'true')
        assert adb('shell', 'settings', 'get', 'global', 'airplane_mode_on').stdout.strip() == b'1'
        assert adb('shell', 'settings', 'get', 'global', 'wifi_on').stdout.strip() == b'0'
        assert adb('shell', 'run-as', 'ru.replika.offline', 'test', '-e', remote, check=False).returncode != 0
        adb('shell', 'run-as', 'ru.replika.offline', 'mkdir', '-p', remote + '/audio')
        temporary = '/data/local/tmp/' + run_id
        for local, relative in [(audio, 'audio/' + case_id + '.wav')]:
            adb('push', local, temporary)
            adb('shell', 'run-as', 'ru.replika.offline', 'cp', temporary, remote + '/' + relative)
            adb('shell', 'rm', temporary)
        batch = {'schema_version': 1, 'run': run_id,
                 'cases': [{'id': case_id, 'audio': 'audio/' + case_id + '.wav', 'sha256': case['audio_sha256']}]}
        local_batch = args.output / 'batch.json'
        local_batch.write_text(json.dumps(batch) + '\n')
        adb('push', local_batch, temporary)
        adb('shell', 'run-as', 'ru.replika.offline', 'cp', temporary, remote + '/batch.json')
        adb('shell', 'rm', temporary)
        report.update(status='RUNNING', inference_requested=True, started_at=datetime.now(timezone.utc).isoformat())
        save()
        cp = adb('shell', 'am', 'instrument', '-w', '-r', '-e', 'class',
                 'ru.replika.EvaluationBatchTest#stagedCanonicalInputsThroughProductionWorker',
                 '-e', 'evalRun', run_id, '-e', 'evalThreads', '2',
                 '-e', 'evalAsrPlan', 'vad_words_context600', '-e', 'evalDiarPlan', 'eres2net_window_v1',
                 '-e', 'evalExpectedSpeakers', '-1',
                 'ru.replika.offline.test/androidx.test.runner.AndroidJUnitRunner', check=False)
        (args.output / 'instrumentation.log').write_bytes(cp.stdout + cp.stderr)
        for name in ['report.json', *[case_id + '.' + suffix + '.json' for suffix in
                                      ('case', 'diagnostics', 'hypothesis', 'diarization-evidence')]]:
            pulled = adb('exec-out', 'run-as', 'ru.replika.offline', 'cat', remote + '/output/' + name, check=False)
            (args.output / (name if pulled.returncode == 0 else name + '.pull-error.txt')).write_bytes(pulled.stdout + pulled.stderr)
        assert cp.returncode == 0 and re.search(rb'OK \(1 tests?\)', cp.stdout) and b'FAILURES!!!' not in cp.stdout
        actual = json.loads((args.output / 'report.json').read_text())
        assert actual['status'] == 'COMPLETE' and [c['id'] for c in actual['cases']] == [case_id]
        report.update(status='SMOKE_PASS', new_model_inference=True, completed_at=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        report.update(status='FAILED', error=str(error))
        raise
    finally:
        if old is not None:
            if old == 'null':
                adb('shell', 'settings', 'delete', 'global', 'stay_on_while_plugged_in')
            else:
                adb('shell', 'settings', 'put', 'global', 'stay_on_while_plugged_in', old)
            report['screen_original'] = old
            report['screen_restored'] = adb('shell', 'settings', 'get', 'global', 'stay_on_while_plugged_in').stdout.decode().strip()
        save()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
