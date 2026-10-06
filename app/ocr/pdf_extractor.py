"""Adapt local OCR to the existing PdfSegment writer contract."""
from time import perf_counter
from statistics import median

from PIL import ImageStat
import pypdfium2.raw as raw

from app.documents.pdf_document import NativeTextExtractor
from app.documents.pdf_types import PdfSegment
from app.documents.pdf_ocr_policy import classify, protected_kind
from app.documents.pdf_document import meaningful, detached_pdf_work
from app.engine.languages import language_code
from app.ocr.config import configuration, profile
from app.ocr.errors import OcrError
from app.ocr.postprocess.deduplication import duplicate, area, intersection
from app.ocr.postprocess.regions import allocate,merge_lines,reading_order
from app.ocr.preprocess.renderer import render_region
from app.ocr.preprocess.orientation import pixel_to_pdf
from app.ocr.types import OcrRequest
from app.documents.pdf_diagnostics import timed_process, timed_stage, current_document_run
import logging
import json
import os
from app.ocr.page_gate import decide_page

logger = logging.getLogger('treetranslate.documents.ocr')


def usable_native_chars(segments):
    """Ignore navigation/measurements when deciding if diagrams need OCR."""
    return sum(len(meaningful(s.text)) for s in segments
               if not protected_kind(s.text) and s.text.count('>') < 2)


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
        self._current_region = 0
        self._page_regions = 0
        self.source_identity = ''
        self.gate_decisions = []

    def set_source_identity(self, identity):
        self.source_identity = identity

    def report_progress(self,stage,page,page_index):
        total=len(page.pdf)
        # Estimate extraction only. Exclude the first cold observation and wait
        # for two warm regions; later inference has its own estimator.
        samples = [t['render_seconds'] + t['ocr_seconds'] for t in self.timings[1:]][-8:]
        remaining = (total - page_index - 1) * self._page_regions + self._page_regions - self._current_region
        eta = max(1, round(median(samples) * remaining)) if len(samples) >= 2 and remaining > 0 else None
        self.progress(stage,page_index,total,eta)

    @timed_process('hybrid_page_extract', page_index_arg=2)
    def extract(self, page, page_index, objects, limits):
        self.checkpoint()
        if page_index >= configuration()['limits']['pages']:
            raise OcrError('limit')
        result = self.native.extract(page, page_index, objects, limits)
        bounds = page.get_bbox()
        gate_started = perf_counter()
        decision = decide_page(bounds, objects, result.segments, usable_native_chars)
        regions = list(decision.regions)
        quality_fallback = decision.quality_fallback
        gate_row = dict(source_identity=self.source_identity, page=page_index,
                        status=decision.status, regions=regions, gate_seconds=perf_counter()-gate_started,
                        avoided_regions=decision.avoided_regions, new_skips=0)
        self.gate_decisions.append(gate_row)
        gate_path = os.environ.get('TREETRANSLATE_OCR_GATE_LOG')
        if gate_path:
            with open(gate_path, 'a', encoding='utf8') as stream:
                stream.write(json.dumps(gate_row)+'\n')
        if quality_fallback:
            regions = [bounds]
            logger.info('run=%s page=%d native_quality_fallback usable_chars=%d',
                        current_document_run(), page_index+1, usable_native_chars(result.segments))
        self._page_regions = len(regions)
        for region_index, region in enumerate(regions):
            self._current_region = region_index
            self.checkpoint()
            started = perf_counter()
            self.report_progress('RENDERING',page,page_index)
            with timed_stage('ocr_render', page_index + 1, region_index + 1):
                image = render_region(page, region, profile(self.config.profile)['dpi'])
            try:
                if max(ImageStat.Stat(image).stddev) < 2:
                    continue
                render_seconds = perf_counter()-started
                with timed_stage('ocr_complexity', page_index + 1, region_index + 1):
                    indicators = complexity(image,objects)
                request = OcrRequest(image,page_index,language_code(self.config.source),self.config.device,self.config.profile,region,
                                     complexity=indicators, source_identity=self.source_identity,
                                     render_identity=(profile(self.config.profile)['dpi'], *image.size))
                self.report_progress('LAYOUT_ANALYSIS' if indicators['lines'] >= 8 and profile(self.config.profile)['structure'] else 'OCR',page,page_index)
                with timed_stage('ocr_recognize', page_index + 1, region_index + 1):
                    # render_region returns an independent RGB copy and closes
                    # its bitmap/restores the page rotation before this scope.
                    # The router uses image/request data, never page/objects.
                    with detached_pdf_work():
                        recognized = self.router.recognize(request)
                logger.info('run=%s page=%d region=%d OCR backend=%s device=%s segments=%d worker_seconds=%.4f timings=%s',
                            current_document_run(), page_index + 1, region_index + 1, recognized.backend, recognized.device,
                            len(recognized.segments), recognized.duration, recognized.timings)
                self.region_count += len(recognized.segments)
                if self.region_count > configuration()['limits']['regions']:
                    raise OcrError('limit')
                self.ocr_used = True
                result.warnings.extend(recognized.warnings)
                self.timings.append(dict(page=page_index,render_seconds=render_seconds,ocr_seconds=recognized.duration))
                # Stable page-space reading order. Layout model regions may group
                # columns, but never change the source coordinates or cell bounds.
                with timed_stage('ocr_postprocess', page_index + 1, region_index + 1):
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
                        s.ocr_kind = classify(s)
                    result.segments.extend(converted)
                    if not recognized.segments and not result.segments:
                        result.warnings.append(f'Страница {page_index+1}: текст не распознан; изображение сохранено.')
            finally:
                image.close()
            self.checkpoint()
        if quality_fallback:
            height = bounds[3]-bounds[1]
            body = (bounds[0],bounds[1]+height*.1,bounds[2],bounds[3]-height*.15)
            usable_body = [s for s in result.segments if s.ocr_kind not in ('noise','identifier','measurement')
                           and intersection(s.bbox,body) > area(s.bbox)*.8]
            if usable_native_chars(usable_body) == 0:
                result.warnings.append(f'Страница {page_index+1}: OCR не нашёл пригодного текста в области содержимого. Проверьте исходный PDF.')
                logger.warning('run=%s page=%d native_quality_fallback no_usable_body_text',current_document_run(),page_index+1)
        return result
