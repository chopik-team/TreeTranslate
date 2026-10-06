"""Curate existing AW0.8x evidence; no translation, OCR, models or runtime edits."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'qa/aw086/benchmarks'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')


def main():
    groups = {
        'final100': ('100pdf_final_speed_calibration', ['run_manifest.json', 'sample_manifest.json', 'run_summary.json',
                    'stage_profile.json', 'nmt_profile.json', 'resource_summary.json', 'output_equivalence.json',
                    'full_archive_forecast.json', 'final_evidence_audit.json']),
        'initial100': ('speed_calibration_100', ['run_summary.json', 'run_manifest.json', 'measurement_protocol.json',
                      'calibration_analysis.json', 'full_archive_recount.json', 'final_receipt.json']),
        'ocr_adaptive': ('ocr_adaptive_runtime', ['sample_manifest.json', 'fixed20_result.json', 'equivalence.json',
                        'hardware_plan.json', 'final_audit.json', 'full_pytest.json']),
        'glossary': ('glossary_hot_path', ['sample_manifest.json', 'fixed20_result.json', 'lookup_equivalence.json',
                    'output_equivalence.json', 'query_plan.json', 'fixed20_lookup_profile.json', 'final_audit.json', 'full_pytest.json']),
        'pipeline': ('adaptive_pipeline', ['sample_manifest.json', 'fixed20_result.json', 'output_equivalence.json',
                    'lookup_equivalence.json', 'pipeline_metrics.json', 'pipeline_plan.json', 'mini_benchmarks.json', 'final_audit.json', 'full_pytest.json']),
        'runtime_polish': ('final_speed_patch_5pdf', ['sample_manifest.json', 'fixed5_result.json', 'accepted_changes.json',
                          'lock_profile.json', 'output_equivalence.json', 'full_pytest.json']),
    }
    copied = []
    for name, (folder, files) in groups.items():
        for filename in files:
            source = ROOT / 'qa/aw081' / folder / filename
            target = DEST / name / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(dict(path=target.relative_to(ROOT).as_posix(), source=source.relative_to(ROOT).as_posix(),
                               size=target.stat().st_size, sha256=digest(target)))
    original = ROOT / 'qa/aw081/nmt_batch_scheduler_5pdf'
    research = ROOT / 'qa/experiments/nmt_batch_scheduler'
    for filename in ('rejected_prototype.zip', 'sample_manifest.json', 'scheduler_design.json', 'nmt_profile.json',
                     'fixed5_result.json', 'output_equivalence.json', 'rollback.json', 'full_pytest.json'):
        source = original / filename
        target = research / ('evidence' if filename != 'rejected_prototype.zip' else '') / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(dict(path=target.relative_to(ROOT).as_posix(), source=source.relative_to(ROOT).as_posix(),
                           size=target.stat().st_size, sha256=digest(target)))
    baseline = json.loads((original / 'baseline.json').read_text('utf8'))
    replay = json.loads((original / 'batch_replay.json').read_text('utf8'))
    captured = [r for r in baseline['nmt']['batches'] if r['device'] == 'cuda' and 'm2m100' in r['model']
                and r['sequences'] == 1 and r['tokens'] <= 32 and 'outputs' in r]
    assert len(captured) == 994
    save(research / 'evidence/native_replay_inputs.json', dict(options=replay['options'], captured_requests=captured,
        source_baseline_sha256=digest(original / 'baseline.json'), scope='Only captured short native requests; not a corpus ZIP'))
    save(research / 'summary.json', dict(status='REJECTED', scope='AW0.8x exact-output contract/model/runtime',
        baseline_commit='9aa36fc327463b5ef11d6d02e40a810207bd5e8f',
        baseline_kind='Uncommitted production hashes in evidence/rollback.json; baseline commit alone is insufficient',
        baseline_run='2bf4fd0f345e', captured_requests=994,
        replay={key: dict(seconds=row['seconds'], mismatches=len(row['mismatches']),
                         exact_outputs=row['exact_outputs']) for key, row in replay['results'].items()},
        canonical_replay_evidence='qa/aw081/nmt_batch_scheduler_5pdf/batch_replay.json',
        production_restored_files=json.loads((original / 'rollback.json').read_text('utf8'))['restored_files']))
    save(DEST / 'evidence_index.json', dict(policy='Exact copies of compact existing evidence; local raw corpus/outputs/logs excluded',
        files=copied, total_bytes=sum(r['size'] for r in copied),
        research_derived_inputs='qa/experiments/nmt_batch_scheduler/evidence/native_replay_inputs.json',
        preserved_test_fixture='qa/aw081/nmt_batch_scheduler_5pdf/batch_replay.json'))
    print(json.dumps(dict(copied_files=len(copied), bytes=sum(r['size'] for r in copied), captured_requests=len(captured))))


if __name__ == '__main__':
    main()
