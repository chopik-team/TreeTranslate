"""Conservative structural fidelity rules, independent of the translation model."""
import re
from decimal import Decimal
import unicodedata
from app.documents.docx_document import URL


ATOM = re.compile(URL.pattern + r'|(?<![A-Za-z])[A-Z][A-Z0-9]{1,}(?![A-Za-z])'
                  r'|(?<![A-Za-z0-9])(?:\d+(?:[.,]\d+)*)(?:\s*[-–—－]\s*\d+(?:[.,]\d+)*)?[%％]?'
                  r'|\b[A-Za-z][A-Za-z0-9]*[_.-][A-Za-z0-9_.-]*\d[A-Za-z0-9_.-]*\b')


def preserve_title(text):
    """Short Latin labels/titles, mixed case brands, code, version identifiers.

    No product names from the regression corpus are embedded in this rule.
    Ordinary sentence-case prose and punctuation-ended sentences are translated.
    """
    text = text.strip()
    if not text or not any(c.isalpha() for c in text):
        return True
    if not re.fullmatch(r'[A-Za-z0-9\s_./&()+\-:]+', text) or text.endswith(('.', '!', '?')):
        return False
    words = text.split()
    if len(words) > 10 or len(text) > 100:
        return False
    if len(words) == 1:
        return bool(re.search(r'[A-Z]|[0-9_./]', text))
    if len(words) <= 4 and re.fullmatch(r'[A-Z0-9]{1,5}', words[0]):
        return True
    connectors = {'for', 'of', 'the', 'and', 'in', 'on', 'to', '&'}
    return all(w[0].isupper() or w[0].isdigit() or w.lower() in connectors or w.startswith('(') for w in words)


def segment_source(text, default, target, resolve):
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 24:
        return default
    latin = sum('a' <= c.lower() <= 'z' for c in letters) / len(letters)
    cyrillic = sum('а' <= c.lower() <= 'я' for c in letters) / len(letters)
    chinese = sum('\u4e00' <= c <= '\u9fff' for c in letters) / len(letters)
    different = (latin > .85 and default not in {'en','de','fr','es'} or cyrillic > .85 and default != 'ru'
                 or chinese > .85 and default != 'zh')
    return resolve(text, 'auto', target)[0] if different else default


class FidelityMismatch(ValueError):
    """Contains no source/translated content; caller preserves source with notice."""


def faithful_result(source, translated):
    # Check values and multiplicity before restoring the source's exact spelling.
    number = re.compile(r'\d+(?:[.,]\d+)?')
    original = list(number.finditer(source))
    result = list(number.finditer(translated))
    value = lambda m: Decimal(m.group().replace(',', '.'))
    if [value(m) for m in original] != [value(m) for m in result]:
        raise FidelityMismatch('numeric_invariant')
    for a, b in reversed(list(zip(original, result))):
        translated = translated[:b.start()] + a.group() + translated[b.end():]
    translit = str.maketrans(dict(zip('ABVGDEZIJKLMNOPRSTUFHCY', 'АБВГДЕЗИЙКЛМНОПРСТУФХЦЫ')))
    identifiers = re.findall(r'(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])', source)
    for token in identifiers:
        translated = re.sub(r'(?<![A-Za-z])'+re.escape(token)+r'(?![A-Za-z0-9])', token, translated, flags=re.I)
        if not re.search(r'(?<![A-Za-z])'+re.escape(token)+r'(?![A-Za-z0-9])', translated):
            translated = re.sub(r'(?<![А-Я])'+re.escape(token.translate(translit))+r'(?![А-Я])', token, translated)
        if token not in translated:
            raise FidelityMismatch('identifier_invariant')
    return translated
