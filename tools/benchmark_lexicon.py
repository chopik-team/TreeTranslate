"""Measure the installed AW0.7.5 lexical database without loading it into RAM."""
import argparse
import json
from pathlib import Path
import sqlite3
from statistics import median
import sys
from time import perf_counter

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.lexical_assistance import LexicalAssistance


def run(database: Path):
    service = LexicalAssistance(database)
    process = psutil.Process()
    before = process.memory_info().rss
    words = (("hello", "en", "ru"), ("bank", "en", "ru"), ("engine", "en", "ru"),
             ("привет", "ru", "en"), ("двигателя", "ru", "en"), ("работает", "ru", "en"))
    cold = []
    for word, source, target in words:
        started = perf_counter(); service.reference(word, source, target); cold.append((perf_counter() - started) * 1000)
    warm = []
    for _ in range(20):
        for word, source, target in words:
            started = perf_counter(); service.reference(word, source, target); warm.append((perf_counter() - started) * 1000)
    with sqlite3.connect(database) as connection:
        counts = {
            table: dict(connection.execute(f"SELECT language,count(*) FROM {table} GROUP BY language"))
            for table in ("articles", "forms", "examples")
        }
        counts["senses"] = {}
        for language in ("en", "ru"):
            counts["senses"][language] = sum(len(json.loads(row[0])["senses"]) for row in connection.execute(
                "SELECT payload FROM articles WHERE language=?", (language,)))
    return {"database_bytes": database.stat().st_size, **counts,
            "cold_lookup_ms_median": median(cold), "cold_lookup_ms_max": max(cold),
            "warm_lookup_ms_median": median(warm), "warm_lookup_ms_max": max(warm),
            "rss_delta_bytes": max(0, process.memory_info().rss - before),
            "peak_rss_bytes": process.memory_info().peak_wset if hasattr(process.memory_info(), "peak_wset") else process.memory_info().rss}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("vendor/lexicon/lexicon.sqlite3"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.database)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
