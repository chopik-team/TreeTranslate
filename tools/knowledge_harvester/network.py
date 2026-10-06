"""Only this module opens network connections; every call requires explicit opt-in."""
from pathlib import Path
import os
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from .models import HarvestError

USER_AGENT = 'TreeTranslate-KnowledgeHarvester/0.7.2 (https://github.com/chopik-team/TreeTranslate; developer preview)'


def download(url, destination, *, allow_network=False, max_bytes=64 * 1024 * 1024, dry_run=False):
    if not allow_network:
        raise HarvestError('Сеть запрещена: нужен --allow-network.')
    if urlsplit(url).scheme != 'https':
        raise HarvestError('Допускается только HTTPS.')
    destination = Path(destination)
    if destination.exists():
        raise HarvestError('Файл уже существует; используйте pinned cache или новый путь.')
    if dry_run:
        return {'url': url, 'destination': str(destination), 'max_bytes': max_bytes}
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            with urlopen(Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'}), timeout=60) as response:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HarvestError('Превышен лимит загрузки.')
                    output.write(chunk)
            output.flush(); os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'url': url, 'bytes': size, 'destination': str(destination)}
