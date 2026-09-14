from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TranslationEngine(ABC):
    """Boundary for a future local translation engine. No implementation yet."""

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
    def shutdown(self) -> None: ...
