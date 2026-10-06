"""Developer-only offline catalog seed builder, using already installed M2M100.

Runtime loads JSON only. Model output is a draft; reviewed overrides are merged
separately. Templates/markup/product identifiers are never sent for translation.
"""
import ast
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
CYR=re.compile('[А-Яа-яЁё]')
PROTECTED=re.compile(r'(<[^>]*>|\{\d+\}|TreeTranslate|CHOPIK Team|GPT-6|ChatGPT|M2M100|CTranslate2|SentencePiece|Argos Translate|PaddleOCR|PPStructure|DOCX|PDF|OCR|CPU|GPU|CUDA|VRAM|RAM|Auto|CC0|MIT|Apache-2.0|[\r\n]+)')


def source_keys():
    keys=set()
    for p in (ROOT/'app').rglob('*.py'):
        # Diagram abbreviations are translated document content, not UI copy.
        if (p.name in ('translation_mode.py','pdf_ocr_policy.py')
                or p in (ROOT/'app/knowledge/units.py', ROOT/'app/knowledge/safety.py', ROOT/'app/knowledge/objects.py', ROOT/'app/knowledge/directives.py', ROOT/'app/knowledge/references.py', ROOT/'app/knowledge/qualifiers.py', ROOT/'app/knowledge/questions.py',
                         ROOT/'app/knowledge/router.py', ROOT/'app/glossary/constraints.py', ROOT/'app/documents/run_metrics.py') or 'localization' in p.parts):
            continue
        tree=ast.parse(p.read_text('utf-8'))
        patterns = {id(n.args[0]) for n in ast.walk(tree) if isinstance(n,ast.Call) and n.args
                    and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
                    and n.func.value.id=='re'}
        for n in ast.walk(tree):
            if id(n) in patterns:continue
            if isinstance(n,ast.Constant) and isinstance(n.value,str) and CYR.search(n.value):
                keys.add(n.value)
            elif isinstance(n,ast.JoinedStr):
                values=[];count=0
                for v in n.values:
                    if isinstance(v,ast.Constant):values.append(v.value)
                    else:values.append('{'+str(count)+'}');count+=1
                value=''.join(values)
                if CYR.search(value):keys.add(value)
    # App-owned metadata shown by About; official license bodies are excluded.
    meta=json.loads((ROOT/'assets/language-support.json').read_text('utf-8'))
    keys.add(meta['routing_note'])
    html=(ROOT/'assets/licenses/third-party.html').read_text('utf-8')
    keys.update(part for part in re.findall(r'>([^<>]+)<',html) if CYR.search(part))
    return sorted(k for k in keys if not k.startswith('(?') and '\\b' not in k)


def main():
    from app.engine.backends.m2m100_backend import M2M100Backend
    from app.engine.runtime.model_manager import ModelManager
    from app.engine.runtime.device_manager import DeviceManager
    from app.engine.router.routing_policy import RoutingPolicy
    from app.engine.types import InferenceOptions
    from app.engine.runtime.cuda_libraries import load_cuda_libraries
    from app.engine.runtime.offline import offline_scope
    out=ROOT/'assets/locales';out.mkdir(exist_ok=True)
    keys=source_keys()
    (out/'ru-RU.json').write_text(json.dumps(dict.fromkeys(keys,None),ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'ru-RU.json').write_text(json.dumps({k:k for k in keys},ensure_ascii=False,indent=2),encoding='utf-8')
    load_cuda_libraries()
    from app.config.paths import MODELS_DIR
    backend=M2M100Backend(ModelManager(MODELS_DIR))
    try:
        with offline_scope():
            backend._load(InferenceOptions('cuda','int8_float16',8,4,2048,192,512))
            tokenizer=backend._tokenizer
            for target,locale in [('en','en-US'),('de','de-DE'),('es','es-ES'),('fr','fr-FR'),('zh','zh-CN'),('ja','ja-JP')]:
                path=out/(locale+'.json')
                values=json.loads(path.read_text('utf-8')) if path.is_file() else {}
                missing=[key for key in keys if key not in values]
                fragments=sorted({part.strip() for key in missing for part in PROTECTED.split(key)
                                  if part and CYR.search(part) and not part.startswith('<')})
                translated={}
                for offset in range(0,len(fragments),24):
                    chunk=fragments[offset:offset+24]
                    tokens=[tokenizer.source_tokens(tokenizer.encode(text),'ru') for text in chunk]
                    results=backend._translator.translate_batch(tokens,target_prefix=[[f'__{target}__']]*len(tokens),
                        beam_size=4,max_batch_size=2048,batch_type='tokens',max_input_length=0,max_decoding_length=512)
                    for source,result in zip(chunk,results):translated[source]=tokenizer.decode(result.hypotheses[0])
                    print(locale,offset+len(chunk),'/',len(fragments),flush=True)
                for key in missing:
                    values[key]=''.join((part[:len(part)-len(part.lstrip())]+translated[part.strip()]+part[len(part.rstrip()):])
                                       if part.strip() in translated else part for part in PROTECTED.split(key))
                (out/(locale+'.json')).write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
                if target=='en':(out/'en-GB.json').write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:backend.shutdown()


if __name__=='__main__':main()
