"""Read-only coverage evidence, not a publisher or a semantic acceptance rule."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from app.glossary.bundled import bundled_paths
from app.glossary.normalization import normalize

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run():
    inventory = QA / 'major_root_causes.json'
    entries = []
    hashes = {}
    for path in bundled_paths():
        hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
        with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as connection:
            connection.row_factory = sqlite3.Row
            for entry in connection.execute('SELECT * FROM entries'):
                row = dict(entry)
                if row['status'] in ('DISABLED', 'REJECTED', 'AUTO'):
                    continue
                try:
                    metadata = json.loads(row['notes'])
                except (ValueError, TypeError):
                    metadata = {}
                row['metadata'] = metadata if isinstance(metadata, dict) else {}
                row['pack'] = path.name
                entries.append(row)
    rows = []
    for case in json.loads(inventory.read_text('utf8'))['rows']:
        source = normalize(case['source'])
        candidates = []
        for entry in entries:
            surfaces = [entry['source_term'], *json.loads(entry['variants'])]
            for surface in surfaces:
                if not surface or normalize(surface) not in source:
                    continue
                selected = any(m['source'] == surface for m in case['selected_knowledge'])
                candidates.append(dict(source=surface, canonical_source=entry['source_term'],
                    target=entry['target_term'], pack=entry['pack'], priority=entry['priority'],
                    domain=entry['domain'], context=entry['context'], status=entry['status'],
                    metadata=entry['metadata'], selected_surface=selected,
                    eligibility='Not established: raw substring inventory does not apply context/type/word-boundary filters.'))
        rows.append(dict(id=case['id'], source_text_sha256=case['source_text_sha256'],
            selected_concepts=case['selected_concepts'], raw_available_candidates=candidates,
            diagnosis='Coverage must be checked against actual active profile and candidate filters before publishing new terms.'))
    result = dict(revision='AW0.81', inventory_sha256=sha256(inventory.read_bytes()).hexdigest(),
        production_assets_sha256=hashes, assets_unchanged=True, references_not_used=True,
        frozen_final_set_not_read=True, rows=rows)
    (QA / 'major_coverage_evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print('cases', len(rows), 'raw candidates', sum(len(r['raw_available_candidates']) for r in rows))


if __name__ == '__main__':
    run()
