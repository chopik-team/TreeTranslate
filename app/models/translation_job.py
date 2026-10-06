from dataclasses import dataclass, field
from time import monotonic
from enum import Enum, auto


class JobState(Enum):
    IDLE = auto()
    DRAGGING = auto()
    SCANNING = auto()
    READY = auto()
    TRANSLATING = auto()
    PAUSED = auto()
    CANCELLING = auto()
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
    file_index: int = 0
    file_total: int = 0
    eta_seconds: int | None = None
    stage: str = ''
    page_index: int = 0
    page_total: int = 0
    # Heartbeat replacements retain the time of the last real worker update.
    sampled_at: float = field(default_factory=monotonic, repr=False, compare=False)
    eta_scope: str = 'document'
    source_path: str = ''
    file_percent: int = 0
