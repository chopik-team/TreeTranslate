"""Reject broken decoder artifacts and restore casing of explicit software literals."""
import re
from collections import Counter
import unicodedata

from app.engine.errors import TranslationError

_MODEL_TOKEN = re.compile(r'<unk>|</?s>|__[a-z]{2,3}__|\ufffd')
_FILE = re.compile(r'(?<![A-Za-z0-9_.])[A-Za-z0-9_-]+\.(?:json|xml|yaml|yml|ini|cfg|txt|csv|docx|pdf|py|exe|dll)(?![A-Za-z0-9_.])', re.I)
_PYTHON_COMMAND = re.compile(r'(?<![A-Za-z0-9_])python(?=\s+[\w.-]+\.py\b)')


def checked_output(source, output):
    if (source.strip() and not output.strip()) or any(
        token.group() not in source for token in _MODEL_TOKEN.finditer(output)
    ) or any(0xD800 <= ord(c) <= 0xDFFF or (ord(c)<32 and c not in '\n\r\t') for c in output):
        raise TranslationError()
    # Dates/identifiers such as 2026-09-28 and ITM-20 are not negative quantities.
    def negative_values(text):
        text = unicodedata.normalize('NFKC', text)
        text = re.sub(r'(?i)(?:\bminus\b|\bnegative\b|\bминус\b|\bmoins\b|\bmenos\b|负|マイナス)\s*(?=\d)', '-', text)
        return Counter(value.replace(',', '.') for value in re.findall(
            r'(?:−|(?<![0-9A-Za-z_])-)\s*(\d+(?:[.,]\d+)?)', text))
    required = negative_values(source)
    actual = negative_values(output)
    if any(actual[value] < count for value, count in required.items()):
        raise TranslationError('Перевод изменил знак отрицательного числа. Проверьте исходный фрагмент.')
    if required:
        def numbers(text):
            text = unicodedata.normalize('NFKC', text)
            text = re.sub(r'(?<=\d)[ ,\u00a0\u202f](?=\d{3}(?:\D|$))', '', text)
            return Counter(x.replace(',', '.') for x in re.findall(r'\d+(?:[.,]\d+)?', text))
        if numbers(source) != numbers(output):
            raise TranslationError('Перевод изменил числовые данные. Проверьте исходный фрагмент.')
    # Only unambiguous, explicitly present literal spellings; never invent a lost
    # filename or replace arbitrary translated words based on a glossary guess.
    spellings={}
    for pattern in (_FILE, _PYTHON_COMMAND):
        for match in pattern.finditer(source):
            spellings.setdefault(match.group().casefold(),set()).add(match.group())
    for forms in spellings.values():
        if len(forms)==1:
            original=next(iter(forms))
            output=re.sub(r'(?<![A-Za-z0-9_.])'+re.escape(original)+r'(?![A-Za-z0-9_.])',lambda _:original,output,flags=re.I)
    return output
