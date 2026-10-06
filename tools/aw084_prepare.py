"""Developer-only official-source retrieval and local CT2 conversion."""
import argparse,json,os,sys,time
from hashlib import sha256
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw084';BUILD=ROOT/'build/aw084';QA.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
SOURCES={'m2m100-1.2b':'facebook/m2m100_1.2B','madlad-3b':'google/madlad400-3b-mt'}

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def audit():
    from huggingface_hub import HfApi
    api=HfApi();rows=[]
    for name,upstream in SOURCES.items():
        info=api.model_info(upstream,files_metadata=True)
        files=[dict(path=s.rfilename,size=s.size,lfs=s.lfs) for s in info.siblings]
        rows.append(dict(id=name,upstream=upstream,revision=info.sha,license=info.card_data.get('license'),
            files=files,source=f'https://huggingface.co/{upstream}/tree/{info.sha}'))
        print(name,info.sha,[(f['path'],f['size']) for f in files],flush=True)
    (QA/'candidate_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n','utf-8')
    paths=[ROOT/'assets/knowledge/manifest.json',ROOT/'qa/aw083/body_dimensions_gold.json',ROOT/'vendor/models/models_manifest.json',ROOT/'requirements-runtime.txt']
    knowledge=json.loads(paths[0].read_text('utf-8'))
    paths += [ROOT/'assets/knowledge'/p['file'] for p in knowledge['packs']]
    state={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in paths}
    (QA/'frozen_state.json').write_text(json.dumps(dict(files=state,TM='isolated empty per candidate',user_glossary='isolated empty per candidate',
        baseline='AW0.8.3 accepted 5582364caf97, unchanged',decode=dict(beam_size=4,max_decoding_length=512,batch_tokens=2048)),indent=2)+'\n','utf-8')


def prepare(name):
    from huggingface_hub import snapshot_download
    row=next(r for r in json.loads((QA/'candidate_inventory.json').read_text('utf-8')) if r['id']==name)
    source=BUILD/'sources'/name
    # Never retrieve duplicate Rust/JAX/GGUF representations of the weights.
    patterns=['config.json','generation_config.json','README.md','LICENSE*','NOTICE*','tokenizer*','special_tokens_map.json','vocab.json','sentencepiece.bpe.model','spiece.model','added_tokens.json']
    patterns += ['pytorch_model.bin'] if name.startswith('m2m') else ['model.safetensors','model-*.safetensors','model.safetensors.index.json']
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    started=time.perf_counter()
    snapshot_download(row['upstream'],revision=row['revision'],local_dir=source,allow_patterns=patterns,max_workers=3)
    row['download_seconds']=time.perf_counter()-started
    row['original_files']=[dict(path=p.name,size=p.stat().st_size,sha256=digest(p)) for p in source.iterdir() if p.is_file()]
    (QA/(name+'-source.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n','utf-8')
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from ctranslate2.converters import TransformersConverter
    from transformers import AutoTokenizer
    output=BUILD/'candidates'/name
    tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,use_fast=False)
    tokenizer.save_pretrained(output/'tokenizer')
    if name.startswith('m2m'):
        (output/'tokenizer/languages.json').write_text(json.dumps(sorted(tokenizer.lang_code_to_id)),'utf-8')
    started=time.perf_counter()
    converter=TransformersConverter(str(source),load_as_float16=True,trust_remote_code=False)
    converter.convert(str(output/'model'),quantization='int8')
    row['conversion_seconds']=time.perf_counter()-started
    row['converted_files']=[dict(path=p.relative_to(output).as_posix(),size=p.stat().st_size,sha256=digest(p)) for p in output.rglob('*') if p.is_file()]
    row['quantization']='int8';row['path']=str(output);row['format']='ctranslate2'
    (output/'provenance.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n','utf-8')
    (QA/(name+'-prepared.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('PREPARED',name,'bytes',sum(f['size'] for f in row['converted_files']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['audit',*SOURCES]);args=parser.parse_args()
    audit() if args.action=='audit' else prepare(args.action)
