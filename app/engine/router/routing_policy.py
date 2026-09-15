from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.engine.types import PerformanceProfile


@dataclass(frozen=True, slots=True)
class ProfilePolicy:
    prefer_quality: bool
    allow_quality: bool
    auto_gpu: bool
    threads: int
    beam_size: int
    batch_tokens: int
    max_input_tokens: int
    max_decoding_length: int


class RoutingPolicy:
    """Measured defaults; evidence and hardware scope live with the configuration."""

    def __init__(self, path: Path | None = None) -> None:
        path = path or Path(__file__).resolve().parents[2] / "config" / "engine_profiles.json"
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.idle_timeout_seconds = float(self.data["idle_timeout_seconds"])
        self.max_text_chars = int(self.data["max_text_chars"])
        self.quality_pairs = {tuple(pair) for pair in self.data["quality_pairs"]}
        self.argos_preferred_pairs = {tuple(pair) for pair in self.data["argos_preferred_pairs"]}

    def profile(self, profile: PerformanceProfile, threads: int | None = None) -> ProfilePolicy:
        data = dict(self.data["profiles"][profile.value])
        data.update(self.data["decoding"])
        available = os.cpu_count() or 1
        requested = threads if threads is not None else data["threads"]
        data["threads"] = max(1, min(available, requested))
        return ProfilePolicy(**data)
