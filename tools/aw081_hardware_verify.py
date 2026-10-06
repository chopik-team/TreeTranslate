"""Independent final evidence audit; no model, OCR or translation execution."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_speed_calibration_100 import frozen_hashes, save

QA = ROOT / 'qa/aw081/hardware_scaling_20'


def verify():
    required = ['experiment_manifest.json', 'sample_manifest.json', 'runs.jsonl',
                'resource_samples.jsonl', 'hardware_summary.json',
                'factorial_analysis.json', 'mode_recommendations.json',
                'scheduler_analysis.json', 'sustained_analysis.json',
                'residency_overlap_probe.json', 'completion_receipt.json']
    assert all((QA / name).is_file() for name in required)
    experiment = json.loads((QA / required[0]).read_text('utf8'))
    sample = json.loads((QA / required[1]).read_text('utf8'))
    calibration = json.loads((ROOT / 'qa/aw081/speed_calibration_100/sample_manifest.json').read_text('utf8'))
    calibration_members = {doc['member_path']: doc for doc in calibration['documents']}
    assert hashlib.sha256((QA / required[1]).read_bytes()).hexdigest() == experiment['sample_manifest_sha256']
    assert len(sample['documents']) == 20
    assert sum(doc['pages'] for doc in sample['documents']) == 39
    for doc in sample['documents']:
        assert doc['member_path'] in calibration_members
        for key in ['source_sha256', 'source_size', 'pages']:
            assert doc[key] == calibration_members[doc['member_path']][key]
    for name, digest in experiment['qa_script_sha256'].items():
        assert hashlib.sha256((ROOT / 'tools' / name).read_bytes()).hexdigest() == digest
    source = Path(sample['sample_archive'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == sample['sample_archive_sha256']
    production = json.loads((QA / 'production_before.json').read_text('utf8'))
    assert frozen_hashes() == production
    rows = [json.loads(line) for line in (QA / 'runs.jsonl').read_text('utf8').splitlines()]
    by_label = {row['label']: row for row in rows}
    assert len(by_label) == len(rows)
    assert all(label in by_label for label in experiment['run_order'])
    completion = json.loads((QA / 'completion_receipt.json').read_text('utf8'))
    assert not completion['full_archive_run'] and not completion['production_changes']
    assert len(rows) == sum(completion[key] for key in
                            ['main_runs', 'scheduler_runs', 'sustained_runs', 'additional_sweeps'])
    plan = json.loads((QA / 'post_matrix_manifest.json').read_text('utf8'))
    assert all(label in by_label for label in plan['scheduler_order'])
    assert all(config + '_sustained' in by_label for config in plan['sustained_order'])
    hook = json.loads((QA / 'easy_first_hook_validation.json').read_text('utf8'))
    assert hook['status'] == 'PASS' and hook['modified_processing_loops'] == 1
    trials = []
    reference_receipt = json.loads((QA / 'runs/mid/execution.json').read_text('utf8'))
    with ZipFile(reference_receipt['outputs'][0]) as reference:
        reference_directories = {entry.filename for entry in reference.infolist() if entry.is_dir()}
    with ZipFile(source) as original:
        members = set(original.namelist())
        assert len(members) == 20 and original.testzip() is None
        assert members == {doc['member_path'] for doc in sample['documents']}
        for doc in sample['documents']:
            data = original.read(doc['member_path'])
            assert len(data) == doc['source_size']
            assert hashlib.sha256(data).hexdigest() == doc['source_sha256']
        for row in rows:
            directory = QA / 'runs' / row['label']
            receipt = json.loads((directory / 'execution.json').read_text('utf8'))
            with sqlite3.connect((directory / 'empty-tm.db').resolve().as_uri() + '?mode=ro', uri=True) as memory:
                assert memory.execute('SELECT count(*) FROM units').fetchone()[0] == 0
            assert receipt['production_unchanged'] and receipt['source_immutable']
            assert not receipt['monitor_errors']
            expected_eligible = (not receipt['fatal'] and row['processed'] == 20
                                 and row['equivalence']['status'] == 'PASS')
            assert row['eligible'] == expected_eligible
            if receipt['fatal']:
                trials.append(dict(label=row['label'],status='RECORDED_FATAL',fatal=receipt['fatal']))
                continue
            fingerprint = json.loads((directory / 'fingerprints.json').read_text('utf8'))
            assert row['processed'] == 20 and set(fingerprint) == members
            assert len(receipt['outputs']) == 1
            preserved = 0
            with ZipFile(receipt['outputs'][0]) as output:
                entries = output.infolist()
                all_names = output.namelist()
                names = [entry.filename for entry in entries if not entry.is_dir()]
                directories = {entry.filename for entry in entries if entry.is_dir()}
                assert len(all_names) == len(set(all_names)) and output.testzip() is None
                assert len(names) == 20
                assert directories == reference_directories
                assert all(entry.file_size == 0 for entry in entries if entry.is_dir())
                assert set(names) == {doc['output_member'] for doc in fingerprint.values()}
                for member, doc in fingerprint.items():
                    if doc['status'] == 'FAILED_SOURCE_PRESERVED':
                        data = output.read(doc['output_member'])
                        assert doc['output_member'] == member and data == original.read(member)
                        assert hashlib.sha256(data).hexdigest() == doc['failed_sha256']
                        preserved += 1
            assert preserved == row['failed']
            warmups = list((directory / 'warmup-output').glob('*.zip')) if row['sustained'] else []
            if row['sustained']:
                assert len(warmups) == 1
                with ZipFile(warmups[0]) as warm:
                    assert len(warm.namelist()) == len(set(warm.namelist()))
                    assert sum(not entry.is_dir() for entry in warm.infolist()) == 20
                    assert warm.testzip() is None
            trials.append(dict(label=row['label'],status='PASS_OPERATIONAL_AUDIT',
                               output_equivalence=row['equivalence']['status'],
                               preserved_exact=preserved,warmup_archives_verified=len(warmups),
                               translation_memory_rows=0,directory_paths_equivalent=True,
                               directory_entries=len(directories)))
    factorial = json.loads((QA / 'factorial_analysis.json').read_text('utf8'))
    if factorial.get('raw_exploratory_contrasts'):
        assert json.loads((QA / 'analysis_math_check.json').read_text('utf8'))['status'] == 'PASS'
    report = ROOT / 'docs/AW0.81_HARDWARE_SCALING_20PDF.md'
    assert report.is_file() and report.stat().st_size > 1000
    import psutil
    benchmark_names = {'aw081_hardware_scaling_20.py', 'aw081_hardware_post.py',
                       'aw081_hardware_easy_first.py', 'aw081_hardware_probe.py',
                       'aw081_hardware_windows.py'}
    active = []
    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            if any(Path(arg).name in benchmark_names for arg in process.info['cmdline'] or []):
                active.append(process.info['pid'])
        except psutil.Error:
            continue
    assert not active, f'Benchmark processes still active: {active}'
    save(QA / 'final_evidence_audit.json',dict(status='PASS',
         scope='Operational evidence/source/safety audit; not semantic acceptance of rejected variants.',
         benchmark_root_processes_remaining=active,
         required_files=required,production_frozen_files=len(production),
         source_members=20,source_pages=39,main_trials=9,total_measured_trials=len(rows),
         trials=trials,full_archive_run=False,report=str(report),
         qa_analysis_script_sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in sorted((ROOT / 'tools').glob('aw081_hardware_*.py'))}))
    print('FINAL_EVIDENCE_AUDIT PASS', len(rows), 'trials;', len(production), 'production hashes unchanged')


if __name__ == '__main__':
    verify()
