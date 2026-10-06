"""Deterministic geometry grouping and text fitting; PDF coordinates are bottom-left."""
from dataclasses import dataclass
import math
import re

from app.documents.pdf_types import PdfSegment
from app.documents.run_metrics import measure


def union(boxes):
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def reading_order(blocks):
    """Recursive whitespace cuts: columns before rows, with spanning headings as bands."""
    if len(blocks) < 2:
        return blocks
    intervals = sorted((b.bbox[0], b.bbox[2]) for b in blocks)
    end = intervals[0][1]
    gaps = []
    for left, right in intervals[1:]:
        if left - end >= 18:
            gaps.append((left - end, (left + end) / 2))
        end = max(end, right)
    if gaps:
        split = max(gaps)[1]
        left = [b for b in blocks if b.bbox[2] <= split]
        right = [b for b in blocks if b.bbox[0] >= split]
        if left and right:
            return reading_order(left) + reading_order(right)
    ordered = sorted(blocks, key=lambda b: (-b.bbox[3], b.bbox[0], b.block_id))
    # A full-width heading prevents a global column cut. Split horizontal bands.
    bottom = ordered[0].bbox[1]
    for i, block in enumerate(ordered[1:], 1):
        if block.bbox[3] < bottom - 4:
            return reading_order(ordered[:i]) + reading_order(ordered[i:])
        bottom = min(bottom, block.bbox[1])
    return ordered


@measure('segmentation_reassembly')
def group_spans(page, spans, max_chars):
    from app.documents.pdf_ocr_policy import protected_kind
    def same_region(a, b):
        # Grid cells are assigned before grouping: adjacent rows/columns must
        # not become one logical string that never existed in the PDF.
        enclosed={'table_cell','warning'}
        if a.region_kind in enclosed or b.region_kind in enclosed:
            return (a.region_kind==b.region_kind and a.region_key is not None
                    and b.region_key is not None and a.region_key[:3]==b.region_key[:3])
        return True

    def hanging_continuation(block,line):
        # A Latin bullet can be larger than CJK glyphs in its hanging-indent
        # continuation. Require the same enclosed cell and an unfinished item;
        # ordinary paragraphs retain their original style boundary.
        return (block.region_kind in {'table_cell','warning'} and same_region(block,line)
                and re.match(r'^\s*[•●▪]\s',block.text)
                and not re.search(r'[。.!?！？]\s*$',block.text)
                and max(block.font_size,line.font_size)/min(block.font_size,line.font_size)<=1.25)

    def compatible_line_font(block,line):
        return abs(block.font_size-line.font_size)<=line.font_size*.12 or hanging_continuation(block,line)

    def compatible_indent(block,line):
        return (abs(block.bbox[0]-line.bbox[0])<=line.font_size*.6
                or hanging_continuation(block,line)
                and 0<=line.bbox[0]-block.bbox[0]<=max(block.font_size,line.font_size)*.8)
    # Cluster baselines before x ordering: CJK/Latin may use different font
    # sizes and a slightly different baseline inside the same physical line.
    rows = []
    for span in sorted(spans, key=lambda s: (-s.baseline, s.bbox[0])):
        row = next((r for r in reversed(rows) if span.rotation == r[0].rotation == 0
                    and abs(span.baseline - r[0].baseline) <= min(span.font_size, r[0].font_size) * .25), None)
        if row is None:
            rows.append([span])
        else:
            row.append(span)
    lines = []
    for row in rows:
        line = None
        for span in sorted(row, key=lambda s: s.bbox[0]):
            gap = span.bbox[0] - line.bbox[2] if line else 999
            if (line and same_region(line, span) and span.rotation == line.rotation == 0 and -2 <= gap <= max(line.font_size, span.font_size) * .9
                    and span.color == line.color and max(span.font_size, line.font_size) / min(span.font_size, line.font_size) < 1.5):
                space = ' ' if gap > line.font_size * .3 and not line.text.endswith(' ') and not span.text.startswith(' ') else ''
                line.text += space + span.text
                line.bbox = union([line.bbox, span.bbox])
                line.object_indices += span.object_indices
                line.font_names = tuple(dict.fromkeys(line.font_names + span.font_names))
            else:
                lines.append(span)
                line = span
    blocks = []
    for line in sorted(lines, key=lambda s: (-s.bbox[3], s.bbox[0])):
        candidates = [b for b in blocks if not re.match(r'^\s*(?:\d+[.)、]|[•●▪–-]\s)', line.text)
                      and same_region(b, line) and not protected_kind(b.text) and not protected_kind(line.text)
                      and b.rotation == line.rotation == 0
                      and compatible_indent(b,line)
                      and 0 <= b.bbox[1] - line.bbox[3] <= line.font_size * .9
                      and compatible_line_font(b,line)
                      and b.color == line.color and len(b.text) + len(line.text) < max_chars]
        if candidates:
            block = min(candidates, key=lambda b: b.bbox[1] - line.bbox[3])
            block.text += ' ' + line.text
            block.bbox = union([block.bbox, line.bbox])
            block.object_indices += line.object_indices
            block.font_names = tuple(dict.fromkeys(block.font_names + line.font_names))
        else:
            blocks.append(line)
    ordered = reading_order(blocks)
    for order, block in enumerate(ordered):
        block.text = block.text.strip()
        block.reading_order = order
        block.block_id = f'p{page + 1}-b{order + 1}'
    return ordered


def wrap(text, face, size, width):
    """Keep every character; long words and CJK may break between characters."""
    lines, current = [], ''
    for token in re.findall(r'\S+\s*|\s+', text):
        if face.width(current + token.rstrip(), size) <= width:
            current += token
            continue
        if current.strip():
            lines.append(current.rstrip())
            current = ''
        for character in token:
            if face.width(current + character, size) > width and current:
                lines.append(current.rstrip())
                current = ''
            current += character
    if current.strip():
        lines.append(current.rstrip())
    return lines


@dataclass
class FittedText:
    lines: list[str]
    size: float
    ascent: float
    leading: float
    overflow: bool


def fit(text, face, box, original_size, minimum, rotation=0):
    width, height = box[2] - box[0], box[3] - box[1]
    if rotation in {90, 270}:
        width, height = height, width
    ascent, descent = face.vertical(text)
    start = max(minimum, min(original_size, 100))
    sizes = [start - i * .5 for i in range(max(0, math.ceil((start - minimum) * 2)))] + [minimum]
    for size in sizes:
        lines = wrap(text, face, size, width)
        leading = max(1.15, ascent - descent + .1) * size
        needed = (ascent - descent) * size + max(0, len(lines) - 1) * leading
        if needed <= height + .1 and all(face.width(line, size) <= width + .1 for line in lines):
            return FittedText(lines, size, ascent * size, leading, False)
    # Visible marker plus full Unicode translation in a standard PDF text annotation.
    marker = '[...]'
    size = minimum
    lines = wrap(text, face, size, width)
    leading = max(1.15, ascent - descent + .1) * size
    count = max(0, math.floor((height - (ascent - descent) * size) / leading) + 1)
    visible = lines[:count]
    if visible:
        tail = visible[-1]
        while tail and face.width(tail + marker, size) > width:
            tail = tail[:-1]
        visible[-1] = tail + marker if face.width(marker, size) <= width else ''
    return FittedText(visible, size, ascent * size, leading, True)
