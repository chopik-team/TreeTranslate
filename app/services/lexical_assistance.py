"""Local dictionary and input assistance. No translation model or network imports."""
from __future__ import annotations

from bisect import bisect_left
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

from app.config.paths import PROJECT_ROOT
from app.engine.languages import language_code


def lookup_key(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\u0301", "")).casefold().strip()


def assist_language(value: str, token: str) -> str:
    code = language_code(value)
    if code != "auto":
        return code
    # For unfinished words, script is more useful than sentence language detection.
    # Ambiguous Latin input defaults to English until the actual translation resolves it.
    if re.fullmatch(r"[а-яёА-ЯЁ\u0301]+", token):
        return "ru"
    if re.fullmatch(r"[a-zA-Z'’]+", token):
        return "en"
    return "auto"


@dataclass(frozen=True)
class Suggestion:
    word: str
    kind: str  # completion / spelling


@dataclass(frozen=True)
class Reference:
    word: str
    source: str
    target: str
    entries: tuple[dict, ...] = ()
    usage: dict | None = None
    notice: str = ""


class LexicalAssistance:
    def __init__(self, database: Path | None = None, usage_path: Path | None = None):
        self.database = database or PROJECT_ROOT / "vendor" / "lexicon" / "lexicon.sqlite3"
        self.usage_path = usage_path or PROJECT_ROOT / "assets" / "language" / "usage.json"

    @lru_cache(maxsize=1)
    def _usage(self):
        try:
            return json.loads(self.usage_path.read_text(encoding="utf-8"))["entries"]
        except (OSError, ValueError, KeyError):
            return []

    def reference(self, word: str, source: str, target: str) -> Reference:
        source, target = assist_language(source, word), language_code(target)
        word = word.strip()
        if not word or len(word) > 160:
            return Reference(word, source, target)
        usage = next((entry for entry in self._usage() if entry["source"] == source
                      and entry["target"] == target and lookup_key(word) in entry["words"]), None)
        entries = ()
        notice = ""
        if (source, target) in {("en", "ru"), ("ru", "en")}:
            try:
                with closing(sqlite3.connect(self.database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
                    rows = connection.execute("SELECT payload FROM entries WHERE source=? AND target=? AND key=? LIMIT 12",
                                              (source, target, lookup_key(word))).fetchall()
                entries = tuple(json.loads(row[0]) for row in rows)
            except (sqlite3.Error, OSError, ValueError):
                notice = "Локальный словарь недоступен."
            if not entries and not usage and not notice:
                notice = "В локальном словаре нет этой формы. Попробуйте начальную форму слова."
        elif not usage:
            notice = "Словарные статьи пока доступны для английского и русского."
        return Reference(word, source, target, entries, usage, notice)

    @staticmethod
    @lru_cache(maxsize=2)
    def _speller(language):
        from spellchecker import SpellChecker
        spell = SpellChecker(language=language, distance=1)
        return spell, sorted(word for word in spell.word_frequency.keys() if word.isalpha())

    def suggest(self, word: str, language: str) -> tuple[Suggestion, ...]:
        language = assist_language(language, word)
        if language not in {"en", "ru", "de", "fr", "es"} or not 3 <= len(word) <= 32 or not word.isalpha():
            return ()
        # Do not reinterpret a different script under an explicitly selected language.
        if (language == "ru") != bool(re.fullmatch(r"[а-яёА-ЯЁ]+", word)):
            return ()
        try:
            spell, words = self._speller(language)
        except (ImportError, ValueError, OSError):
            return ()
        key = word.lower()
        frequency = spell.word_frequency
        if frequency[key] >= 1000:
            return ()  # ordinary complete word; keep Enter available for a newline
        start, end = bisect_left(words, key), bisect_left(words, key + "\uffff")
        completions = sorted((w for w in words[start:end] if w != key),
                             key=lambda w: (-frequency[w], len(w), w))[:3]
        corrections = sorted((spell.candidates(key) or set()) - {key},
                             key=lambda w: (-frequency[w], w))
        # A frequent completion wins for fragments such as Gam; corrections win otherwise.
        candidates = [(w, "completion") for w in completions] + [(w, "spelling") for w in corrections]
        def rank(item):
            value, kind = item
            doubled = any(key[:i] + key[i] + key[i:] == value for i in range(len(key)))
            priority = 0 if doubled else 1 if kind == "completion" and frequency[value] >= 1000 else 2 if kind == "spelling" else 3
            return priority, -frequency[value], value
        candidates.sort(key=rank)
        result, seen = [], set()
        for value, kind in candidates:
            if value in seen:
                continue
            seen.add(value)
            value = value.upper() if word.isupper() else value.capitalize() if word[0].isupper() else value
            result.append(Suggestion(value, kind))
        return tuple(result[:5])
