from abc import ABC, abstractmethod
from threading import Event

from app.engine.errors import TranslationCancelledError
from app.engine.types import BackendCapabilities, BackendOutput, InferenceOptions, PairKind, TranslationRequest


def check_cancelled(cancelled: Event) -> None:
    if cancelled.is_set():
        raise TranslationCancelledError()


class BaseBackend(ABC):
    name: str

    @abstractmethod
    def capabilities(self) -> BackendCapabilities: ...

    def supports_pair(self, source: str, target: str, kind: PairKind = PairKind.DIRECT) -> bool:
        return self.capabilities().supports_pair(source, target, kind)

    @abstractmethod
    def translate(self, request: TranslationRequest, kind: PairKind,
                  options: InferenceOptions, cancelled: Event) -> BackendOutput: ...

    @abstractmethod
    def shutdown(self) -> None: ...
