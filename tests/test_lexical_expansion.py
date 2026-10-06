import sqlite3
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.lexical_assistance import LexicalAssistance
from tools.lexical_expansion import _quality


EN_WORDS = ("hello", "person", "house", "water", "work", "car", "engine", "connector", "steel", "radiator")
RU_WORDS = ("привет", "человек", "дом", "вода", "работа", "машина", "двигатель", "разъём", "сталь", "радиатор")
RU_FORMS = {"двигателя": "двигатель", "машины": "машина", "людям": "человек", "работает": "работать"}


@pytest.fixture(scope="module")
def lexicon():
    service = LexicalAssistance()
    if not service.database.exists():
        pytest.skip("Expanded lexical database is not installed")
    with sqlite3.connect(service.database) as connection:
        if connection.execute("PRAGMA user_version").fetchone()[0] < 2:
            pytest.skip("AW0.7.5 lexical schema is not installed")
    return service


@pytest.mark.parametrize("word", EN_WORDS)
def test_english_qa_words_have_real_articles_and_examples(lexicon, word):
    reference = lexicon.reference(word, "en", "ru")
    assert reference.entries
    assert any(entry.get("source") == "Princeton WordNet 3.0" for entry in reference.entries)
    assert reference.examples


@pytest.mark.parametrize("word", RU_WORDS)
def test_russian_qa_words_have_real_articles_and_examples(lexicon, word):
    reference = lexicon.reference(word, "ru", "en")
    assert reference.entries
    assert any(entry.get("source") == "OpenRussian" for entry in reference.entries)
    assert reference.examples


@pytest.mark.parametrize("form,lemma", RU_FORMS.items())
def test_russian_inflected_form_resolves_without_stemming(lexicon, form, lemma):
    reference = lexicon.reference(form, "ru", "en")
    assert any(entry.get("headword") == lemma for entry in reference.entries)
    assert reference.examples


@pytest.mark.parametrize("word", ("bank", "current", "driver"))
def test_ambiguous_english_words_preserve_multiple_senses(lexicon, word):
    reference = lexicon.reference(word, "en", "ru")
    wordnet = [entry for entry in reference.entries if entry.get("source") == "Princeton WordNet 3.0"]
    assert sum(len(entry["senses"]) for entry in wordnet) >= 2


def test_yo_and_e_are_lookup_variants_but_source_spelling_is_preserved(lexicon):
    with sqlite3.connect(lexicon.database) as connection:
        row = connection.execute("SELECT lemma FROM articles WHERE language='ru' AND lemma LIKE '%ё%' LIMIT 1").fetchone()
    assert row
    original = row[0]
    variant = original.replace("ё", "е")
    result = lexicon.reference(variant, "ru", "en")
    assert any(entry["headword"] == original for entry in result.entries)


def test_expanded_lookup_is_offline_indexed_and_lazy(lexicon):
    with patch("socket.socket.connect", side_effect=AssertionError("network called")):
        assert lexicon.reference("engine", "en", "ru").entries
        assert lexicon.reference("двигателя", "ru", "en").entries
    with sqlite3.connect(lexicon.database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        indexes = {row[1] for row in connection.execute("PRAGMA index_list('forms')")}
        assert "form_lookup" in indexes
        assert connection.execute("SELECT count(*) FROM articles WHERE language='en'").fetchone()[0] > 100_000
        assert connection.execute("SELECT count(*) FROM articles WHERE language='ru'").fetchone()[0] > 40_000
        assert connection.execute("SELECT count(*) FROM examples WHERE language='en'").fetchone()[0] > 50_000
        assert connection.execute("SELECT count(*) FROM examples WHERE language='ru'").fetchone()[0] > 40_000


def test_raw_corpora_are_not_runtime_assets():
    from app.config.paths import ASSETS_DIR
    forbidden = {".csv", ".bz2", ".zip", ".xml.bz2"}
    assert not [path for path in ASSETS_DIR.rglob("*") if path.is_file() and any(str(path).endswith(ext) for ext in forbidden)]


def test_manifest_hashes_provenance_and_license_notices(lexicon):
    manifest = json.loads((lexicon.database.parent / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == 2
    assert hashlib.sha256(lexicon.database.read_bytes()).hexdigest() == manifest["sha256"]
    expansion = manifest["expansion"]
    assert set(expansion["statistics"]["lemmas"]) == {"en", "ru"}
    source_dir = Path("build/lexical-sources/aw075")
    for name, record in expansion["source_files"].items():
        assert record["url"].startswith("https://")
        assert record["revision"] and record["license"] and record["attribution"]
        assert record["acquisition_date"] == "2026-09-27"
        path = source_dir / name
        if path.exists():
            assert path.stat().st_size == record["bytes"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    root = Path("vendor/licenses")
    assert (root / "WordNet/LICENSE.txt").is_file()
    assert (root / "OpenRussian/CC-BY-SA-4.0.txt").is_file()
    assert (root / "Tatoeba/CC-BY-2.0-FR.html").is_file()


def test_example_zero_one_many_unicode_and_quality_filter(lexicon):
    assert not lexicon.reference("notawordxyzaw075", "en", "ru").examples
    with sqlite3.connect(lexicon.database) as connection:
        one = connection.execute("""
            SELECT key FROM example_terms WHERE language='en'
            GROUP BY key HAVING count(*)=1 LIMIT 1
        """).fetchone()
    assert one and len(lexicon.reference(one[0], "en", "ru").examples) == 1
    assert len(lexicon.reference("engine", "en", "ru").examples) >= 2
    assert lexicon.reference("двигатель", "ru", "en").examples
    assert _quality("Двигатель работает ровно и тихо.") is not None
    assert _quality("Read https://example.org for documentation.") is None
    assert _quality("word " * 100) is None
