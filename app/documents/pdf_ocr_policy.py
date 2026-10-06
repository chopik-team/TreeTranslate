"""Conservative diagram policies; no corpus or filename specific rules."""
import re

IDENTIFIER = re.compile(r"[A-Z]{1,8}[0-9]*['′″\"]*(?:\s*[-/=]&?\s*[A-Z]{1,8}[0-9]*['′″\"]*)*")
MEASUREMENT = re.compile(r"(?:[A-Z]['′″\"]*(?:\s*[-/=]\s*[A-Z]['′″\"]*)?\s*[:：]\s*)?[ØøΦφ⌀]?\d+(?:[.,]\d+)?(?:\s*[x×X±+\-/]\s*\d+(?:[.,]\d+)?)*(?:\s*\(\d+(?:[.,]\d+)?\))?(?:\s*(?:mm|inch|毫米|英寸))?", re.I)


def protected_kind(text):
    text = text.strip()
    if IDENTIFIER.fullmatch(text):
        return 'identifier'
    wrapped = re.fullmatch(r'(?:\(\s*(.*?)\s*\)|（\s*(.*?)\s*）|\[\s*(.*?)\s*\]|［\s*(.*?)\s*］)',text)
    if wrapped and IDENTIFIER.fullmatch(next(value for value in wrapped.groups() if value is not None)):
        return 'identifier'
    if MEASUREMENT.fullmatch(text):
        return 'measurement'
    from app.knowledge.units import TECHNICAL_MEASUREMENT
    if TECHNICAL_MEASUREMENT.fullmatch(text):
        return 'measurement'
    return None


def classify(segment):
    text = segment.text.strip()
    kind = protected_kind(text)
    if kind:
        return kind
    if not re.search(r'[\u4e00-\u9fff]|[a-zа-я]{3}', text):
        return 'noise'
    letters = sum(c.isalpha() for c in text)
    height = segment.bbox[3] - segment.bbox[1]
    if (not letters or letters <= 1 or (segment.confidence or 0) < .65
            or height < 3 or '\ufffd' in text
            or sum(c.isalnum() for c in text) < len(text) * .3):
        return 'noise'
    # Sentence punctuation and sufficient language content distinguish real
    # instructions from short labels, including labels merged over two rows.
    if letters >= 18 and re.search(r'[。！？.!?]', text):
        return 'prose'
    return 'diagram_label'


def diagram_box(segment, neighbours):
    box = segment.rendered_bbox or segment.available_bbox or segment.bbox
    box = (max(box[0], segment.bbox[0]), max(box[1], segment.bbox[1]),
           box[2], min(box[3], segment.bbox[3]))
    right = min((s.bbox[0] - 1 for s in neighbours if s is not segment
                 and s.bbox[0] > segment.bbox[0]
                 and min(s.bbox[3], box[3]) > max(s.bbox[1], box[1])), default=box[2])
    return (box[0], box[1], min(box[2], right), box[3])


def native_diagram_label(segment):
    return (segment.origin == 'native' and segment.region_kind == 'table_cell'
            and len(segment.text) <= 80 and re.search(r'[\u4e00-\u9fff]', segment.text)
            and not segment.text.rstrip().endswith(('。', '!', '?')))


def compact_label(text):
    """Unambiguous Russian technical abbreviations; never change geometry."""
    words = {'отверстие': 'отв.', 'крепления': 'крепл.', 'внутренней': 'внутр.',
             'передней': 'передн.', 'задней': 'задн.', 'электродвигателя': 'электромотора'}
    def abbreviation(match):
        word = match.group()
        value = words[word.lower()]
        return value[0].upper() + value[1:] if word[0].isupper() else value
    return re.sub(r'\b(?:'+'|'.join(words)+r')\b', abbreviation, text, flags=re.I)
