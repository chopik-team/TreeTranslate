"""Read-only production freeze audit; only release version marker may differ."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw086/closure'


def tree_hash(rows):
    return hashlib.sha256(''.join(r['path']+'\0'+r['sha256']+'\n' for r in rows).encode()).hexdigest()


def main():
    before = json.loads((QA/'production_before.json').read_text('utf8'))
    after, changes = [], []
    for row in before['files']:
        path = ROOT / row['path']
        data = path.read_bytes()
        current = dict(path=row['path'],size=len(data),sha256=hashlib.sha256(data).hexdigest())
        after.append(current)
        if current['sha256'] != row['sha256']:
            changes.append(row['path'])
            assert row['path'] in {'app/config/constants.py','assets/language-support.json'}, f"Forbidden production change: {row['path']}"
            original = (data.replace(b'APP_VERSION = "AW0.86"',b'APP_VERSION = "AW 0.8.3"')
                        if row['path'] == 'app/config/constants.py' else
                        data.replace(b'"version": "AW0.86"',b'"version": "AW 0.8.3"'))
            assert hashlib.sha256(original).hexdigest() == row['sha256'], 'Version marker is not the only constant change'
    expected = {r['path'] for r in before['files'] if r['path'].startswith(('app/','assets/'))}
    actual = {p.relative_to(ROOT).as_posix() for folder in ('app','assets') for p in (ROOT/folder).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')
              and not p.name.endswith(('-wal','-shm'))}
    assert expected == actual, 'Production file inventory changed'
    rollback_path = ROOT/'qa/experiments/nmt_batch_scheduler/evidence/rollback.json'
    rollback = json.loads(rollback_path.read_text('utf8'))
    restored = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == rollback['production_hashes'][name.replace('/', '\\')]
                for name in rollback['restored_files']}
    assert all(restored.values()), 'Rejected NMT production files differ from restored baseline'
    assert not (ROOT/'app/engine/runtime/semantic_batch_scheduler.py').exists()
    manifest = json.loads((ROOT/'assets/knowledge/manifest.json').read_text('utf8'))
    dictionaries = {p['file']:hashlib.sha256((ROOT/'assets/knowledge'/p['file']).read_bytes()).hexdigest() for p in manifest['packs']}
    assert len(dictionaries) == 49
    assert all(dictionaries[p['file']] == p['sha256'] for p in manifest['packs'])
    result = dict(status='PASS',pre_closure_tree_sha256=before['production_tree_sha256'],
        production_tree_sha256=tree_hash(after),allowed_changes=changes,production_logic_unchanged=True,
        hash_policy='SHA256 of sorted relative-path NUL raw-file-SHA256 newline records; working bytes before Git text normalization',
        files=after,rejected_nmt_restored_files_match=restored,knowledge_db_sha256=dictionaries,
        models_reference='vendor/models/models_manifest.json and vendor/model-metadata/ocr/models_manifest.json',
        marker_inventory=dict(current='app/config/constants.py:APP_VERSION',consumers=['About UI','document logs','language support builder'],
            historical_data=['benchmark asset version 0.81','Knowledge revisions','language-support history snapshots','TMX format component version 0.7'],
            package_metadata='No pyproject/setup package version or independent CLI/build app version present'))
    (QA/'production_after.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','knowledge_db_sha256')},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
