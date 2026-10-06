from dataclasses import dataclass, field
from enum import StrEnum
import json


def entry_metadata(entry):
    """Legacy notes remain free text; only a JSON object supplies metadata."""
    try:
        value = json.loads(entry.notes or '{}')
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


class Status(StrEnum):
    CONFIRMED='CONFIRMED'
    REVIEWED='REVIEWED'
    IMPORTED='IMPORTED'
    BUILTIN='BUILTIN'
    AUTO='AUTO'
    REJECTED='REJECTED'
    DISABLED='DISABLED'


class Mode(StrEnum):
    PREFERRED='PREFERRED'
    KEEP='KEEP'
    FORBIDDEN='FORBIDDEN'


TRUST={'CONFIRMED':1.,'REVIEWED':.9,'IMPORTED':.8,'BUILTIN':.8,'AUTO':.2,'REJECTED':0.,'DISABLED':0.}


@dataclass(frozen=True)
class GlossaryEntry:
    source_term: str
    target_term: str
    source_language: str
    target_language: str
    domain: str='general'
    case_sensitive: bool=True
    whole_word: bool=True
    priority: int=0
    notes: str=''
    status: str=Status.AUTO
    id: int=0
    source_normalized: str=''
    context: str=''
    origin: str='user'
    trust: float=.2
    created_at: str=''
    updated_at: str=''
    source_pack: str=''
    provenance: str=''
    mode: str=Mode.PREFERRED
    variants: tuple[str,...]=()
    forbidden_target_variants: tuple[str,...]=()


@dataclass(frozen=True)
class TermMatch:
    start: int
    end: int
    entry: GlossaryEntry
    store: str='user'


@dataclass(frozen=True)
class ConstraintPlan:
    text: str
    mapping: tuple[tuple[str,str],...]=()
    forbidden: tuple[str,...]=()
    matches: tuple[TermMatch,...]=()
