"""Adapt local OCR to the existing PdfSegment writer contract."""
from time import perf_counter
from statistics import median

from PIL import ImageStat
import pypdfium2.raw as raw

from app.documents.pdf_document import NativeTextExtractor
from app.documents.pdf_types import PdfSegment
from app.engine.languages import language_code
from app.ocr.config import configuration, profile
from app.ocr.errors import OcrError
from app.ocr.postprocess.deduplication import duplicate, area, intersection
from app.ocr.postprocess.regions import allocate,merge_lines,reading_order
from app.ocr.preprocess.renderer import render_region
from app.ocr.preprocess.orientation import pixel_to_pdf
from app.ocr.types import OcrRequest


def background(image, bbox):
    """Estimate the flat background from the text-box perimeter, not its glyphs."""
    x,y,r,b = bbox
    x,y = max(0,int(x)-1), max(0,int(y)-1)
    r,b = min(image.width-1,int(r)+1), min(image.height-1,int(b)+1)
    pixels = [image.getpixel((a,v)) for a in range(x,r+1) for v in (y,b)]
    pixels += [image.getpixel((a,v)) for v in range(y,b+1) for a in (x,r)]
    if not pixels:
        return (255,255,255,255), True
    color = tuple(int(median(p[c] for p in pixels)) for c in range(3))
    deviation = sum(max(abs(p[c]-color[c]) for c in range(3)) > 30 for p in pixels)/len(pixels)
    return (*color,255), deviation > .2


def complexity(image, objects):
    # Cheap bounded projection, not an additional neural model.
    gray = image.convert('L')
    gray.thumbnail((400,400))
    rows = list(gray.get_flattened_data())
    w,h = gray.size
    bands, active = 0, False
    for y in range(h):
        dark = sum(p < 100 for p in rows[y*w:(y+1)*w]) > w*.55
        if dark and not active:
            bands += 1
        active = dark
    vectors = sum(o.type == raw.FPDF_PAGEOBJ_PATH for o in objects)
    return {'lines': max(bands,vectors), 'regions': 0, 'columns': 0}


