from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    supports_gpu: bool = False
    supports_cpu: bool = True
    supports_parallel_jobs: bool = False
    supports_streaming_text: bool = False
    supports_ocr: bool = False


class EngineStatus(Enum):
    UNINITIALIZED = auto()
    INITIALIZING = auto()
    READY = auto()
    BUSY = auto()
    PAUSED = auto()
    ERROR = auto()
    SHUTDOWN = auto()


class TranslationEngine(ABC):
    """Backend-neutral boundary. GUI code must depend only on services/controllers."""

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def translate_text(self, text: str, source: str, target: str) -> str: ...

    @abstractmethod
    def translate_file(self, path: Path, source: str, target: str) -> Path: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def cancel(self) -> None: ...

    @abstractmethod
    def capabilities(self) -> EngineCapabilities: ...

    @abstractmethod
    def get_status(self) -> EngineStatus: ...

    @abstractmethod
    def shutdown(self) -> None: ...
