"""Real OCR -> existing TranslationRouter -> existing PDF writer, both renderers."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.documents.control import JobControl
from app.documents.job import DocumentConfig,DocumentJob
from app.documents.scanner import scan_sources
from app.engine.factory import create_translation_engine
from app.engine.types import DevicePreference,PerformanceProfile
from tools.pdf_fixtures import make_pdf,render
from tools.ocr_fixtures import rasterize,make_mixed
import app.documents.job as jobs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',nargs='+',default=['automotive','silverstone','english','rotated','mixed'])
    args=parser.parse_args()
    root=Path('output/pdf/aw062').resolve();root.mkdir(parents=True,exist_ok=True)
    qa=Path('docs/qa/aw062');qa.mkdir(parents=True,exist_ok=True)
    build=Path('build/aw062');build.mkdir(parents=True,exist_ok=True)
    reportpath=qa/'end-to-end.json'
    reports=json.loads(reportpath.read_text('utf-8')) if reportpath.exists() else []
    engine=create_translation_engine();docs=[]
    original=jobs.open_document
    def capture(*a,**kw):
        doc=original(*a,**kw);docs.append(doc);return doc
    jobs.open_document=capture
    cachepath=build/'translation-cache.json'
    cache=json.loads(cachepath.read_text('utf-8')) if cachepath.exists() else {}
    fresh=0;cached=0
    def translate(request,cancel):
        nonlocal fresh,cached
        key=json.dumps([request.text,request.source_language,request.target_language,str(request.device_preference),str(request.performance_profile)],ensure_ascii=False)
        if key in cache:
            from types import SimpleNamespace
            cached+=1
            return SimpleNamespace(translated_text=cache[key])
        result=engine.translate(request,cancel);fresh+=1
        cache[key]=result.translated_text
        cachepath.write_text(json.dumps(cache,ensure_ascii=False),'utf-8')
        return result
    try:
        for name in args.cases:
            if name in ('automotive','silverstone'):
                source=Path('tests/fixtures/pdf')/(name+'.pdf')
                scan=build/(name+'-scan.pdf')
                if not scan.exists():rasterize(source,scan)
                language='zh' if name=='automotive' else 'ru'
                target='ru' if name=='automotive' else 'en'
            elif name=='mixed':
                scan=make_mixed(build/'mixed.pdf');language='en';target='ru'
            else:
                source=make_pdf(build/'english-native.pdf','Save the configuration file before restarting the application.',lines=2,background=False)
                scan=rasterize(source,build/(name+'-scan.pdf'),angle=90 if name=='rotated' else 0)
                language='auto';target='ru'
            digest=sha256(scan.read_bytes()).hexdigest();control=JobControl();warnings=[];progress=[]
            last=''
            def update(p):
                nonlocal last
                progress.append(p)
                if p.stage!=last:
                    print(name,p.stage,flush=True);last=p.stage
            started=perf_counter();docs.clear();fresh=0;cached=0
            config=DocumentConfig(source=language,target=target,device=DevicePreference.AUTO,profile=PerformanceProfile.BALANCED,output=root)
            with engine.runtime.keep_warm():
                output,=DocumentJob(scan_sources([scan],control).files,config,control,translate,engine.languages.resolve,
                    update,warning=warnings.append,before_ocr=engine.runtime.release_models).run()
            doc=docs[-1];doc.validate(output)
            assert sha256(scan.read_bytes()).hexdigest()==digest
            render(output,qa/name/'pdfium')
            dest=qa/name/'poppler';dest.mkdir(parents=True,exist_ok=True)
            exe=Path('C:/Users/PC/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
            subprocess.run([str(exe),'-r','108','-png',str(output),str(dest/'page')],check=True,capture_output=True)
            row=dict(case=name,output=str(output),seconds=perf_counter()-started,original_pages=len(doc.pages),
                continuations=doc.continuation_count,segments=len(doc.segments),warnings=len(set(warnings)),source_sha256=digest,
                source_unchanged=True,renderers=['PDFium','Poppler'],fresh_translation_calls=fresh,cached_translation_calls=cached,
                stages=list(dict.fromkeys(p.stage for p in progress)))
            transcript=[{k:getattr(s,k) for k in ('text','translated','page','bbox','region_kind','available_bbox','written_boxes','policy','status','continuation_page')} for s in doc.segments]
            (qa/f'{name}-translated-corpus.json').write_text(json.dumps(transcript,ensure_ascii=False,indent=2),'utf-8')
            reports=[r for r in reports if r['case']!=name]+[row]
            reportpath.write_text(json.dumps(reports,indent=2),'utf-8')
            print(json.dumps(row),flush=True)
    finally:
        engine.shutdown();jobs.open_document=original


if __name__=='__main__':main()
