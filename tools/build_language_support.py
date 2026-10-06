"""Generate presentation metadata from the existing audit and read-only bundled DBs."""
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config.constants import APP_VERSION
from app.engine.languages import RELEASE_LANGUAGE_CODES


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def resource_counts(root=ROOT):
    counts = {code: dict.fromkeys(("technical_entries", "dictionary_entries",
                                  "bilingual_entries", "usage_examples"))
              for code in sorted(RELEASE_LANGUAGE_CODES)}
    db = root / "vendor/lexicon/lexicon.sqlite3"
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as con:
        for table, language, metric in (("articles", "language", "dictionary_entries"),
                                        ("entries", "source", "bilingual_entries"),
                                        ("examples", "language", "usage_examples")):
            for code, count in con.execute(f"SELECT {language}, COUNT(*) FROM {table} GROUP BY {language}"):
                if code in counts:
                    counts[code][metric] = count
    for pack in read_json(root / "assets/knowledge/manifest.json")["packs"]:
        db = root / "assets/knowledge" / pack["file"]
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as con:
            count = con.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            assert count == pack["entries"], pack["pack_id"]
        code = pack["source_language"]
        counts[code]["technical_entries"] = (counts[code]["technical_entries"] or 0) + count
    return counts


def build_snapshot(root=ROOT):
    audit = read_json(root / "docs/qa/aw076/language-matrix.json")
    counts = resource_counts(root)
    by_code = {row["code"]: row for row in audit["languages"]}
    languages = []
    for code in audit["release_language_codes"]:
        row = by_code[code]
        languages.append({"code": code, "labels": row["ui_labels"], "status": row["status"],
                          "documents": row["documents"], "auto_detect": row["auto_detect"]["ok"],
                          "counts": counts[code]})
    assert {row["code"] for row in languages} == RELEASE_LANGUAGE_CODES
    technical = {}
    for pack in read_json(root / "docs/qa/aw074/packs.json")["packs"]:
        code = "zh" if "-zh-ru-" in pack["pack_id"] else "ru"
        technical.setdefault(code, {"technical_entries": 0})
        technical[code]["technical_entries"] += pack["counts"]["accepted_entries"]
    lexical = read_json(root / "docs/qa/aw075/lexical-benchmark.json")
    history = [
        {"version": "AW 0.7.4", "source": "docs/qa/aw074/packs.json", "counts": technical},
        {"version": "AW 0.7.5", "source": "docs/qa/aw075/lexical-benchmark.json",
         "counts": {code: {"dictionary_entries": lexical["articles"][code],
                           "usage_examples": lexical["examples"][code]} for code in ("en", "ru")}},
    ]
    existing = root / "assets/language-support.json"
    if existing.is_file():
        prior = read_json(existing)
        history = prior["history"]
        if prior["version"] != APP_VERSION:
            history = [*history, {"version": prior["version"],
                                  "source": "assets/language-support.json (previous snapshot)",
                                  "counts": {r["code"]: r["counts"] for r in prior["languages"]}}]
    return {"schema": 1, "version": APP_VERSION,
            "capability_source": "docs/qa/aw076/language-matrix.json",
            "languages": languages, "history": history,
            "routing_note": "Маршрут зависит от пары и профиля.\n" + "\n".join(
                line.removeprefix("- ") for line in
                (root / "docs/LANGUAGE_SUPPORT.md").read_text(encoding="utf-8")
                .split("## Маршрутизация\n", 1)[1].split("\n## ", 1)[0].strip().splitlines()
                if line.startswith("- "))}



if __name__ == "__main__":
    output = ROOT / "assets/language-support.json"
    output.write_text(json.dumps(build_snapshot(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
