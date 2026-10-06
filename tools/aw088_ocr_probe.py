"""Bounded development-only OCR probe through production HybridPdfExtractor."""
from dataclasses import asdict
from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw088_prepare import QA,ZIP,save
from app.documents.control import JobControl
from app.documents.job import DocumentConfig
from app.documents.pdf_document import PdfDocument
from app.ocr.router.ocr_router import OcrRouter
from app.ocr.pdf_extractor import HybridPdfExtractor


def run():
    manifest=json.loads((QA/'development_manifest.json').read_text('utf8'))
    docs=[d for d in manifest['documents'] if not d['native_chars'] and 0<d['pages']<=2][:2]
    control=JobControl();router=OcrRouter(checkpoint=control.checkpoint);records=[];start=perf_counter()
    try:
        with TemporaryDirectory(prefix='TreeTranslate-aw088-ocr-') as root,ZipFile(ZIP) as archive:
            for n,item in enumerate(docs):
                router.last_results=[]
                path=Path(root)/f'{n}.pdf';path.write_bytes(archive.read(item['member']))
                extractor=HybridPdfExtractor(router,DocumentConfig(source='zh',target='ru'),control.checkpoint)
                t=perf_counter()
                try:
                    document=PdfDocument(path,checkpoint=control.checkpoint,extractor=extractor)
                    records.append(dict(member=item['member'],sha256=item['sha256'],pages=len(document.pages),seconds=perf_counter()-t,
                        ocr_used=extractor.ocr_used,segments=[dict(text=s.text,confidence=s.confidence,kind=s.ocr_kind) for s in document.segments],
                        routing=list(router.last_results)))
                    del document
                except Exception as error:
                    records.append(dict(member=item['member'],sha256=item['sha256'],seconds=perf_counter()-t,error=type(error).__name__,code=str(getattr(error,'code',getattr(error,'kind',''))),message=str(error),routing=list(router.last_results)))
    finally:router.shutdown()
    save('ocr_probe.json',dict(policy='Production PaddleOCR Auto device/HybridPdfExtractor region policy; development only; max two PDFs/four pages; not trained automatically',
        records=records,seconds=perf_counter()-start,automatic_verified=0))
    print('OCR probe',len(records),round(perf_counter()-start,2),flush=True)

if __name__=='__main__':run()
