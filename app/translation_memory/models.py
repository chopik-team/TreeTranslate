from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    CONFIRMED = 'CONFIRMED'
    IMPORTED = 'IMPORTED'
    REVIEWED = 'REVIEWED'
    AUTO = 'AUTO'
    REJECTED = 'REJECTED'


TRUST = {Status.CONFIRMED: 1.0, Status.REVIEWED: .9, Status.IMPORTED: .8,
         Status.AUTO: .2, Status.REJECTED: 0.0}


@dataclass(frozen=True)
class TranslationUnit:
    id: int
    source_language: str
    target_language: str
    source_text: str
    source_normalized: str
    target_text: str
    source_hash: str
    domain: str
    context: str
    origin: str
    status: str
    quality: float
    created_at: str
    updated_at: str
    last_used_at: str | None
    use_count: int
    document_type: str
    source_document: str
    engine_origin: str
    confirmed_by_user: bool
    is_template: bool


@dataclass(frozen=True)
class MemoryMatch:
    translation_unit_id: int
    source: str
    target: str
    score: float
    match_type: str
    language_pair: tuple[str, str]
    trust: float
    domain: str
    reusable: bool
    store: str = 'user'


# Compatibility import for the AW0.7 extension point; storage belongs to glossary.
from app.glossary.models import GlossaryEntry
