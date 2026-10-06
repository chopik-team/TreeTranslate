"""AW0.7.5 build-time EN/RU lexical expansion for the existing SQLite store."""
from __future__ import annotations

import bz2
import csv
from collections import defaultdict
from contextlib import closing
import hashlib
import heapq
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
import zipfile


WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[А-Яа-яЁё]+", re.UNICODE)
URL_RE = re.compile(r"(?:https?://|www\.|<[^>]+>|\{\{|\[\[)", re.I)
OPENRUSSIAN_FILES = {
    "nouns": "n", "verbs": "v", "adjectives": "adj", "others": "other",
}


def lexical_key(value: str, language: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\u0301", "").replace("'", "").replace("’", ""))
    value = " ".join(value.casefold().strip().split())
    return value.replace("ё", "е") if language == "ru" else value


def create_expansion_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE lexical_sources (
            id INTEGER PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            url TEXT NOT NULL, revision TEXT NOT NULL, license TEXT NOT NULL, attribution TEXT NOT NULL
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, language TEXT NOT NULL, key TEXT NOT NULL,
            lemma TEXT NOT NULL, pos TEXT NOT NULL, source_id INTEGER NOT NULL,
            payload TEXT NOT NULL, UNIQUE(language, key, pos, source_id, payload)
        );
        CREATE TABLE forms (
            language TEXT NOT NULL, key TEXT NOT NULL, article_id INTEGER NOT NULL,
            form TEXT NOT NULL, UNIQUE(language, key, article_id)
        );
        CREATE TABLE examples (
            id INTEGER PRIMARY KEY, language TEXT NOT NULL, sentence TEXT NOT NULL,
            source_id INTEGER NOT NULL, source_ref TEXT NOT NULL, contributor TEXT NOT NULL,
            rank INTEGER NOT NULL, UNIQUE(language, sentence)
        );
        CREATE TABLE example_terms (
            language TEXT NOT NULL, key TEXT NOT NULL, example_id INTEGER NOT NULL,
            UNIQUE(language, key, example_id)
        );
        CREATE INDEX article_lookup ON articles(language, key);
        CREATE INDEX form_lookup ON forms(language, key);
        CREATE INDEX example_lookup ON example_terms(language, key, example_id);
    """)


def add_source(connection, source_id, name, url, revision, license_id, attribution):
    cursor = connection.execute(
        "INSERT INTO lexical_sources(source_id,name,url,revision,license,attribution) VALUES(?,?,?,?,?,?)",
        (source_id, name, url, revision, license_id, attribution),
    )
    return cursor.lastrowid


def _wordnet_senses(archive: zipfile.ZipFile):
    pos_files = {"noun": "n", "verb": "v", "adj": "adj", "adv": "adv"}
    by_lemma = defaultdict(list)
    for filename, pos in pos_files.items():
        with archive.open(f"wordnet/data.{filename}") as raw:
            for binary in raw:
                line = binary.decode("utf-8").strip()
                if not line or line.startswith(" ") or " | " not in line:
                    continue
                data, gloss = line.split(" | ", 1)
                fields = data.split()
                try:
                    word_count = int(fields[3], 16)
                except (IndexError, ValueError):
                    continue
                lemmas = [fields[4 + 2 * index].replace("_", " ") for index in range(word_count)]
                parts = [part.strip() for part in re.split(r';\s*', gloss) if part.strip()]
                examples = [p[1:-1] for p in parts if len(p) > 2 and p.startswith('"') and p.endswith('"')]
                definitions = [p for p in parts if not (p.startswith('"') and p.endswith('"'))]
                for lemma in lemmas:
                    synonyms = [word for word in lemmas if lexical_key(word, "en") != lexical_key(lemma, "en")]
                    by_lemma[(lexical_key(lemma, "en"), lemma, pos)].append({
                        "definitions": definitions[:2], "synonyms": synonyms[:12], "examples": examples[:4],
                    })
    return by_lemma


def import_wordnet(connection: sqlite3.Connection, path: Path, source_id: int):
    article_count = sense_count = embedded_examples = 0
    with zipfile.ZipFile(path) as archive:
        by_lemma = _wordnet_senses(archive)
        exception_forms = defaultdict(set)
        for filename, pos in (("noun", "n"), ("verb", "v"), ("adj", "adj"), ("adv", "adv")):
            with archive.open(f"wordnet/{filename}.exc") as raw:
                for line in raw:
                    fields = line.decode("utf-8").strip().split()
                    if fields:
                        for lemma in fields[1:]:
                            exception_forms[(lexical_key(lemma.replace('_', ' '), 'en'), pos)].add(fields[0].replace('_', ' '))
        for (key, lemma, pos), senses in by_lemma.items():
            payload = json.dumps({"headword": lemma, "pos": [pos], "senses": senses,
                                  "source": "Princeton WordNet 3.0"}, ensure_ascii=False, separators=(",", ":"))
            article_id = connection.execute(
                "INSERT INTO articles(language,key,lemma,pos,source_id,payload) VALUES('en',?,?,?,?,?)",
                (key, lemma, pos, source_id, payload)).lastrowid
            forms = {lemma, *exception_forms.get((key, pos), ())}
            connection.executemany("INSERT OR IGNORE INTO forms VALUES('en',?,?,?)",
                                   ((lexical_key(form, "en"), article_id, form) for form in forms))
            article_count += 1
            sense_count += len(senses)
            embedded_examples += sum(len(sense["examples"]) for sense in senses)
    return {"articles": article_count, "senses": sense_count, "embedded_examples": embedded_examples}


def _split_values(value):
    if isinstance(value, list):
        value = ",".join(part for part in value if part)
    return [part.strip() for part in re.split(r"[,/]", value or "") if part.strip()]


def import_openrussian(connection: sqlite3.Connection, directory: Path, source_id: int):
    articles = senses = form_count = rejected = duplicates = 0
    for stem, pos in OPENRUSSIAN_FILES.items():
        path = directory / f"openrussian-{stem}.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            for row in reader:
                lemma = (row.get("bare") or "").strip()
                equivalents = (row.get("translations_en") or "").strip()
                if not lemma or not WORD_RE.fullmatch(lemma) or not equivalents:
                    rejected += 1
                    continue
                sense_rows = []
                for group in equivalents.split(";"):
                    values = _split_values(group)
                    if values:
                        sense_rows.append({"definitions": values, "translations": values})
                if not sense_rows:
                    rejected += 1
                    continue
                grammar = {name: row[name] for name in ("gender", "animate", "aspect", "partner") if row.get(name)}
                payload = json.dumps({"headword": lemma, "accented": row.get("accented") or lemma,
                                      "pos": [pos], "senses": sense_rows, "grammar": grammar,
                                      "source": "OpenRussian"}, ensure_ascii=False, separators=(",", ":"))
                key = lexical_key(lemma, "ru")
                before_insert = connection.total_changes
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO articles(language,key,lemma,pos,source_id,payload) VALUES('ru',?,?,?,?,?)",
                    (key, lemma, pos, source_id, payload))
                if connection.total_changes == before_insert:
                    duplicates += 1
                    continue
                article_id = cursor.lastrowid
                forms = {lemma, row.get("accented") or ""}
                ignored = {"bare", "accented", "translations_en", "translations_de", "gender", "animate",
                           "indeclinable", "sg_only", "pl_only", "aspect", "partner"}
                for name, value in row.items():
                    if name not in ignored and value:
                        forms.update(_split_values(value))
                before = connection.total_changes
                connection.executemany("INSERT OR IGNORE INTO forms VALUES('ru',?,?,?)",
                                       ((lexical_key(form, "ru"), article_id, form) for form in forms if lexical_key(form, "ru")))
                form_count += connection.total_changes - before
                articles += 1
                senses += len(sense_rows)
    return {"articles": articles, "senses": senses, "forms": form_count,
            "rejected": rejected, "duplicates": duplicates}


def _quality(sentence: str) -> int | None:
    if URL_RE.search(sentence) or "\ufffd" in sentence or not 12 <= len(sentence) <= 220:
        return None
    words = WORD_RE.findall(sentence)
    if not 3 <= len(words) <= 30:
        return None
    # Higher is better: complete, readable sentences near 70 characters rank first.
    return 1000 - abs(len(sentence) - 70) * 3 - max(0, len(words) - 18) * 10 + (40 if sentence[-1:] in ".!?…" else 0)


def import_tatoeba(connection: sqlite3.Connection, path: Path, language: str, source_id: int, limit=3):
    form_rows = connection.execute("SELECT f.key, a.key FROM forms f JOIN articles a ON a.id=f.article_id WHERE f.language=?", (language,))
    forms = defaultdict(set)
    for form_key, lemma_key in form_rows:
        if " " not in form_key:
            forms[form_key].add(lemma_key)
    candidates = defaultdict(list)
    rejected = duplicates = scanned = 0
    seen_sentences = set()
    with bz2.open(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            scanned += 1
            if len(row) < 4:
                rejected += 1
                continue
            sentence_id, _lang, sentence, contributor = row[:4]
            score = _quality(sentence)
            normalized_sentence = " ".join(sentence.casefold().split())
            if score is None or normalized_sentence in seen_sentences:
                rejected += score is None
                duplicates += score is not None
                continue
            seen_sentences.add(normalized_sentence)
            lemma_keys = set()
            for token in WORD_RE.findall(sentence):
                lemma_keys.update(forms.get(lexical_key(token, language), ()))
            if not lemma_keys:
                continue
            record = (score, int(sentence_id), sentence, contributor or "anonymous")
            for lemma_key in lemma_keys:
                heap = candidates[lemma_key]
                if len(heap) < limit:
                    heapq.heappush(heap, record)
                elif record[:2] > heap[0][:2]:
                    heapq.heapreplace(heap, record)
    inserted = links = 0
    sentence_ids = {}
    for lemma_key, records in candidates.items():
        for score, sentence_id, sentence, contributor in sorted(records, reverse=True):
            identity = (language, sentence)
            example_id = sentence_ids.get(identity)
            if example_id is None:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO examples(language,sentence,source_id,source_ref,contributor,rank) VALUES(?,?,?,?,?,?)",
                    (language, sentence, source_id, str(sentence_id), contributor, score))
                example_id = cursor.lastrowid or connection.execute(
                    "SELECT id FROM examples WHERE language=? AND sentence=?", identity).fetchone()[0]
                sentence_ids[identity] = example_id
                inserted += bool(cursor.lastrowid)
            before = connection.total_changes
            connection.execute("INSERT OR IGNORE INTO example_terms VALUES(?,?,?)", (language, lemma_key, example_id))
            links += connection.total_changes - before
    return {"scanned": scanned, "examples": inserted, "links": links, "rejected": rejected, "duplicates": duplicates}


def expanded_statistics(connection):
    return {
        "articles": dict(connection.execute("SELECT language,count(*) FROM articles GROUP BY language")),
        "lemmas": dict(connection.execute("SELECT language,count(DISTINCT key) FROM articles GROUP BY language")),
        "forms": dict(connection.execute("SELECT language,count(*) FROM forms GROUP BY language")),
        "examples": dict(connection.execute("SELECT language,count(*) FROM examples GROUP BY language")),
        "example_links": dict(connection.execute("SELECT language,count(*) FROM example_terms GROUP BY language")),
    }


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
