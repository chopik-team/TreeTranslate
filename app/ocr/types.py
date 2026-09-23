from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OcrRequest:
    image: Any
    page_index: int = 0
    source_language: str = 'auto'
    device_preference: str = 'auto'
    performance_profile: str = 'automatic'
    region: tuple | None = None
    request_id: str = ''
    complexity: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OcrSegment:
    segment_id: str
    text: str
    polygon: tuple
    bbox: tuple
    confidence: float
    angle: int = 0
    language: str = 'auto'
    reading_order: int = 0
    page_index: int = 0
    source_region: tuple | None = None
    backend: str = 'paddle'
    model_id: str = ''


@dataclass
class OcrPageResult:
    page_index: int
    segments: list[OcrSegment]
    backend: str
    device: str
    duration: float
    warnings: list[str] = field(default_factory=list)
    layout_complexity: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    layout: list = field(default_factory=list)
    route_reason: str = ''