class HybridPdfExtractor:
    def __init__(self, router, config, checkpoint=lambda: None, progress=lambda *a: None):
        self.router, self.config = router, config
        self.checkpoint, self.progress = checkpoint, progress
        self.native = NativeTextExtractor()
        self.ocr_used = False
        self.timings = []
        self.region_count = 0

    def report_progress(self,stage,page,page_index):
        total=len(page.pdf)
        measured={t['page']:t['render_seconds']+t['ocr_seconds'] for t in self.timings}
        eta=round(sum(measured.values())/len(measured)*max(0,total-page_index)) if measured else None
        self.progress(stage,page_index,total,eta)

    def extract(self, page, page_index, objects, limits):
        self.checkpoint()
        if page_index >= configuration()['limits']['pages']:
            raise OcrError('limit')
        result = self.native.extract(page, page_index, objects, limits)
        bounds = page.get_bbox()
        minimum = configuration()['native']['minimum_region_points']
        images = [o.get_bounds() for o in objects if o.type == raw.FPDF_PAGEOBJ_IMAGE]
        regions = []
        for box in images:
            clipped = (max(bounds[0],box[0]), max(bounds[1],box[1]), min(bounds[2],box[2]), min(bounds[3],box[3]))
            if clipped[2]-clipped[0] < minimum or clipped[3]-clipped[1] < minimum:
                continue
            # A page-size scan with a usable native layer already has text. Keep
            # native priority; do not run a second recognizer over the same page.
            native_chars = sum(len(s.text) for s in result.segments if intersection(s.bbox,clipped) > 0)
            if area(clipped)/max(1,area(bounds)) >= .65 and native_chars >= 20:
                continue
            if not any(intersection(clipped,r)/max(1,area(clipped)) > .98 for r in regions):
                regions.append(clipped)
        if not result.segments and not images and objects:
            regions = [bounds]
        for region_index, region in enumerate(regions):
            self.checkpoint()
            started = perf_counter()
            self.report_progress('RENDERING',page,page_index)
            image = render_region(page, region, profile(self.config.profile)['dpi'])
            try:
                if max(ImageStat.Stat(image).stddev) < 2:
                    continue
                render_seconds = perf_counter()-started
                indicators = complexity(image,objects)
                request = OcrRequest(image,page_index,language_code(self.config.source),self.config.device,self.config.profile,region,
                                     complexity=indicators)
                self.report_progress('LAYOUT_ANALYSIS' if indicators['lines'] >= 8 and profile(self.config.profile)['structure'] else 'OCR',page,page_index)
                recognized = self.router.recognize(request)
                self.region_count += len(recognized.segments)
                if self.region_count > configuration()['limits']['regions']:
                    raise OcrError('limit')
                self.ocr_used = True
                result.warnings.extend(recognized.warnings)
                self.timings.append(dict(page=page_index,render_seconds=render_seconds,ocr_seconds=recognized.duration))
                # Stable page-space reading order. Layout model regions may group
                # columns, but never change the source coordinates or cell bounds.
                converted = []
                for item in recognized.segments:
                    pts = [pixel_to_pdf(x,y,region,image.size) for x,y in item.polygon]
                    xs,ys = zip(*pts)
                    box = (max(region[0],min(xs)),max(region[1],min(ys)),min(region[2],max(xs)),min(region[3],max(ys)))
                    if not item.text.strip() or area(box) <= 0:
                        continue
                    candidate = PdfSegment(page_index,f'ocr-{region_index}-{item.segment_id}',item.text,box,0,(),
                                           max(8,(box[3]-box[1])*.8),confidence=item.confidence,
                                           rotation=(-item.angle)%360,source_language=item.language,
                                           origin='ocr',polygon=tuple(pts),ocr_model=item.model_id)
                    if duplicate(candidate,result.segments+converted):
                        continue
                    if item.confidence < configuration()['confidence']['low']:
                        result.warnings.append(f'Страница {page_index+1}: блок с низкой уверенностью OCR сохранён как изображение.')
                        continue
                    candidate.available_bbox = box
                    candidate.region_key = (candidate.block_id,)
                    candidate.region_kind = 'ocr_region'
                    cells=[r for r in recognized.layout if r['label']=='table_cell' and intersection(item.bbox,r['bbox'])/max(1,area(item.bbox))>.9]
                    if cells:
                        cell=min(cells,key=lambda c:area(c['bbox']))['bbox']
                        left,top=pixel_to_pdf(cell[0],cell[1],region,image.size)
                        right,bottom=pixel_to_pdf(cell[2],cell[3],region,image.size)
                        if left+2 < box[0] and right-2 > box[2] and bottom+2 < box[1] and top-2 > box[3]:
                            candidate.available_bbox=(left+2,bottom+2,right-2,top-2)
                            candidate.region_key=tuple(round(v,1) for v in candidate.available_bbox)
                            candidate.region_kind='table_cell'
                    candidate.background_color, uncertain = background(image,item.bbox)
                    rgb = candidate.background_color[:3]
                    candidate.color = (255,255,255,255) if sum(rgb)/3 < 128 else (0,0,0,255)
                    if uncertain:
                        result.warnings.append(f'Страница {page_index+1}: неоднородный фон OCR-блока; используется локальная непрозрачная подложка.')
                    converted.append(candidate)
                converted=reading_order(converted,region)
                allocate(converted,image,region)
                converted=merge_lines(converted,limits.max_segment_chars)
                for i,s in enumerate(converted,len(result.segments)):
                    s.reading_order = i
                result.segments.extend(converted)
                if not recognized.segments and not result.segments:
                    result.warnings.append(f'Страница {page_index+1}: текст не распознан; изображение сохранено.')
            finally:
                image.close()
            self.checkpoint()
        return result
