import unicodedata
from difflib import SequenceMatcher
from app.ocr.config import configuration


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def intersection(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def area(box):
    return max(0, box[2]-box[0]) * max(0, box[3]-box[1])


def duplicate(candidate, existing):
    thresholds = configuration()['dedup']
    for other in existing:
        coverage = intersection(candidate.bbox, other.bbox) / max(1, min(area(candidate.bbox), area(other.bbox)))
        similarity = SequenceMatcher(None, normalize(candidate.text), normalize(other.text)).ratio()
        if coverage >= thresholds['overlap'] and similarity >= thresholds['similarity']:
            return True
    return False
