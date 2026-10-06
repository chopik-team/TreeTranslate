"""Gather development-only evidence for independently authored action concepts."""
import json
import sqlite3
from pathlib import Path
from collections import Counter, defaultdict
from hashlib import sha256
ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw081'

PROPOSALS = {
    'INCREASE': ('Увеличьте','Увеличение', ('增大','提高')),
    'DECREASE': ('Уменьшите','Уменьшение', ('降低','减小','减少')),
    'LOCK': ('Заблокируйте','Блокировка', ('锁定','锁止')),
    'UNLOCK': ('Разблокируйте','Разблокировка', ('解锁','解除锁止')),
    'ENABLE': ('Активируйте','Активация', ('使能','启用')),
    'DISABLE': ('Деактивируйте','Деактивация', ('禁用','停用')),
    'APPLY_POWER': ('Подайте питание','Подача питания', ('施加电源','接通电源','通电')),
    'REMOVE_POWER': ('Отключите питание','Отключение питания', ('切断电源','断电')),
    'PUSH': ('Вставьте','Вставление', ('推入',)),
    'CLOSE': ('Замкните','Замыкание', ('关上','闭合')),
}


def run():
    manifest_path = ROOT / 'qa/aw088/development_manifest.json'
    development = json.loads(manifest_path.read_text('utf8'))
    allowed = {d['member']: d['sha256'] for d in development['documents']}
    terms = {surface for _,_,surfaces in PROPOSALS.values() for surface in surfaces}
    counts, samples = Counter(), defaultdict(list)
    with sqlite3.connect(ROOT/'qa/aw088/native_corpus.db') as connection:
        for member, digest, _, raw in connection.execute('SELECT * FROM documents'):
            if member not in allowed:
                continue
            assert digest == allowed[member]
            for offset, line in enumerate(json.loads(raw)['lines']):
                for term in terms:
                    if term not in line:
                        continue
                    counts[term] += line.count(term)
                    if len(samples[term]) < 6:
                        samples[term].append(dict(member=member, sha256=digest, offset=offset, context=line))
    rows = [dict(concept=concept, imperative=imperative, heading=heading,
                surfaces=[dict(source=t, frequency=counts[t], samples=samples[t]) for t in terms],
                review_state='REVIEW_REQUIRED')
            for concept,(imperative,heading,terms) in PROPOSALS.items()]
    (QA/'action_development_evidence.json').write_text(json.dumps(dict(rows=rows,
        development_manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(),
        references_not_used=True, reviewer='Codex'), ensure_ascii=False, indent=2), 'utf8')
    print(dict(counts), flush=True)


if __name__ == '__main__':
    run()
