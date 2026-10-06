import re
from .models import LicenseStatus, HarvestError

SUPPORTED = {'CC0-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0'}
REQUIRED = ('source_id', 'source_url', 'acquired_at', 'revision', 'license', 'redistribution_status',
            'license_url', 'license_checked_at', 'attribution', 'independence_group', 'languages')


def validate_source(source):
    if not isinstance(source, dict) or any(not source.get(k) for k in REQUIRED):
        raise HarvestError('Неполные сведения об источнике/лицензии.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', source['source_id']):
        raise HarvestError('Некорректный source_id.')
    if source['redistribution_status'] not in set(LicenseStatus):
        raise HarvestError('Неизвестный статус лицензии.')
    if not isinstance(source['languages'], list) or not source['languages']:
        raise HarvestError('Нужен список языков лицензированного набора.')
    if source['redistribution_status'] == LicenseStatus.APPROVED and source['license'] not in SUPPORTED:
        raise HarvestError('Лицензия требует отдельной проверки совместимости.')
    return source


def approved(source):
    return source['redistribution_status'] == LicenseStatus.APPROVED and source['license'] in SUPPORTED


def require_approved(source):
    validate_source(source)
    if not approved(source):
        raise HarvestError('Источник не одобрен для перераспространения.')
