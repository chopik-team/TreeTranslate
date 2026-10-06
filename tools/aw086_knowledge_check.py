"""Exercise every authored addition through the production glossary component."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.engine.types import TranslationRequest
from app.glossary.bundled import bundled_paths
from app.glossary.engine import GlossaryEngine


def run():
    with (ROOT / 'assets/knowledge/aw086-automotive-reviewed.tsv').open(encoding='utf-8', newline='') as stream:
        authored = list(csv.DictReader(stream, delimiter='\t'))
    rows = []
    with tempfile.TemporaryDirectory(prefix='aw086-knowledge-check-') as temporary:
        glossary = GlossaryEngine(Path(temporary) / 'isolated-user.db', builtin_paths=bundled_paths())
        started = perf_counter()
        for row in authored:
            request = TranslationRequest(row['source'], 'zh', 'ru', domain='automotive')
            result = glossary.full_segment(request)
            rows.append(dict(source=row['source'], expected=row['target'],
                             actual=result.translated_text if result else None,
                             passed=bool(result and result.translated_text == row['target'])))
        elapsed = perf_counter() - started
        forms = json.loads((ROOT / 'assets/config/automotive-slot-forms.json').read_text('utf-8'))['forms']
        slots = []
        for form in forms:
            matches = glossary.lookup(form['source'], 'zh', 'ru', 'automotive')
            for prefix, case in [('Проверьте ', 'accusative'), ('С помощью ', 'genitive')]:
                source = prefix + form['base']
                expected = prefix + form[case]
                actual = glossary.grammatical_phrases(source, matches)
                slots.append(dict(source=source, actual=actual, expected=expected, passed=actual == expected))
    result = dict(authored_rows=len(rows), direct_passed=sum(r['passed'] for r in rows),
                  slot_checks=len(slots), slot_passed=sum(r['passed'] for r in slots),
                  lookup_seconds=elapsed, timing_scope='Cold isolated glossary lookups; not document runtime benchmark',
                  direct=rows, slots=slots)
    (ROOT / 'qa/aw086/knowledge_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    assert all(r['passed'] for r in [*rows, *slots])
    print(json.dumps({key: value for key, value in result.items() if key not in ('direct', 'slots')}, ensure_ascii=False))


if __name__ == '__main__':
    run()
