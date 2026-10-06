"""Isolated exact-copy/provenance audit; never exposes held text to authoring.

This detects exact copies and source-document provenance, not paraphrased
leakage. A semantic acceptance run is separate and remains frozen.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from app.glossary.bundled import bundled_paths
from app.glossary.normalization import normalize

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run():
    development = ROOT / 'qa/aw088/development_manifest.json'
    frozen = QA / 'final_holdout_manifest.json'
    diag = QA / 'diagnostic_before.json'
    dev_docs = json.loads(development.read_text('utf8'))['documents']
    final_docs = json.loads(frozen.read_text('utf8'))['documents']
    held_hashes = {d['sha256'] for d in final_docs}
    held_members = {d['member'] for d in final_docs}
    held_groups = {d['group'] for d in final_docs}
    overlaps = [d['sha256'] for d in dev_docs
                if d['sha256'] in held_hashes or d['member'] in held_members or d['group'] in held_groups]
    diagnostic = json.loads(diag.read_text('utf8'))['rows']
    diagnostic_sources = {normalize(r['source']): r['id'] for r in diagnostic}
    diagnostic_references = {normalize(r['reference']): r['id'] for r in diagnostic
                             if len(normalize(r['reference'])) >= 40}
    # Read held source only inside this auditor. No text or translation is
    # printed, published, returned to a prompt, or added to a candidate store.
    final_sources = set()
    with sqlite3.connect(f'{(ROOT / "qa/aw088/native_corpus.db").as_uri()}?mode=ro', uri=True) as connection:
        for document in final_docs:
            digest, payload = connection.execute('SELECT sha256,payload FROM documents WHERE member=?',
                                                (document['member'],)).fetchone()
            assert digest == document['sha256']
            final_sources.update(normalize(line) for line in json.loads(payload)['lines'] if len(normalize(line)) >= 24)
    exact_copies, provenance_hits = [], []
    types = Counter()
    asset_hashes = {}
    for path in bundled_paths():
        asset_hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
        with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as connection:
            for entry_id, source, target, notes, provenance in connection.execute(
                    'SELECT id,source_term,target_term,notes,provenance FROM entries'):
                try:
                    metadata = json.loads(notes)
                except (ValueError, TypeError):
                    metadata = {}
                metadata = metadata if isinstance(metadata, dict) else {}
                kind = metadata.get('type', 'LEGACY_UNTYPED')
                types[kind] += 1
                source = normalize(source)
                copied = []
                if kind == 'full_segment' and source in diagnostic_sources:
                    copied.append('diagnostic_full_segment')
                if source in final_sources:
                    copied.append('frozen_A_long_exact_source')
                if normalize(target) in diagnostic_references:
                    copied.append('diagnostic_long_exact_reference')
                if copied:
                    exact_copies.append(dict(pack=path.name,entry_id=entry_id,
                        source_sha256=sha256(source.encode()).hexdigest(),checks=copied))
                hits = sorted(digest for digest in held_hashes if digest in (notes + provenance))
                if hits:
                    provenance_hits.append(dict(pack=path.name,entry_id=entry_id,held_source_sha256=hits))
    for name in ('knowledge-templates.json', 'automotive-slot-forms.json', 'technical-actions.json'):
        path = ROOT / 'assets/config' / name
        asset_hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
        data = json.loads(path.read_text('utf8'))
        records = data.get('templates', data.get('forms', data.get('actions', [])))
        for index, record in enumerate(records):
            source = normalize(record.get('source', ''))
            if source in final_sources or (len(source) >= 24 and source in diagnostic_sources):
                exact_copies.append(dict(asset=name,record=index,source_sha256=sha256(source.encode()).hexdigest(),
                                         checks=['long_exact_source_config']))
    result = dict(revision='AW0.81',scope='Bundled glossary/Knowledge entries, forms, templates, actions, manifest separation and embedded source SHA provenance.',
        limitations=['Does not prove absence of paraphrased leakage.',
                     'User-owned runtime TM/glossary and unpublished candidate stores are outside this packaged-asset audit.',
                     'Exact-source collision is an audit finding, not automatic proof of copying; independently evidenced legacy entries require separate review.'],
        frozen_A_semantic_acceptance_not_run=True,held_text_not_exposed=True,
        development_manifest_sha256=sha256(development.read_bytes()).hexdigest(),
        frozen_manifest_sha256=sha256(frozen.read_bytes()).hexdigest(),asset_sha256=asset_hashes,
        manifest_document_overlaps=overlaps,exact_copy_findings=exact_copies,
        held_source_provenance_findings=provenance_hits,entry_types=dict(types),
        automated_checks_clear=not(overlaps or exact_copies or provenance_hits))
    (QA / 'knowledge_leak_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print('manifest overlaps',len(overlaps),'exact findings',len(exact_copies),'provenance findings',len(provenance_hits))


if __name__ == '__main__':
    run()
