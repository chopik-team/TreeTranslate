from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class DevicePreference(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    AUTO = "auto"


class PerformanceProfile(StrEnum):
    ECONOMY = "economy"
    FAST = "fast"
    BALANCED = "balanced"
    TURBO = "turbo"
    MAXIMUM = "maximum"
    AUTOMATIC = "automatic"


class PairKind(StrEnum):
    DIRECT = "direct"
    PIVOT = "pivot"


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    text: str
    source_language: str
    target_language: str
    device_preference: DevicePreference = DevicePreference.AUTO
    performance_profile: PerformanceProfile = PerformanceProfile.AUTOMATIC
    request_id: str = field(default_factory=lambda: uuid4().hex)
    cpu_threads: int | None = None
    domain: str = 'general'
    context: str = ''
    document_type: str = ''
    context_profile: object = None
    knowledge_snapshot: object = None
    segment_type: str = ''
    context_router: object = None


@dataclass(frozen=True, slots=True)
class TranslationResult:
    translated_text: str
    source_language: str
    target_language: str
    backend: str
    device: str
    duration_ms: float
    route_reason: str
    fallback_used: bool
    request_id: str
    model_ids: tuple[str, ...] = ()
    compute_type: str = "none"
    knowledge_source: str = 'model'
    glossary_hits_count: int = 0
    pack_ids: tuple[str, ...] = ()
    domain: str = 'general'
    constraint_status: str = 'none'
    question_kind: str = ''


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    direct_pairs: frozenset[tuple[str, str]] = frozenset()
    pivot_pairs: frozenset[tuple[str, str]] = frozenset()
    languages: frozenset[str] = frozenset()
    devices: frozenset[str] = frozenset({"cpu", "cuda"})

    def supports_pair(self, source: str, target: str, kind: PairKind = PairKind.DIRECT) -> bool:
        if source == target:
            return False
        if kind == PairKind.PIVOT:
            return (source, target) in self.pivot_pairs
        return (source, target) in self.direct_pairs or {source, target} <= self.languages


@dataclass(frozen=True, slots=True)
class InferenceOptions:
    device: str
    compute_type: str
    threads: int
    beam_size: int
    batch_tokens: int
    max_input_tokens: int
    max_decoding_length: int


@dataclass(frozen=True, slots=True)
class BackendOutput:
    text: str
    model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TranslationMetric:
    backend: str
    language_pair: str
    text_length: int
    latency_ms: float
    device: str
    success: bool
    fallback: bool
    error_type: str | None = None
