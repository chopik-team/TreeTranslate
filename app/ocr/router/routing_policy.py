from dataclasses import dataclass
from app.ocr.config import configuration, profile


@dataclass(frozen=True)
class RouteDecision:
    backend: str
    reason: str
    indicators: dict


def decide(indicators, performance_profile):
    thresholds = configuration()['complexity']
    complex_page = any(indicators.get(k, 0) >= thresholds[k] for k in thresholds)
    structure = complex_page and profile(performance_profile)['structure']
    return RouteDecision('structure' if structure else 'paddle',
                         'complex layout' if structure else 'simple page or lightweight profile', indicators)
