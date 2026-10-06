"""Developer-only HF reference to distinguish engine issues from adapter issues."""
import json
import os
import time
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import torch
from transformers import AutoTokenizer,AutoModelForSeq2SeqLM

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'build/aw084/sources/madlad-3b'
torch.set_num_threads(8)
tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,use_fast=False)
started=time.perf_counter()
model=AutoModelForSeq2SeqLM.from_pretrained(source,local_files_only=True,torch_dtype=torch.float32)
model.eval()
rows=[]
gold=json.loads((ROOT/'qa/aw084/semantic_gold.json').read_text('utf-8'))['entries']
for case in [gold[i] for i in [2,9,55,56,73]]:
    start=time.perf_counter();inputs=tokenizer('<2ru> '+case['source_zh'],return_tensors='pt')
    with torch.inference_mode():
        generated=model.generate(**inputs,num_beams=4,max_new_tokens=128)
    row={'id':case['id'],'text':tokenizer.decode(generated[0],skip_special_tokens=True),'seconds':time.perf_counter()-start}
    rows.append(row);print(row,flush=True)
(ROOT/'qa/aw084/madlad-hf-reference.json').write_text(json.dumps({'purpose':'Developer-only original HF float32 sanity, not production',
    'max_new_tokens':128,'total_seconds':time.perf_counter()-started,'rows':rows},ensure_ascii=False,indent=2),'utf-8')
