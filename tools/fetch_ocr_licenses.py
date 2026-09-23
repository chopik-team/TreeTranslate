"""Build-only retrieval of omitted license texts from hash-verified PyPI sdists."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--allow-network',action='store_true')
    if not parser.parse_args().allow_network:parser.error('Explicit --allow-network required')
    root=Path(__file__).resolve().parents[1]/'vendor/licenses/ocr-runtime'
    inventory=json.loads((root/'inventory.json').read_text('utf-8'));records=[]
    for dist in inventory:
        if dist['files']:continue
        name,version=dist['name'],dist['version']
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:
            info=json.load(response)
        source=next(f for f in info['urls'] if f['packagetype']=='sdist')
        with urllib.request.urlopen(source['url'],timeout=60) as response:data=response.read(100_000_000)
        assert sha256(data).hexdigest()==source['digests']['sha256']
        files=[]
        with tarfile.open(fileobj=BytesIO(data)) as archive:
            for member in archive.getmembers():
                if not member.isfile() or member.size>2_000_000 or not any(s in Path(member.name).name.lower() for s in ('licen','copying','notice')):continue
                relative=Path(*Path(member.name).parts[1:])
                if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe archive path')
                output=root/name/'upstream'/relative
                output.parent.mkdir(parents=True,exist_ok=True)
                output.write_bytes(archive.extractfile(member).read());files.append(relative.as_posix())
        if not files and name in ('bce-python-sdk','latex2mathml'):
            repo='baidubce/bce-sdk-python' if name=='bce-python-sdk' else 'roniemartinez/latex2mathml'
            with urllib.request.urlopen(f'https://api.github.com/repos/{repo}/commits?path=LICENSE&per_page=1',timeout=30) as response:
                revision=json.load(response)[0]['sha']
            url=f'https://raw.githubusercontent.com/{repo}/{revision}/LICENSE'
            with urllib.request.urlopen(url,timeout=30) as response:license_data=response.read()
            output=root/name/'upstream/LICENSE';output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(license_data)
            files.append('LICENSE')
            records.append(dict(name=name,source=url,sha256=sha256(license_data).hexdigest(),note='Official repository license revision; sdist omits license text'))
        records.append(dict(name=name,version=version,source=source['url'],sha256=source['digests']['sha256'],files=files))
    (root/'upstream-licenses.json').write_text(json.dumps(records,indent=2),'utf-8')
    print([(r['name'],r.get('files', ['official repository license'])) for r in records])


if __name__=='__main__':main()
