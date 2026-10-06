"""Collect bounded source evidence, without reading evaluation references."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'


def run(authored_name='aw081-semantic-components.txt', destination_name='profile_development_evidence.json'):
    authored = ROOT / 'assets/knowledge' / authored_name
    manifest = ROOT / 'qa/aw088/development_manifest.json'
    allowed = {d['member']: d['sha256'] for d in json.loads(manifest.read_text('utf8'))['documents']}
    held = json.loads((QA / 'final_holdout_manifest.json').read_text('utf8'))
    assert not set(allowed).intersection(d['member'] for d in held['documents'])
    rows = []
    for line in authored.read_text('utf8').splitlines():
        if not line or line.startswith('#'):
            continue
        source, nom, gen, acc, gender, domain = line.split('|')
        rows.append(dict(source=source, target=nom, genitive=gen, accusative=acc,
                         gender=gender, subdomain=domain, status='REVIEW_REQUIRED'))
    operators = ['使用', '顺时针', '逆时针', '来松开', '以松开', '来拧紧', '以拧紧', '然后', '大灯', '转向信号灯', '飞轮']
    terms = {r['source'] for r in rows}.union(operators)
    counts, samples = Counter(), defaultdict(list)
    with sqlite3.connect(ROOT / 'qa/aw088/native_corpus.db') as connection:
        for member, digest, _, payload in connection.execute('SELECT * FROM documents'):
            if member not in allowed:
                continue
            assert digest == allowed[member]
            for offset, text in enumerate(json.loads(payload)['lines']):
                for source in terms:
                    if source not in text:
                        continue
                    counts[source] += text.count(source)
                    # Distinct contexts make repeated navigation labels apparent.
                    if len(samples[source]) < 8 and not any(s['context'] == text for s in samples[source]):
                        samples[source].append(dict(member=member, sha256=digest, offset=offset, context=text))
    for row in rows:
        row.update(frequency=counts[row['source']], samples=samples[row['source']])
    result = dict(revision='AW0.81', references_not_used=True,
                  authored_sha256=sha256(authored.read_bytes()).hexdigest(),
                  development_manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),
                  rows=rows, operators=[dict(source=s, frequency=counts[s], samples=samples[s]) for s in operators])
    destination = QA / destination_name
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({r['source']: r['frequency'] for r in rows}, ensure_ascii=False))


if __name__ == '__main__':
    run(*sys.argv[1:])
