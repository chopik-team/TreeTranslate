"""Synthetic local TM benchmark. Never populates the user's memory."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
from time import perf_counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.translation_memory.engine import TranslationMemoryEngine
from app.translation_memory.maintenance import integrity


def timed(call, repeats=7):
    values = []
    for _ in range(repeats):
        start = perf_counter()
        call()
        values.append((perf_counter()-start)*1000)
    values.sort()
    return {'median_ms': statistics.median(values), 'max_ms': max(values), 'samples': repeats}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[10,100,1000,10000,100000,500000])
    parser.add_argument('--output', type=Path, default=Path('docs/qa/aw07/benchmark.json'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix='tm-benchmark-') as directory:
        path = Path(directory)/'memory.db'
        tm = TranslationMemoryEngine(path)
        previous = 0
        for size in sorted(set(args.sizes)):
            started = perf_counter()
            tm.repository.insert_many(dict(source_text=f'Save item {i} before restart.',
                target_text=f'Сохраните элемент {i} перед запуском.', source_language='en', target_language='ru',
                status='CONFIRMED',origin='synthetic-benchmark') for i in range(previous,size))
            insertion = perf_counter()-started
            def cold(text):
                tm.cache.clear()
                return tm.lookup(text,'en','ru')
            source = f'Save item {size-1} before restart.'
            def startup():
                memory = TranslationMemoryEngine(path)
                assert memory.lookup(source,'en','ru').reusable
            row = dict(units=size, inserted=size-previous, insert_seconds=insertion,
                       startup=timed(startup), exact=timed(lambda:cold(source)),
                       normalized=timed(lambda:cold(source.replace(' ', '  '))),
                       fuzzy=timed(lambda:cold('Save item 0 before restarting.')),
                       hot=timed(lambda:tm.lookup(source,'en','ru')))
            texts = [f'Save item {i} before restart.' for i in range(min(size,1000))]
            def batch():
                tm.cache.clear()
                assert all(m and m.reusable for m in tm.lookup_many(texts,'en','ru'))
            row['batch_size'] = len(texts)
            row['batch'] = timed(batch,3)
            row['database_bytes'] = path.stat().st_size
            row['integrity'] = integrity(tm.db)
            with tm.db.connect() as con:
                row['query_plans'] = {column:[tuple(r) for r in con.execute(
                    f'EXPLAIN QUERY PLAN SELECT * FROM units WHERE source_language=? AND target_language=? AND {column}=?',
                    ('en','ru','hash'))] for column in ('source_hash','normalized_hash')}
            rows.append(row)
            args.output.write_text(json.dumps(rows,indent=2,ensure_ascii=False),'utf-8')
            print(f'{size}: insert={insertion:.2f}s exact={row["exact"]["median_ms"]:.2f}ms batch={row["batch"]["median_ms"]:.2f}ms',flush=True)
            previous = size


if __name__ == '__main__':
    main()
