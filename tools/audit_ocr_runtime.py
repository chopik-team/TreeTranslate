"""Build-only reproducibility/license inventory from the dedicated OCR environment."""
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil


def main():
    root=Path(__file__).resolve().parents[1]
    output=root/'vendor/licenses/ocr-runtime'
    output.mkdir(parents=True,exist_ok=True)
    records=[];lock=[]
    for dist in sorted(metadata.distributions(),key=lambda d:d.metadata['Name'].lower()):
        name=dist.metadata['Name']; version=dist.version
        lock.append(f'{name}=={version}')
        files=[];size=0
        for item in dist.files or ():
            path=Path(dist.locate_file(item))
            if path.is_file():size+=path.stat().st_size
            if any('licen' in part.lower() or 'copying' in part.lower() for part in item.parts) and path.is_file():
                dest=output/name/Path(*[p for p in item.parts if p not in ('..','.')])
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,dest)
                files.append(dest.relative_to(root).as_posix())
        records.append(dict(name=name,version=version,license=dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                            classifiers=[c for c in dist.metadata.get_all('Classifier',[]) if c.startswith('License')],
                            files=files,installed_bytes=size))
    (root/'requirements-ocr-lock.txt').write_text('\n'.join(lock)+'\n','utf-8')
    (output/'inventory.json').write_text(json.dumps(records,indent=2),'utf-8')
    print('packages',len(records),'installed_bytes',sum(r['installed_bytes'] for r in records))


if __name__=='__main__':main()
