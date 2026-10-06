"""Bounded repair: quantize original FP32 directly, retaining FP16 pilot evidence."""
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw084';CANDIDATES=ROOT/'build/aw084/candidates'
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'


def main(name):
    from ctranslate2.converters import TransformersConverter
    previous=json.loads((QA/f'{name}-prepared.json').read_text('utf-8'))
    output=CANDIDATES/(name+'-fp32-int8');source=ROOT/'build/aw084/sources'/name
    pilot=QA/'fp16-load-pilot';pilot.mkdir(exist_ok=True)
    for path in QA.glob(name+'-*.json'):
        shutil.copy2(path,pilot/path.name)
    shutil.copytree(Path(previous['path'])/'tokenizer',output/'tokenizer')
    started=time.perf_counter()
    TransformersConverter(str(source),load_as_float16=False,trust_remote_code=False).convert(str(output/'model'),quantization='int8')
    previous['conversion_seconds']=time.perf_counter()-started
    previous['path']=str(output);previous['conversion_input_dtype']='original FP32; no intermediate half precision'
    previous['supersedes']='fp16-load-pilot/'+name+'-prepared.json'
    files=[]
    for path in output.rglob('*'):
        if path.is_file():
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            files.append({'path':path.relative_to(output).as_posix(),'size':path.stat().st_size,'sha256':digest})
    previous['converted_files']=files
    (output/'provenance.json').write_text(json.dumps(previous,indent=2),'utf-8')
    (QA/f'{name}-prepared.json').write_text(json.dumps(previous,indent=2),'utf-8')
    manifest=json.loads((CANDIDATES/'models_manifest.json').read_text('utf-8'))
    for row in manifest['models']:
        if row['id']==name:row.update(path=output.name,files=files,size=sum(f['size'] for f in files))
    for path in [CANDIDATES/'models_manifest.json',QA/'candidate_manifest.json']:
        path.write_text(json.dumps(manifest,indent=2),'utf-8')
    print('RECONVERTED',name,sum(f['size'] for f in files),previous['conversion_seconds'],flush=True)


if __name__=='__main__':main(sys.argv[1])
