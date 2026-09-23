from app.config.paths import MODELS_DIR
from app.engine.runtime.model_manager import ModelManager
from app.engine.errors import ModelMissingError
from app.ocr.errors import OcrError


class OcrModelManager(ModelManager):
    def __init__(self, root=None):
        super().__init__(root or MODELS_DIR / 'ocr')

    def require(self, model_id):
        try:
            record = next((r for r in self.records if r.id == model_id), None)
            if record is None:
                raise OcrError('missing')
            return str(self.validate(record))
        except ModelMissingError:
            raise OcrError('missing') from None


class RecognitionModelResolver:
    def resolve(self, language):
        if language in ('ru', 'uk', 'bg', 'be'):
            return 'cyrillic_PP-OCRv5_mobile_rec'
        return 'PP-OCRv6_small_rec'

    def candidates(self, language):
        return ('PP-OCRv6_small_rec', 'cyrillic_PP-OCRv5_mobile_rec') if language == 'auto' else (self.resolve(language),)
