"""AW0.8 representative matrix; existing benchmark workers, no downloads."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.benchmark_translation import local_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['baseline', 'final'], required=True)
    args = parser.parse_args()
    qa = ROOT / 'docs/qa/aw08'
    qa.mkdir(parents=True, exist_ok=True)
    sentence = 'Save the configuration file before restarting the application. '
    cases = [dict(id=name, source='en', target='ru', text=text) for name, text in (
        ('short', 'Save the file.'), ('medium', sentence * 8),
        ('long', '\n\n'.join(sentence * 8 for _ in range(8))),
        ('very-long', '\n\n'.join(sentence * 8 for _ in range(24))))]
    cases += [dict(id='zh-ru', source='zh', target='ru', text='连续铸造机因冷却水压力下降而停止。'),
              dict(id='en-fr', source='en', target='fr', text='Do not restart the machine before the inspection is complete.')]
    corpus = qa / 'performance-corpus.json'
    corpus.write_text(json.dumps({'cases': cases}, ensure_ascii=False, indent=2), encoding='utf-8')
    matrix = [(name, 'gpu', 'balanced') for name in ('short', 'medium', 'long', 'very-long')]
    matrix += [('medium', device, 'balanced') for device in ('cpu', 'auto')]
    matrix += [('zh-ru', 'gpu', profile) for profile in ('economy', 'fast', 'automatic', 'balanced', 'turbo', 'maximum')]
    matrix += [('en-fr', 'gpu', 'economy')]
    import psutil
    report = {'phase': args.phase, 'python': sys.version, 'os': platform.platform(),
              'cpu': local_command(['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_Processor).Name']),
              'gpu': local_command(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader']),
              'ram_bytes': psutil.virtual_memory().total,
              'versions': {x: importlib.metadata.version(x) for x in ('ctranslate2','argostranslate','sentencepiece','PySide6','pypdfium2')},
              'method': 'fresh process per row; first cold call, 1 warmup, 3 measured runs; no output cache; GPU figures device-total snapshots',
              'results': []}
    output = qa / f'performance-{args.phase}.json'
    for name, device, profile in matrix:
        cmd = [sys.executable, str(ROOT/'tools/benchmark_translation.py'), '--worker', '--backends', 'router',
               '--devices', device, '--profiles', profile, '--cases', name, '--corpus', str(corpus), '--repeats', '3', '--warmup', '1']
        try:
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=360,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if run.returncode:
                raise RuntimeError(run.stderr[-2000:])
            row = json.loads(run.stdout)
        except Exception as error:
            row = {'case': name, 'requested_device': device, 'profile': profile, 'error': str(error)}
        report['results'].append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(name, device, profile, row.get('cold_ms'), row.get('warm_median_ms'), row.get('errors', row.get('error')), flush=True)


if __name__ == '__main__':
    main()
