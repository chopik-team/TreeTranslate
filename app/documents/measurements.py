"""Persistent, content-free measurements collected from the existing diagnostic log."""
import json
import re
from pathlib import Path
from statistics import median

from app.config.paths import APP_DATA_DIR, LOGS_DIR, ASSETS_DIR

MEASUREMENTS_DIR = APP_DATA_DIR / 'measurements'


def collect(log_dir=LOGS_DIR, destination=MEASUREMENTS_DIR):
    runs = {}
    paths = sorted(Path(log_dir).glob('documents.log*'), reverse=True)
    for path in paths:
        for line in path.read_text('utf-8', errors='replace').splitlines():
            match = re.search(r'run=([a-f0-9]{12})\b', line)
            if not match:
                continue
            run = runs.setdefault(match[1], dict(run=match[1], processes={}, sources=[], routes=[], ocr=[]))
            for marker, key in (('selection=', 'selections'), ('document_metadata=', 'documents'), ('scan_result=', 'scan_results')):
                if marker in line:
                    try:
                        run.setdefault(key, []).append(json.loads(line.split(marker, 1)[1]))
                    except ValueError:
                        pass
            scan_link = re.search(r'scan_run=([a-f0-9]{12})', line)
            if scan_link:
                run['scan_run'] = scan_link[1]
            started = re.search(r'operation=(\w+) started .*files=(\d+) requested_source=(.*?) target=(.*?) device=(\S+)', line)
            if started:
                run.update(operation=started[1], date=line[:23], files=int(started[2]),
                           requested_source=started[3], target=started[4], requested_device=started[5])
            timing = re.search(r'process=(\S+) event=end .*seconds=([\d.]+) state=(\S+)', line)
            if timing:
                run['processes'].setdefault(timing[1], []).append(float(timing[2]))
            source = re.search(r'source=(.*?) bytes=(\d+) sha256=(\w+) pages=(\d+) segments=(\d+)', line)
            if source:
                run['sources'].append(dict(path=source[1], bytes=int(source[2]), sha256=source[3],
                                           pages=int(source[4]), segments=int(source[5])))
                details = re.search(r'chars=(\d+) native_segments=(\d+) ocr_segments=(\d+)', line)
                if details:
                    run['sources'][-1].update(zip(('chars', 'native_segments', 'ocr_segments'), map(int, details.groups())))
            prediction = re.search(r'eta calibration_runs=.*estimated_seconds=([\d.]+)', line)
            if prediction:
                run['predicted_seconds'] = float(prediction[1])
            route = re.search(r'route source=(\S+) target=(\S+) domain=(\S+) backend=(\S+) device=(\S+) compute_type=(\S+)', line)
            if route:
                value = dict(zip(('source', 'target', 'domain', 'backend', 'device', 'compute_type'), route.groups()))
                if value not in run['routes']:
                    run['routes'].append(value)
            ocr = re.search(r'OCR backend=(\S+) device=(\S+) segments=(\d+) worker_seconds=([\d.]+)', line)
            if ocr:
                run['ocr'].append(dict(backend=ocr[1], device=ocr[2], segments=int(ocr[3]), seconds=float(ocr[4])))
            workload = re.search(r'workload file=(\d+) native_chars=(\d+) ocr_regions=(\d+)', line)
            if workload:
                run.setdefault('workloads', []).append(dict(file=int(workload[1]), native_chars=int(workload[2]),
                                                          ocr_regions=int(workload[3])))
            finished = re.search(r'finished state=(\S+) elapsed=([\d.]+) warnings=(\d+)', line)
            if finished:
                run.update(state=finished[1], elapsed=float(finished[2]), warnings=int(finished[3]))
                active = re.search(r'active_seconds=([\d.]+)', line)
                if active:
                    run['active_seconds'] = float(active[1])
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for run in runs.values():
        # Only archive complete logs; a rotated fragment cannot replace a full record.
        if run.get('operation') not in {'translate', 'scan'} or 'state' not in run:
            continue
        linked = runs.get(run.get('scan_run'))
        if linked:
            run['selections'] = linked.get('selections', [])
            run['scan_results'] = linked.get('scan_results', [])
            run['scan_processes'] = linked.get('processes', {})
        path = destination / (run['run'] + '.json')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(path)
    return runs


def bundled_calibration(config):
    from app.engine.languages import language_code
    try:
        rates=json.loads((ASSETS_DIR/'config/document-performance.json').read_text('utf8'))
    except (OSError,ValueError):return None
    if (language_code(config.target)!=rates['target_language']
            or language_code(config.source) not in {'auto',rates['source_language']}
            or config.device.value.lower()=='cpu'):
        return None
    return rates


def calibration(config, directory=MEASUREMENTS_DIR):
    from app.engine.languages import language_code
    source, target = language_code(config.source), language_code(config.target)
    seed=bundled_calibration(config) if Path(directory)==MEASUREMENTS_DIR else None
    candidates = []
    for path in Path(directory).glob('*.json'):
        try:
            run = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError):
            continue
        routes = [r for r in run.get('routes', []) if r.get('device') in {'cpu','cuda'}]
        if run.get('state') != 'COMPLETED' or not routes or any(r['target'] != target for r in routes):
            continue
        if not run.get('sources') or run.get('elapsed',0)<1:continue
        if run.get('elapsed', 0) - run.get('active_seconds', run.get('elapsed', 0)) > 1:
            continue  # Pauses remain in the journal, but do not bias processing rates.
        if source != 'auto' and any(r['source'] != source for r in routes):
            continue
        if config.device.value.lower() == 'cpu' and any(r['device'] != 'cpu' for r in routes):
            continue
        if config.device.value.lower() in {'cuda', 'gpu'} and not any(r['device']=='cuda' for r in routes):
            continue
        if seed and (run.get('elapsed',0)<5 or not any(r['source']==seed['source_language'] and r['device']=='cuda' for r in routes)):
            continue  # Tiny/mock/other-language CPU runs must not replace measured CUDA priors.
        candidates.append(run)
    if not candidates:
        return seed
    runs = sorted(candidates, key=lambda r: r.get('date', ''), reverse=True)[:8]
    translations = [sum(r['processes'].get('engine_translation', [])) / max(1, sum(s['segments'] for s in r['sources'])) for r in runs]
    ocr = [o['seconds'] for r in runs for o in r['ocr']]
    writes = [sum(r['processes'].get('document_write', [])) / max(1, sum(s['pages'] for s in r['sources'])) for r in runs]
    densities = [s['chars'] / s['segments'] for r in runs for s in r['sources'] if s.get('chars') and s['segments']]
    return dict(seed or {},segment_seconds=median(translations), ocr_seconds=median(ocr) if ocr else (seed or {}).get('ocr_seconds'),
                write_page_seconds=median(writes), runs=[r['run'] for r in runs],
                # Legacy logs have no character count. Replaced by measured density after new runs.
                chars_per_segment=median(densities) if densities else 80,
                segments_per_page=median([sum(s['segments'] for s in r['sources']) / max(1, sum(s['pages'] for s in r['sources'])) for r in runs]))
