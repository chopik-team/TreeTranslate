"""Real backend measurements on explicit synthetic fixtures; never user text."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest, DevicePreference, PerformanceProfile


def main():
    engine=create_translation_engine()
    rows=[]
    formats=['TTTERM{:04d}','__TTTERM{:04d}__','ZXQ{:04d}QXZ']
    try:
        for backend,source,target in [('argos','en','ru'),('argos','ru','en'),('m2m100','zh','ru'),('m2m100','en','ru')]:
            for fmt in formats:
                tokens=[fmt.format(i) for i in (1,2)]
                for count in (1,2):
                    text={'en':f'Replace the {tokens[0]} before starting.' if count==1 else f'Replace the {tokens[0]} and check the {tokens[1]}.',
                          'ru':f'Замените {tokens[0]} перед запуском.' if count==1 else f'Замените {tokens[0]} и проверьте {tokens[1]}.',
                          'zh':f'启动前更换{tokens[0]}。' if count==1 else f'更换{tokens[0]}并检查{tokens[1]}。'}[source]
                    result=engine.translate(TranslationRequest(text,source,target,DevicePreference.AUTO,PerformanceProfile.BALANCED),backend_only=backend)
                    valid=all(result.translated_text.count(token)==1 for token in tokens[:count])
                    rows.append(dict(backend=backend,source_language=source,target_language=target,format=fmt,count=count,
                        input=text,output=result.translated_text,intact=valid,device=result.device,model_ids=result.model_ids))
                    print(backend,source,fmt,count,valid,flush=True)
    finally:
        engine.shutdown()
    output=Path('docs/qa/aw071/placeholders.json');output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')


if __name__=='__main__':main()
