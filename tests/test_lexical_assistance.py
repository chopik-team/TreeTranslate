import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

from app.services.lexical_assistance import LexicalAssistance, assist_language
from tools.prepare_lexicon import import_tei, prepare


def test_freedict_import_preserves_distinct_senses_and_stress(tmp_path):
    data = b'''<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/><text><entry>
    <form><orth>bank</orth><pron>/bank/</pron></form><gramGrp><pos>n</pos></gramGrp>
    <sense><cit type="trans"><quote>financial</quote></cit><sense><def>money</def></sense></sense>
    <sense><cit type="trans"><quote>shore</quote></cit><sense><def>river</def></sense></sense>
    </entry></text></TEI>'''
    database = tmp_path / "dictionary.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE entries (source, target, key, payload)")
    count, header = import_tei(connection, data, "en", "ru")
    connection.commit()
    connection.close()
    assert count == 1
    entry = LexicalAssistance(database).reference("BANK", "en", "ru").entries[0]
    assert entry["senses"][0]["definitions"] == ["money"]
    assert entry["senses"][1]["translations"] == ["shore"]


def test_preparation_requires_explicit_network_permission(tmp_path):
    with patch("tools.prepare_lexicon.urlopen", side_effect=AssertionError("network called")):
        with pytest.raises(FileNotFoundError):
            prepare(tmp_path / "source", tmp_path / "output" / "lexicon.db")
    assert not (tmp_path / "output" / "lexicon.db").exists()


def test_missing_dictionary_keeps_real_usage_and_never_downloads(tmp_path):
    with patch("socket.socket.connect", side_effect=AssertionError("network called")):
        service = LexicalAssistance(tmp_path / "missing.db")
        hi = service.reference("hi", "en", "ru")
        assert hi.usage["variants"][0][0] == "привет"
        assert not hi.entries
        assert hi.notice == "Локальный словарь недоступен."
        assert service.reference("xyz", "en", "ru").usage is None
        assert not (tmp_path / "missing.db").exists()


@pytest.mark.parametrize("word,language,expected", [
    ("Gam", "en", "Game"), ("helo", "en", "hello"), ("recieve", "en", "receive"),
    ("превет", "ru", "привет"), ("прив", "ru", "привет"), ("ПРЕВЕТ", "ru", "ПРИВЕТ"),
])
def test_real_spelling_and_completions(word, language, expected):
    with patch("socket.socket.connect", side_effect=AssertionError("network called")):
        assert LexicalAssistance().suggest(word, language)[0].word == expected


@pytest.mark.parametrize("word,language", [("hello", "en"), ("hi", "en"), ("你好", "zh"),
                                         ("https://host", "en"), ("привет", "en"), ("Gam", "ru"),
                                         ("a" * 33, "en")])
def test_complete_words_unsupported_scripts_and_paths_have_no_suggestion(word, language):
    assert LexicalAssistance().suggest(word, language) == ()


def test_auto_script_and_explicit_language():
    assert assist_language("auto", "Gam") == "en"
    assert assist_language("auto", "прив") == "ru"
    assert assist_language("de", "Gam") == "de"
    assert assist_language("auto", "你好") == "auto"


@pytest.mark.integration
def test_installed_bilingual_dictionary_is_real_and_indexed():
    service = LexicalAssistance()
    if not service.database.exists():
        pytest.skip("FreeDict development artifacts not installed")
    manifest = json.loads((service.database.parent / "manifest.json").read_text(encoding="utf-8"))
    assert sum(source["entries"] for source in manifest["sources"]) == 104781
    with patch("socket.socket.connect", side_effect=AssertionError("network called")):
        for word, source, target in (("bank", "en", "ru"), ("игра", "ru", "en"), ("translation", "en", "ru")):
            assert service.reference(word, source, target).entries
        assert not service.reference("несуществующеесловоxyz", "ru", "en").entries
        assert service.reference("приве́т", "ru", "en").entries
