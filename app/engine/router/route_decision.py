from dataclasses import dataclass

from app.engine.types import PairKind, PerformanceProfile


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    backend: str
    kind: PairKind


@dataclass(frozen=True, slots=True)
class RouteDecision:
    backend: str
    reason: str
    fallback_chain: tuple[RouteCandidate, ...]
    device: str
    profile: PerformanceProfile
    kind: PairKind = PairKind.DIRECT
