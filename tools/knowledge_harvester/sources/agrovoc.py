"""Streaming JSON-LD node subset (one concept per JSONL record).

Expanded SKOS JSON-LD is accepted; arbitrary compact contexts and RDF/XML are
not silently guessed. A local RDF exporter must produce this documented subset.
"""
from ..models import RawConcept, HarvestError

SKOS = 'http://www.w3.org/2004/02/skos/core#'


def parse(record):
    if not isinstance(record, dict) or not record.get('@id'):
        raise HarvestError('Нужен expanded SKOS JSON-LD concept node.')
    labels, aliases, descriptions = {}, {}, {}
    for name, destination in [('prefLabel', labels), ('altLabel', aliases), ('definition', descriptions)]:
        for value in record.get(SKOS + name, []):
            lang, text = value.get('@language'), value.get('@value')
            if lang not in ('zh', 'ru', 'en'):
                continue
            if name == 'altLabel':
                destination.setdefault(lang, []).append(text)
            elif lang in destination and destination[lang] != text:
                raise HarvestError('Несколько preferred labels одного языка; требуется review.')
            else:
                destination[lang] = text
    uid = record['@id']
    relations = [('broader', 'agrovoc:' + v['@id']) for v in record.get(SKOS + 'broader', [])]
    mappings = []
    for value in record.get(SKOS + 'exactMatch', []):
        url = value.get('@id', '')
        if url.startswith(('http://www.wikidata.org/entity/Q', 'https://www.wikidata.org/entity/Q')):
            mappings.append('wikidata:' + url.rsplit('/', 1)[1])
    return RawConcept(uid, 'agrovoc:' + uid, labels, aliases, descriptions, relations=relations, mappings=mappings)
