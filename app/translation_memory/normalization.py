"""Version 1 normalization; punctuation, case and identifiers remain significant."""
from hashlib import sha256, blake2s
from decimal import Decimal
import re
import unicodedata

NUMBER = re.compile(r'(?<![A-Za-z0-9_])[+-]?\d+(?:[.,]\d+)?(?![A-Za-z0-9_])')
IDENTIFIER = re.compile(r'(?:https?://|www\.)\S+|\b[\w.+-]+@[\w.-]+\b|\b[A-Za-z][\w]*[_.-][\w.-]*\d[\w.-]*\b|(?<![A-Za-z0-9_])[A-Z]{2,}[A-Z0-9]*(?![A-Za-z0-9_])')
SLOT = '{NUMBER_1}'


def normalize(text):
    text = unicodedata.normalize('NFKC', text)
    text = text.translate(str.maketrans({'“': '"', '”': '"', '‘': "'", '’': "'"}))
    return ' '.join(text.split())


def digest(text):
    return sha256(text.encode('utf-8')).hexdigest()


def signature(text):
    # Case and complete alphanumeric identifiers must survive reuse.
    return (tuple(IDENTIFIER.findall(text)),
            tuple(Decimal(m.replace(',', '.')) for m in NUMBER.findall(text)),
            len(re.findall(r'[%％]', text)),
            tuple(re.findall(r'\d\s*([-–—])\s*\d', text)))


def compatible(left, right):
    return signature(left) == signature(right)


def template_key(text):
    text = normalize(text)
    matches = list(NUMBER.finditer(text))
    if len(matches) != 1 or IDENTIFIER.search(text) or any(c in text for c in '%％'):
        return None
    match = matches[0]
    return text[:match.start()] + SLOT + text[match.end():], match.group()


def fuzzy_keys(text):
    """Bounded deterministic min-hash shingles, including CJK characters."""
    text = normalize(text).casefold()
    grams = {text[i:i+3] for i in range(max(1, len(text)-2))}
    return sorted({blake2s(g.encode(), digest_size=6).hexdigest() for g in grams})[:6]
