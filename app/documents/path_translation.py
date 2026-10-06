"""Run-local component cache; naming never profiles a whole document."""
from collections import OrderedDict
from dataclasses import is_dataclass, replace
from copy import copy

from app.documents.run_metrics import measure
from app.engine.backends.base_backend import check_cancelled


class PathTranslation:
    def __init__(self, translate, capacity=4096):
        engine = getattr(translate, '__self__', None)
        self.translate = getattr(engine, 'translate_path', None) or translate
        self.capacity = capacity
        self.cache = OrderedDict()
        self.hits = self.misses = 0

    @measure('path_translation')
    def __call__(self, request, cancelled):
        check_cancelled(cancelled)
        snapshot = request.knowledge_snapshot
        key = (request.text, request.source_language, request.target_language,
               request.domain, request.context, request.segment_type,
               getattr(snapshot, 'signature', ''), request.device_preference,
               request.performance_profile, request.cpu_threads)
        if key in self.cache:
            self.hits += 1
            result = self.cache.pop(key)
            self.cache[key] = result
            if is_dataclass(result):
                return replace(result, request_id=request.request_id, duration_ms=0)
            return copy(result)  # Lightweight embedding/test callbacks also work.
        self.misses += 1
        result = self.translate(request, cancelled)
        self.cache[key] = result
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
        return result
