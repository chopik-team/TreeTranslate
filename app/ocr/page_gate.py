"""Cheap page decisions preserving the existing extraction region policy."""
from dataclasses import dataclass
import pypdfium2.raw as raw
from app.ocr.config import configuration
from app.ocr.postprocess.deduplication import area, intersection


@dataclass(frozen=True)
class PageDecision:
    status: str
    regions: tuple
    quality_fallback: bool
    native_chars: int
    image_count: int
    avoided_regions: int


def decide_page(bounds, objects, segments, usable_chars):
    minimum = configuration()['native']['minimum_region_points']
    images = [o.get_bounds() for o in objects if o.type == raw.FPDF_PAGEOBJ_IMAGE]
    regions = []; avoided = 0
    for box in images:
        clipped = (max(bounds[0], box[0]), max(bounds[1], box[1]),
                   min(bounds[2], box[2]), min(bounds[3], box[3]))
        if clipped[2]-clipped[0] < minimum or clipped[3]-clipped[1] < minimum:
            avoided += 1; continue
        count = usable_chars(s for s in segments if intersection(s.bbox, clipped) > 0)
        if area(clipped)/max(1, area(bounds)) >= .65 and count >= 20:
            avoided += 1; continue
        if not any(intersection(clipped, r)/max(1, area(clipped)) > .98 for r in regions):
            regions.append(clipped)
        else:
            avoided += 1
    if not segments and not images and objects:
        regions = [bounds]
    graphical = (sum(o.type == raw.FPDF_PAGEOBJ_PATH for o in objects) >= 8
                 or any(o.type == raw.FPDF_PAGEOBJ_FORM and area(o.get_bounds()) >= area(bounds)*.15
                        for o in objects))
    count = usable_chars(segments)
    fallback = not regions and graphical and count == 0
    if fallback:
        regions = [bounds]
    status = ('UNCERTAIN_FALLBACK' if fallback else
              'NATIVE_SUFFICIENT' if not regions and segments else
              'UNCERTAIN_FALLBACK' if not regions else
              'MIXED_NEEDS_REGION_OCR' if segments else 'IMAGE_ONLY_NEEDS_OCR')
    return PageDecision(status, tuple(regions), fallback, count, len(images), avoided)
