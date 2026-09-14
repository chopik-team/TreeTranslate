from dataclasses import dataclass
from enum import Enum, auto


class JobState(Enum):
    EMPTY = auto()
    DRAGGING = auto()
    SCANNING = auto()
    READY = auto()
    TRANSLATING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    ERROR = auto()
    CANCELLED = auto()


@dataclass(slots=True)
class TranslationProgress:
    percent: int = 0
    processed: int = 0
    total: int = 14
    current_file: str = "—"
    elapsed_seconds: int = 0
