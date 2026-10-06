from dataclasses import dataclass, field
from enum import StrEnum


class LicenseStatus(StrEnum):
    APPROVED = 'APPROVED_FOR_REDISTRIBUTION'
    REVIEW = 'REVIEW_REQUIRED'
    BLOCKED = 'NOT_REDISTRIBUTABLE'
    UNKNOWN = 'UNKNOWN'


class LinkType(StrEnum):
    DIRECT = 'DIRECT_CONCEPT'
    CROSS_SOURCE = 'CROSS_SOURCE_CONCEPT'
    PIVOT = 'ENGLISH_PIVOT_EXACT'
    AMBIGUOUS = 'ENGLISH_PIVOT_AMBIGUOUS'
    MACHINE = 'MACHINE_CANDIDATE'


@dataclass
class RawConcept:
    source_record_id: str
    concept_id: str
    labels: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, list[str]] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)
    definitions: list[str] = field(default_factory=list)
    relations: list[tuple[str, str]] = field(default_factory=list)
    domain_hints: list[str] = field(default_factory=list)
    mappings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class CanonicalConcept:
    concept_id: str
    records: list[dict]


class HarvestError(ValueError):
    """Safe developer diagnostic without raw source blobs."""
