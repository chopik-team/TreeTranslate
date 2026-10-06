"""Wiktextract-style JSONL subset. Import only; no HTML or wiki-template parser."""
from ..models import RawConcept, HarvestError
from ..provenance import digest_json


def parse(record):
    if not isinstance(record, dict) or not record.get('word') or record.get('lang_code') not in ('zh', 'ru', 'en'):
        raise HarvestError('Нужен word/lang_code structured Wiktionary record.')
    if not record.get('source_record_id'):
        raise HarvestError('Нужна ссылка на исходную страницу/ревизию Wiktionary.')
    language = record['lang_code']
    aliases = [v['form'] for v in record.get('forms', []) if isinstance(v, dict) and v.get('form')]
    # Senses remain evidence for review. Translation lists are not concept equivalence.
    definitions = [g for sense in record.get('senses', []) for g in sense.get('glosses', [])]
    uid = str(record['source_record_id']) + ':' + digest_json(record)[:16]
    return RawConcept(uid, 'wiktionary:' + uid, {language: record['word']}, {language: aliases},
                      definitions=definitions, domain_hints=record.get('categories', []),
                      metadata={'extractor_revision': record.get('extractor_revision', ''), 'review_only': True})
