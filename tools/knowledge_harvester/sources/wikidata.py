from ..models import RawConcept, HarvestError


def parse(record):
    if not isinstance(record, dict) or not str(record.get('id', '')).startswith('Q'):
        raise HarvestError('Ожидается Wikidata entity JSON.')
    languages = {'zh', 'zh-hans', 'zh-hant', 'zh-cn', 'zh-tw', 'ru', 'en'}
    labels = {k: v['value'] for k, v in record.get('labels', {}).items() if k in languages}
    aliases = {k: [v['value'] for v in values] for k, values in record.get('aliases', {}).items() if k in languages}
    descriptions = {k: v['value'] for k, v in record.get('descriptions', {}).items() if k in languages}
    relations = []
    for prop in ('P31', 'P279', 'P361', 'P2579'):
        for statement in record.get('claims', {}).get(prop, []):
            if statement.get('rank') == 'deprecated':
                continue
            value = statement.get('mainsnak', {}).get('datavalue', {}).get('value', {})
            if isinstance(value, dict) and value.get('id'):
                relations.append((prop, 'wikidata:' + value['id']))
    return RawConcept(record['id'], 'wikidata:' + record['id'], labels, aliases, descriptions,
                      relations=relations, metadata={'revision': record.get('lastrevid'), 'modified': record.get('modified')})
