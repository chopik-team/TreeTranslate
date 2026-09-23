"""Geometry-only layout regions; never infer technical content or change graphics."""
from collections import defaultdict
import re
import pypdfium2.raw as raw


def overlap_x(a, b):
    return a[0] < b[2] - .1 and a[2] > b[0] + .1


def assign_regions(page, objects, segments):
    if not segments:
        return
    bounds = page.get_bbox()
    horizontal, vertical, images = [], [], []
    for obj in objects:
        if obj.type not in {raw.FPDF_PAGEOBJ_PATH, raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_FORM}:
            continue
        box = obj.get_bounds()
        w, h = box[2] - box[0], box[3] - box[1]
        if obj.type != raw.FPDF_PAGEOBJ_PATH:
            images.append(box)
        elif w > 8 and h <= 2:
            horizontal.append(box)
        elif h > 8 and w <= 2:
            vertical.append(box)
    for s in segments:
        if s.rotation:
            s.available_bbox = s.bbox
            continue
        x, y, r, t = s.bbox
        cx, cy = (x+r)/2, (y+t)/2
        lefts = [v[2] for v in vertical if v[2] <= x + 1 and v[1] <= cy <= v[3]]
        rights = [v[0] for v in vertical if v[0] >= r - 1 and v[1] <= cy <= v[3]]
        bottoms = [h[3] for h in horizontal if h[3] <= y + 1 and h[0] <= cx <= h[2]]
        tops = [h[1] for h in horizontal if h[1] >= t - 1 and h[0] <= cx <= h[2]]
        enclosed = bool(lefts and rights and bottoms and tops)
        left = max(lefts) + 1.5 if enclosed else max(bounds[0] + 18, x)
        right = min(rights) - 1.5 if enclosed else bounds[2] - max(18, min(35, x))
        # Neighboring columns form a boundary even without a vector grid.
        neighbors = [b.bbox[0] for b in segments if b is not s and b.bbox[0] > r + 12
                     and b.bbox[1] < t and b.bbox[3] > y]
        if neighbors:
            right = min(right, min(neighbors) - 9)
        bottom = max(bottoms) + 1.5 if bottoms else bounds[1] + 22
        top = min(tops) - 1.5 if tops else bounds[3] - 22
        band = (left, bottom, right, top)
        for obstacle in images:
            if not overlap_x(band, obstacle):
                continue
            if obstacle[1] >= t - .5:
                top = min(top, obstacle[1] - 1.5)
            elif obstacle[3] <= y + .5:
                bottom = max(bottom, obstacle[3] + 1.5)
            elif obstacle[0] >= r:
                right = min(right, obstacle[0] - 3)
        if right <= left or top <= bottom:
            s.available_bbox = s.bbox
            continue
        # Separate table cells and warning boxes; keep all their vector edges.
        s.region_kind = 'table_cell' if enclosed and right-left < (bounds[2]-bounds[0])*.65 else 'warning' if enclosed else 'paragraph'
        if s.region_kind == 'paragraph':
            if re.match(r'^\d+[.)РіР‚Рѓ]', s.text):
                s.region_kind = 'numbered_step'
            elif re.match(r'^[РІР‚СћРІвЂ”РЏРІвЂ“Р„]', s.text):
                s.region_kind = 'bullet'
            elif y < bounds[1] + 55:
                s.region_kind = 'footer'
            elif s.font_size >= 14 or (t > bounds[3] - 60 and len(s.text) < 100):
                s.region_kind = 'heading'
        s.available_bbox = (left, bottom, right, top)
        s.region_key = tuple(round(v / 12) * 12 for v in (bottom, right, top))
        if s.region_kind == 'table_cell':
            s.alignment = 'center' if abs(cx-(left+right)/2) < (right-left)*.15 else 'left'
            if s.alignment == 'left':
                s.available_bbox = (max(left,x), bottom, right, top)
                s.region_key += (round(x/12)*12,)


def flow_boxes(segments, fonts):
    """Allocate a column between fixed graphics; move following text only there.

    Preserve original top positions unless a preceding paragraph needs more room.
    Reserve a readable line for following blocks; final excess uses continuation.
    """
    from app.documents.pdf_layout import wrap
    groups = defaultdict(list)
    for s in segments:
        if not s.rotation and s.available_bbox and s.translated != s.text:
            groups[s.region_key or s.block_id].append(s)
    for group in groups.values():
        group.sort(key=lambda s: (-s.bbox[3], s.bbox[0]))
        cursor = group[0].available_bbox[3]
        sizes = {s.block_id: max(8, s.font_size) for s in group}
        def height(s, size):
            face = fonts.resolve((s.translated or s.text) + '[...]')
            a, d = face.vertical(s.translated or s.text)
            lines = wrap(s.translated or s.text, face, size, s.available_bbox[2]-s.available_bbox[0])
            return (a-d)*size + max(0,len(lines)-1)*max(1.2,a-d+.1)*size + 1
        start = min(cursor, group[0].bbox[3] + max(2, group[0].font_size*.5))
        room = start - group[0].available_bbox[1]
        # Moderate reduction is considered only after width expansion and flow.
        for _ in range(5):
            if sum(height(s,sizes[s.block_id])+2 for s in group)-2 <= room:
                break
            sizes = {k: max(8, v-.4) for k,v in sizes.items()}
        cursor = start
        for s in group:
            left, bottom, right, ceiling = s.available_bbox
            top = cursor
            s.layout_font_size = sizes[s.block_id]
            needed = height(s, s.layout_font_size)
            block_bottom = max(bottom, top-needed)
            if top-bottom < 4:
                # No safe rectangle remains: the writer uses a continuation.
                s.rendered_bbox = (left, bottom, right, bottom)
            else:
                s.rendered_bbox = (left, block_bottom, right, top)
            cursor = block_bottom - 2
