from time import perf_counter

from app.ocr.config import profile, configuration
from app.ocr.errors import OcrError
from app.ocr.types import OcrPageResult, OcrSegment
from app.ocr.runtime.ocr_model_manager import OcrModelManager, RecognitionModelResolver
from app.ocr.preprocess.orientation import restore_point


class PaddleBackend:
    name = 'paddle'

    def __init__(self, runtime, models=None):
        self.runtime = runtime
        self.models = models or OcrModelManager()

    def initialize(self):
        self.models.require('PP-OCRv6_small_det')

    def capabilities(self):
        return {'languages': ('zh', 'en', 'ru'), 'devices': ('cpu', 'gpu'), 'offline': True}

    def recognize(self, request, device):
        started = perf_counter()
        options = profile(request.performance_profile)
        resolver = RecognitionModelResolver()
        candidates = resolver.candidates(request.source_language)
        paths = {name: self.models.require(name) for name in ('PP-OCRv6_small_det', *candidates)}
        if options['orientation']:
            paths['PP-LCNet_x1_0_doc_ori'] = self.models.require('PP-LCNet_x1_0_doc_ori')
        if self.name == 'structure':
            paths['PP-DocLayout_plus-L'] = self.models.require('PP-DocLayout_plus-L')
            for name in ('PP-LCNet_x1_0_table_cls','SLANeXt_wired','SLANet_plus',
                         'RT-DETR-L_wired_table_cell_det','RT-DETR-L_wireless_table_cell_det','PP-LCNet_x1_0_doc_ori'):
                paths[name] = self.models.require(name)
        command = dict(device=device, backend=self.name, models=paths,
                       options={k: options[k] for k in ('threads', 'batch', 'orientation')})
        results = []
        # Auto is bounded to two alphabets, never recursive or an unbounded retry.
        for recognizer in candidates:
            data = self.runtime.run(request.image, dict(command, recognizer=recognizer))
            score = sum(r['confidence'] * len(r['text']) for r in data['rows']) / max(1, sum(len(r['text']) for r in data['rows']))
            results.append((score, recognizer, data))
        _, recognizer, data = max(results, key=lambda r: r[0])
        if len(data['rows']) > configuration()['limits']['regions'] or sum(len(r['text']) for r in data['rows']) > configuration()['limits']['characters']:
            raise OcrError('limit')
        width, height = request.image.size
        angle = data['angle'] % 360
        for region in data['layout']:
            x,y,r,b = region['bbox']
            points=[restore_point(a,v,width,height,(-angle)%360) for a,v in ((x,y),(r,y),(r,b),(x,b))]
            xs,ys=zip(*points)
            region['bbox']=[min(xs),min(ys),max(xs),max(ys)]
        # Paddle document preprocessor rotates counterclockwise by angle.
        polygons = [tuple(restore_point(x, y, width, height, (-angle) % 360) for x,y in row['polygon']) for row in data['rows']]
        segments = []
        for index, (row, polygon) in enumerate(zip(data['rows'], polygons)):
            xs, ys = zip(*polygon)
            segments.append(OcrSegment(str(index), row['text'], polygon, (min(xs), min(ys), max(xs), max(ys)),
                row['confidence'], angle, 'ru' if 'cyrillic' in recognizer else request.source_language,
                index, request.page_index, request.region, self.name, recognizer))
        return OcrPageResult(request.page_index, segments, self.name, data['device'], perf_counter()-started,
                             timings={k: data[k] for k in ('load_seconds', 'inference_seconds', 'rss_bytes', 'network_attempts',
                                                          'gpu_peak_allocated_bytes','gpu_peak_reserved_bytes')}, layout=data['layout'])

    def shutdown(self):
        self.runtime.shutdown()
