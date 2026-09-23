"""Explicit offline developer QA. Corpus/transcripts are opt-in artifacts, not runtime logs."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from time import perf_counter
import unicodedata

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pypdfium2 as pdfium
from app.documents.pdf_document import PdfDocument
from app.documents.job import DocumentConfig
from app.ocr.pdf_extractor import HybridPdfExtractor
from app.ocr.router.ocr_router import OcrRouter
from app.ocr.postprocess.deduplication import intersection,area
from app.ocr.preprocess.orientation import pixel_to_pdf
from types import SimpleNamespace
from tools.ocr_fixtures import rasterize


def normalized(value):
    return ''.join(unicodedata.normalize('NFKC',value).split())


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        next_row=[i]
        for j,y in enumerate(b,1):
            next_row.append(min(next_row[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=next_row
    return row[-1]


def truth(path):
    pages=[]
    with pdfium.PdfDocument(path) as doc:
        for i in range(len(doc)):
            page=doc[i]; tp=page.get_textpage()
            pages.append(tp.get_text_range())
            tp.close();page.close()
    return pages


def metrics(expected,actual):
    reference=normalized(expected); hypothesis=normalized(actual)
    tokens=lambda text:Counter(re.findall(r'\d+(?:[.,]\d+)?|\b[A-Z][A-Z0-9]{1,}\b',text))
    refs=tokens(expected); found=tokens(actual)
    return dict(cer=distance(reference,hypothesis)/max(1,len(reference)),reference_characters=len(reference),
                identifier_numeric_recall=sum((refs&found).values())/max(1,sum(refs.values())),
                identifiers_expected=dict(refs),identifiers_missing=dict(refs-found))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--devices',nargs='+',default=['cpu','gpu','auto'])
    parser.add_argument('--profiles',nargs='+',default=['balanced'])
    parser.add_argument('--cases',nargs='+',default=['automotive','silverstone'])
    parser.add_argument('--output',type=Path,default=Path('docs/qa/aw062/benchmark.json'))
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    for name in args.cases:
        native=Path('tests/fixtures/pdf')/(name+'.pdf')
        scan=Path('build/aw062')/(name+'-scan.pdf')
        if not scan.exists():rasterize(native,scan)
        expected=truth(native)
        native_doc=PdfDocument(native)
        digest=sha256(scan.read_bytes()).hexdigest()
        for profile in args.profiles:
            for device in args.devices:
                router=OcrRouter();start=perf_counter();raw_segments=[]
                recognize=router.recognize
                def capture(request):
                    result=recognize(request)
                    for s in result.segments:
                        pts=[pixel_to_pdf(x,y,request.region,request.image.size) for x,y in s.polygon]
                        xs,ys=zip(*pts)
                        raw_segments.append(SimpleNamespace(text=s.text,page=s.page_index,bbox=(min(xs),min(ys),max(xs),max(ys))))
                    return result
                router.recognize=capture
                row=dict(case=name,device=device,profile=profile)
                try:
                    extractor=HybridPdfExtractor(router,DocumentConfig(source='zh' if name=='automotive' else 'ru',device=device,profile=profile))
                    doc=PdfDocument(scan,extractor=extractor)
                    row.update(seconds=perf_counter()-start,pages=len(doc.pages),segments=len(doc.segments),routes=router.last_results,
                               metrics=[metrics(ref,'\n'.join(s.text for s in sorted(raw_segments,key=lambda s:(-s.bbox[3],s.bbox[0])) if s.page==i)) for i,ref in enumerate(expected)])
                    row['source_sha_unchanged']=sha256(scan.read_bytes()).hexdigest()==digest
                    scoped=[]
                    for i in range(len(expected)):
                        references=[s for s in native_doc.segments if s.page==i]
                        references.sort(key=lambda s:(-s.bbox[3],s.bbox[0]))
                        pairs=[]
                        for ref in references:
                            matching=[s for s in raw_segments if s.page==i and intersection(s.bbox,ref.bbox)/max(1,min(area(s.bbox),area(ref.bbox)))>.4]
                            matching.sort(key=lambda s:(-s.bbox[3],s.bbox[0]))
                            pairs.append((ref.text,''.join(s.text for s in matching)))
                        size=sum(len(normalized(a)) for a,b in pairs)
                        scoped.append(dict(native_region_cer=sum(distance(normalized(a),normalized(b)) for a,b in pairs)/max(1,size),
                            bbox_recall=sum(bool(b) for a,b in pairs)/max(1,len(pairs)),blocks=len(pairs),reference_characters=size))
                    row['native_region_metrics']=scoped
                    transcript=[dict(page=s.page,text=s.text,bbox=s.bbox,confidence=s.confidence,model=s.ocr_model) for s in doc.segments]
                    (args.output.parent/f'{name}-{device}-{profile}-ocr.json').write_text(json.dumps(transcript,ensure_ascii=False,indent=2),'utf-8')
                except Exception as error:
                    row.update(error=type(error).__name__,code=getattr(error,'code',None),seconds=perf_counter()-start)
                finally:
                    router.shutdown()
                records.append(row)
                args.output.write_text(json.dumps(records,ensure_ascii=False,indent=2),'utf-8')
                print(json.dumps({k:v for k,v in row.items() if k not in ('metrics','routes')},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
