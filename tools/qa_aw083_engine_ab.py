"""QA only: compare existing resources; production routing is untouched."""
import sys,json,time
from pathlib import Path
ROOT=Path('C:/TreeTranslate');sys.path.insert(0,str(ROOT))
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.engine import TranslationMemoryEngine
gold=json.loads((ROOT/'qa/aw083/body_dimensions_gold.json').read_text('utf-8'))
engine=create_translation_engine(memory=TranslationMemoryEngine(ROOT/'build/aw083-quality/ab-tm.db'),
    glossary=GlossaryEngine(ROOT/'build/aw083-quality/ab-glossary.db',builtin_paths=bundled_paths()))
sources=list(dict.fromkeys([x['source'] for x in gold['semantic_review_cases']]+list(gold['names'])+
    ['机罩铰链孔','前减震器孔','后悬架弹簧孔','雨刮器电机支架孔']))
rows=[]
try:
    for source in sources:
        row={'source':source}
        for name in ('direct','pivot','knowledge'):
            started=time.perf_counter()
            try:
                if name=='pivot':
                    en=engine.router.translate(TranslationRequest(source,'zh','en'),backend_only='m2m100')
                    result=engine.router.translate(TranslationRequest(en.translated_text,'en','ru'),backend_only='argos')
                    row['pivot_english']=en.translated_text
                elif name=='direct':result=engine.router.translate(TranslationRequest(source,'zh','ru'),backend_only='m2m100')
                else:result=engine.translate(TranslationRequest(source,'zh','ru',domain='automotive'))
                row[name]={'text':result.translated_text,'seconds':time.perf_counter()-started,'backend':result.backend,'models':result.model_ids}
            except Exception as e:row[name]={'error':type(e).__name__,'seconds':time.perf_counter()-started}
        rows.append(row);print(len(rows),len(sources),flush=True)
finally:
    engine.shutdown()
    (ROOT/'qa/aw083/engine_ab.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n','utf-8')
