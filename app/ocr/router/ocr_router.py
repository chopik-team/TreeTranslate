from dataclasses import replace
from app.ocr.backends.paddle_backend import PaddleBackend
from app.ocr.backends.structure_backend import StructureBackend
from app.ocr.config import configuration, profile
from app.ocr.errors import OcrError, OcrDeviceUnavailableError
from app.ocr.router.routing_policy import decide
from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager


class OcrRouter:
    def __init__(self, checkpoint=lambda: None, runtime=None, before_ocr=lambda: None):
        self.runtime = runtime or OcrRuntimeManager(checkpoint=checkpoint)
        self.before_ocr = before_ocr
        self.backends = {'paddle': PaddleBackend(self.runtime), 'structure': StructureBackend(self.runtime)}
        self.last_results = []

    def recognize(self, request):
        width,height=request.image.size
        limits=configuration()['limits']
        if min(width,height)<=0 or max(width,height)>limits['dimension'] or width*height>limits['pixels']:
            raise OcrError('limit')
        self.before_ocr()
        options = profile(request.performance_profile)
        decision = decide(request.complexity, request.performance_profile)
        backend = self.backends[decision.backend]
        preference = str(request.device_preference).lower()
        devices = ('gpu', 'cpu') if preference == 'auto' and options['auto_gpu'] else ('cpu',) if preference == 'auto' else (preference,)
        warning = []
        for device in devices:
            try:
                backend=self.backends[decision.backend]
                result = backend.recognize(request, device)
                middle=request.image.width/2
                left=[s.bbox for s in result.segments if s.bbox[2]<middle-4]
                right=[s.bbox for s in result.segments if s.bbox[0]>middle+4]
                columns=0
                if min(len(left),len(right))>=3:
                    overlap=min(max(b[3] for b in left),max(b[3] for b in right))-max(min(b[1] for b in left),min(b[1] for b in right))
                    if overlap>request.image.height*.5:columns=2
                indicators=dict(request.complexity,regions=len(result.segments),columns=columns)
                if decision.backend == 'paddle' and decide(indicators,request.performance_profile).backend=='structure':
                    decision = decide(indicators,request.performance_profile)
                    request = replace(request,complexity=indicators)
                    result = self.backends['structure'].recognize(request,device)
                break
            except OcrError as error:
                if preference == 'gpu' and error.code == 'gpu':
                    raise OcrDeviceUnavailableError() from None
                if len(devices) < 2 or device == 'cpu' or error.code not in ('gpu', 'inference'):
                    raise
                self.runtime.shutdown()
                warning.append('GPU OCR недоступна; Auto продолжает распознавание на CPU.')
        result.warnings.extend(warning)
        result.route_reason = decision.reason
        result.layout_complexity = request.complexity
        # Metadata only: do not retain document images or recognized text in a runtime cache.
        self.last_results.append(dict(page=result.page_index, backend=result.backend, device=result.device,
                                      seconds=result.duration, timings=result.timings, reason=result.route_reason))
        return result

    def shutdown(self):
        self.runtime.shutdown()
