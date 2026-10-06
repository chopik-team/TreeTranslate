"""Read-only payload estimate, not an installer build or developer-tree total."""
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/aw084'


def compressed(paths):
    raw=packed=0
    for path in sorted(set(paths)):
        compressor=zlib.compressobj(6)
        with path.open('rb') as stream:
            while data:=stream.read(1024*1024):
                raw+=len(data);packed+=len(compressor.compress(data))
        packed+=len(compressor.flush())
    return {'raw_bytes':raw,'deflate6_bytes':packed,'files':len(set(paths))}


def runtime_files(environment,lockfiles,extras=()):
    from importlib.metadata import distributions
    site=ROOT/environment/'Lib/site-packages'
    names=set(extras)
    for lock in lockfiles:
        for line in (ROOT/lock).read_text('utf-8').splitlines():
            if '==' in line and not line.startswith('#'):
                names.add(re.sub('[-_.]+','-',line.split('==')[0]).lower())
    files=[];missing=[];found=set()
    for dist in distributions(path=[str(site)]):
        name=re.sub('[-_.]+','-',dist.metadata.get('Name','')).lower()
        if name not in names:continue
        found.add(name)
        for item in dist.files or ():
            path=Path(dist.locate_file(item)).resolve()
            if path.is_relative_to((ROOT/environment).resolve()) and path.is_file() and path.suffix!='.pyc':files.append(path)
    missing=sorted(names-found)
    return files,missing


def main():
    paths=[]
    for folder in ['app','assets','vendor/models','vendor/licenses','vendor/model-metadata']:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix!='.pyc' and '__pycache__' not in p.parts)
    production,missing=runtime_files('.venv',['requirements-runtime-lock.txt'],['argostranslate','nvidia-cublas-cu12'])
    ocr,ocr_missing=runtime_files('.venv-ocr',['requirements-ocr-lock.txt'])
    paths+=production+ocr+[ROOT/'main.py',ROOT/'THIRD_PARTY_NOTICES.md']
    # Two isolated interpreters for translation and OCR; base Python runtime once.
    import sysconfig
    base=Path(sys.base_prefix)
    paths.extend(p for folder in [base/'DLLs',base/'Lib'] for p in folder.rglob('*')
                 if p.is_file() and p.suffix!='.pyc' and 'site-packages' not in p.parts and '__pycache__' not in p.parts)
    paths.extend(p for p in base.glob('*.dll'))
    current=compressed(paths);results={}
    for model in ['m2m100-418m','m2m100-1.2b','madlad-3b']:
        if model=='m2m100-418m':
            record=next(r for r in json.loads((ROOT/'vendor/models/models_manifest.json').read_text('utf-8'))['models'] if r['id']=='m2m100-418m-int8')
            root=ROOT/'vendor/models'/record['path'];files=record['files'];original=None
        else:
            record=json.loads((QA/f'{model}-prepared.json').read_text('utf-8'));root=Path(record['path']);files=record['converted_files']
            original=sum(f['size'] for f in record['original_files'])
        payload=compressed([root/f['path'] for f in files])
        tokenizer=sum(f['size'] for f in files if f['path'].startswith('tokenizer/'))
        results[model]={'original_source_bytes':original,'converted_quantized_bytes':payload['raw_bytes'],
                        'tokenizer_bytes':tokenizer,'runtime_additions_bytes':0,'model_deflate6_bytes':payload['deflate6_bytes'],
                        'current_plus_candidate_deflate6_estimate_bytes':current['deflate6_bytes']+(0 if model=='m2m100-418m' else payload['deflate6_bytes']),
                        'baseline_retained':True}
        print(model,payload,flush=True)
    result={'method':'Streaming per-file DEFLATE level 6, counting all bytes; baseline retained. No installer authored.',
            'current_payload':current,'candidates':results,'missing_runtime_distributions':missing+ocr_missing,
            'limitation':'Estimate includes selected production wheels, OCR runtime, existing bundled model/assets/licenses, base Python. Excludes developer weights/environments/cache/tests. Not actual installer; packaging recipe is not yet defined. ZIP headers and launcher/bootstrap are not measured. Duplicate selected runtime DLLs remain conservative.'}
    (QA/'installer_impact.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')


if __name__=='__main__':main()
