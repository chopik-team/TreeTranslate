"""Real document QA; source text appears only in explicit local QA corpus, never runtime logs."""
import argparse
import json
from pathlib import Path
from hashlib import sha256
from dataclasses import asdict
from time import monotonic
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import socket
import pypdfium2 as pdfium
from app.documents.control import JobControl
from app.documents.job import DocumentJob,DocumentConfig
from app.documents.scanner import scan_sources
from app.engine.factory import create_translation_engine
from app.engine.types import DevicePreference,PerformanceProfile
from tools.pdf_fixtures import render
import app.documents.job as job_module


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fresh',action='store_true');args=parser.parse_args()
    root=Path('output/pdf/aw061').resolve();root.mkdir(parents=True,exist_ok=True)
    qa=Path('docs/qa/aw061');qa.mkdir(parents=True,exist_ok=True)
    cachepath=Path('build/aw061/inference-cache.json')
    cache=json.loads(cachepath.read_text(encoding='utf-8')) if cachepath.exists() and not args.fresh else {}
    engine=create_translation_engine();reports=[];documents=[]
    original_open=job_module.open_document
    def capture(*args):
        doc=original_open(*args);documents.append(doc);return doc
    job_module.open_document=capture
    def offline(*args,**kwargs):raise AssertionError('Network attempted during translation')
    socket.getaddrinfo=offline;socket.create_connection=offline
    def translate(request,cancel):
        key=json.dumps([request.text,request.source_language,request.target_language,str(request.device_preference),str(request.performance_profile)],ensure_ascii=False)
        if key not in cache:
            result=engine.translate(request,cancel);cache[key]=result.translated_text
            cachepath.write_text(json.dumps(cache,ensure_ascii=False),encoding='utf-8')
            return result
        from types import SimpleNamespace
        return SimpleNamespace(translated_text=cache[key])
    try:
        for name,source,target in [('automotive','zh','ru'),('silverstone','ru','en')]:
            path=Path('tests/fixtures/pdf')/(name+'.pdf');digest=sha256(path.read_bytes()).hexdigest();control=JobControl();progress=[];warnings=[];started=monotonic()
            with engine.runtime.keep_warm():
                outputs=DocumentJob(scan_sources([path],control).files,DocumentConfig(source=source,target=target,output=root,device=DevicePreference.AUTO,profile=PerformanceProfile.MAXIMUM),control,translate,engine.languages.resolve,progress.append,warning=warnings.append).run()
            output=outputs[0];doc=documents[-1]
            assert digest==sha256(path.read_bytes()).hexdigest()
            for tag,p in [('input',path),('output',output)]:
                dest=qa/name/tag
                render(p,dest/'pdfium')
                (dest/'poppler').mkdir(parents=True,exist_ok=True)
                exe=Path('C:/Users/PC/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
                subprocess.run([str(exe),'-r','108','-png',str(p),str(dest/'poppler/page')],check=True,capture_output=True)
            transcript=[{k:getattr(s,k) for k in ('page','block_id','text','translated','region_kind','available_bbox','rendered_bbox','continuation_page','policy','object_indices','written_boxes')} for s in doc.segments]
            (qa/(name+'-corpus.json')).write_text(json.dumps(transcript,ensure_ascii=False,indent=2),encoding='utf-8')
            with pdfium.PdfDocument(output) as pdf:
                annots=[];page_sizes=[]
                for i in range(len(pdf)):
                    page=pdf[i];page_sizes.append(page.get_size());annots.append(pdfium.raw.FPDFPage_GetAnnotCount(page));page.close()
            record=dict(name=name,source_sha256=digest,source_unchanged=True,output=str(output),pages=len(page_sizes),original_pages=len(doc.pages),annotation_counts=annots,segments=len(doc.segments),continuation_blocks=len(doc.continuations),warnings=len(set(warnings)),elapsed_seconds=round(monotonic()-started,2),stage=progress[-1].stage)
            reports.append(record);print(json.dumps(record),flush=True)
            (qa/'real-world.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    finally:
        engine.shutdown();job_module.open_document=original_open


if __name__=='__main__':main()
