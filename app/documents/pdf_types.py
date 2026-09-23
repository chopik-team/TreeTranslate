"""Serializable PDF contracts. No Qt or translation backend dependencies."""
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import json

from app.config.paths import ASSETS_DIR
from app.documents.errors import DocumentError


class PdfKind(StrEnum):
    TEXT_PDF = 'TEXT_PDF'
    MIXED_PDF = 'MIXED_PDF'
    SCANNED_PDF = 'SCANNED_PDF'
    IMAGE_ONLY_PDF = 'IMAGE_ONLY_PDF'
    EMPTY_PDF = 'EMPTY_PDF'
    ENCRYPTED_PDF = 'ENCRYPTED_PDF'
    CORRUPTED_PDF = 'CORRUPTED_PDF'
    UNSUPPORTED_PDF = 'UNSUPPORTED_PDF'


MESSAGES = {
    PdfKind.IMAGE_ONLY_PDF: 'В PDF не найден доступный текст. Для этого документа требуется локальный OCR-компонент.',
    PdfKind.EMPTY_PDF: 'PDF не содержит доступного текста для перевода.',
    PdfKind.ENCRYPTED_PDF: 'PDF зашифрован. Перевод защищённых PDF пока не поддерживается.',
    PdfKind.CORRUPTED_PDF: 'Не удалось открыть PDF: файл повреждён.',
    PdfKind.UNSUPPORTED_PDF: 'Этот PDF не может быть безопасно обработан: неподдерживаемая структура или превышен лимит.',
}


class PdfError(DocumentError):
    def __init__(self, kind, diagnostic=None):
        self.kind = kind
        self.diagnostic = diagnostic
        message = MESSAGES[kind]
        if diagnostic:
            message = 'Не удалось обработать структуру PDF.'
            if diagnostic.get('page'):
                message += f" Ошибка обработки на странице {diagnostic['page']}."
        super().__init__(message)


class ObjectPolicy(StrEnum):
    SUPPORTED = 'SUPPORTED'
    CONSERVATIVE_PRESERVE = 'CONSERVATIVE_PRESERVE'
    TRANSLATABLE = 'TRANSLATABLE'
    UNSUPPORTED_FATAL = 'UNSUPPORTED_FATAL'


@dataclass(frozen=True)
class PdfLimits:
    max_file_bytes: int = 128 * 1024 * 1024
    max_pages: int = 500
    max_objects_per_page: int = 20000
    max_text_chars: int = 2000000
    max_segment_chars: int = 4000
    min_font_size: float = 6.0
    max_page_points: float = 14400.0

    @classmethod
    def load(cls, path: Path | None = None):
        path = path or ASSETS_DIR / 'config/pdf_limits.json'
        values = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        limits = cls(**values)
        if any(not isinstance(v, (int, float)) or v <= 0 for v in values.values()):
            raise DocumentError('Некорректная конфигурация лимитов PDF.')
        return limits


@dataclass
class PdfSegment:
    page: int
    block_id: str
    text: str
    bbox: tuple[float, float, float, float]
    reading_order: int
    font_names: tuple[str, ...]
    font_size: float
    alignment: str = 'left'
    rotation: int = 0
    direction: str = 'ltr'
    source_language: str | None = None
    status: str = 'pending'
    translated: str | None = None
    object_indices: tuple[int, ...] = ()
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    confidence: float | None = None
    visible_text: str | None = None
    overflow_text: str | None = None
    baseline: float = 0.0
    available_bbox: tuple | None = None
    region_kind: str = 'paragraph'
    region_key: tuple | None = None
    policy: ObjectPolicy = ObjectPolicy.TRANSLATABLE
    rendered_bbox: tuple | None = None
    continuation_page: int | None = None
    layout_font_size: float | None = None
    continuation_lines: tuple[str, ...] = ()
    written_boxes: tuple = ()
    origin: str = 'native'
    polygon: tuple = ()
    ocr_model: str = ''
    background_color: tuple = (255, 255, 255, 255)
    raster_boxes: tuple = ()


@dataclass
class PdfPageInfo:
    size: tuple[float, float]
    bounds: tuple[float, float, float, float]
    rotation: int
    annotations: int
    non_text: tuple


@dataclass
class ExtractedPage:
    """Shared native/OCR extraction result for the single PDF writer."""
    segments: list[PdfSegment] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    object_states: list[dict] = field(default_factory=list)
