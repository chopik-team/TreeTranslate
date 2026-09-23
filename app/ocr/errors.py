from app.documents.errors import DocumentError
from app.engine.errors import DeviceUnavailableError


class OcrError(DocumentError):
    def __init__(self, code='inference', page=None):
        self.code = code
        self.diagnostic = dict(stage='OCR', operation=code, page=page)
        messages = {
            'missing': 'Локальные модели OCR отсутствуют или повреждены. Подготовьте OCR-компонент TreeTranslate.',
            'runtime': 'Локальный Paddle OCR runtime недоступен. Проверьте установку OCR-компонента.',
            'gpu': 'GPU недоступна для OCR. Выберите CPU или Auto.',
            'render': 'Не удалось отрисовать страницу для OCR.',
            'limit': 'Превышен безопасный лимит обработки OCR.',
            'confidence': 'Не удалось уверенно распознать текст. Проверьте качество скана или выберите язык вручную.',
            'network': 'Сетевой доступ OCR заблокирован. Используются только локальные модели.',
            'timeout': 'Превышено время распознавания страницы. Попробуйте другой профиль или более короткий документ.',
        }
        message = messages.get(code, 'Не удалось выполнить локальное распознавание текста.')
        if page is not None:
            message += f' Страница {page}.'
        super().__init__(message)


class OcrDeviceUnavailableError(OcrError, DeviceUnavailableError):
    def __init__(self):
        super().__init__('gpu')
