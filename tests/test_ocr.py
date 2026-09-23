from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from PIL import Image
import pytest
import pypdfium2 as pdfium

from app.documents.control import JobControl
from app.documents.job import DocumentConfig, DocumentJob
from app.documents.pdf_document import PdfDocument
from app.documents.pdf_types import PdfSegment
from app.documents.scanner import scan_sources
from app.engine.errors import TranslationCancelledError
from app.ocr.config import profile
from app.ocr.errors import OcrError
from app.ocr.pdf_extractor import HybridPdfExtractor
from app.ocr.postprocess.deduplication import duplicate
from app.ocr.preprocess.orientation import pixel_to_pdf,restore_point
from app.ocr.preprocess.renderer import render_region
from app.ocr.router.ocr_router import OcrRouter
from app.ocr.router.routing_policy import decide
from app.ocr.types import OcrRequest,OcrSegment,OcrPageResult
from tools.pdf_fixtures import make_pdf
from tools.ocr_fixtures import rasterize


class FakeRouter:
    def __init__(self):
        self.calls=[]
    def recognize(self,request):
        self.calls.append(request.image.size)
        # Fixture title is x45..200/y720 in a 600x800 page.
        w,h = request.image.size
        polygon=tuple((x*w/600,y*h/800) for x,y in ((44,62),(250,62),(250,88),(44,88)))
        s=OcrSegment('title','Engine configuration guide',polygon,(0,0,1,1),.99)
        return OcrPageResult(0,[s],'fake','cpu',.01)


def test_native_does_not_call_ocr(tmp_path):
    router=FakeRouter()
    path=make_pdf(tmp_path/'native.pdf')
    doc=PdfDocument(path,extractor=HybridPdfExtractor(router,DocumentConfig()))
    assert doc.segments and not router.calls


def test_scan_shared_writer_masks_and_validates(tmp_path):
    original=make_pdf(tmp_path/'native.pdf')
    scan=rasterize(original,tmp_path/'scan.pdf')
    router=FakeRouter()
    doc=PdfDocument(scan,extractor=HybridPdfExtractor(router,DocumentConfig(source='en')))
    assert len(router.calls)==1 and doc.segments[0].origin=='ocr'
    doc.segments[0].translated='Руководство'
    output=tmp_path/'result.pdf'
    doc.write(output)
    doc.validate(output)
    doc.assert_source_unchanged()
    assert doc.added_non_text[0]
    assert doc.segments[0].written_boxes
    with pdfium.PdfDocument(output) as pdf:
        page=pdf[0]; tp=page.get_textpage()
        assert 'Руководство' in tp.get_text_range()
        tp.close();page.close()


def test_job_extracts_scan_only_once(tmp_path,monkeypatch):
    router=FakeRouter()
    monkeypatch.setattr(OcrRouter,'recognize',lambda self,request:router.recognize(request))
    scan=rasterize(make_pdf(tmp_path/'native.pdf'),tmp_path/'scan.pdf')
    control=JobControl(); progress=[]
    output,=DocumentJob(scan_sources([scan],control).files,DocumentConfig(source='en'),control,
        lambda *a:SimpleNamespace(translated_text='Руководство'),lambda *a:('en','ru'),progress.append).run()
    assert output.exists() and len(router.calls)==1
    assert {'RENDERING','OCR','WRITING','COMPLETED'} <= {p.stage for p in progress}


def test_dedup_requires_geometry():
    s=PdfSegment(0,'0','Engine GDS',(0,0,20,10),0,(),10)
    assert duplicate(replace(s,block_id='1'),[s])
    assert not duplicate(replace(s,bbox=(100,0,120,10)),[s])
    assert not duplicate(replace(s,text='A completely different instruction'),[s])


@pytest.mark.parametrize('angle,point',[(0,(2,3)),(90,(3,198)),(180,(98,197)),(270,(97,2))])
def test_orientation(angle,point):
    assert restore_point(2,3,100,200,angle)==point
    assert pixel_to_pdf(50,100,(10,20,110,220),(100,200))==(60,120)


def test_render_limit_before_allocation():
    with pytest.raises(OcrError,match='лимит'):
        render_region(None,(0,0,100000,100000),200)


def test_policy():
    assert decide({'lines':10},'balanced').backend=='structure'
    assert decide({'lines':10},'economy').backend=='paddle'
    assert decide({},'maximum').backend=='paddle'


@pytest.mark.parametrize('preference,expected',[('cpu',['cpu']),('auto',['gpu','cpu']),('gpu',['gpu'])])
def test_device_policy(preference,expected):
    calls=[]
    class Backend:
        def recognize(self,request,device):
            calls.append(device)
            if device=='gpu': raise OcrError('gpu')
            return OcrPageResult(0,[],'paddle',device,0)
    router=OcrRouter()
    router.backends['paddle']=Backend()
    request=OcrRequest(Image.new('RGB',(10,10)),device_preference=preference)
    if preference=='gpu':
        with pytest.raises(OcrError): router.recognize(request)
    else:
        result=router.recognize(request)
        assert result.device=='cpu'
    assert calls==expected


def test_cancel_before_ocr_start():
    control=JobControl();control.cancel()
    router=OcrRouter(checkpoint=control.checkpoint)
    with pytest.raises(TranslationCancelledError):
        router.runtime.run(Image.new('RGB',(20,20)),{})
    assert router.runtime.process is None


def test_dark_background_is_not_white():
    from app.ocr.pdf_extractor import background
    image=Image.new('RGB',(100,50),'black')
    color,uncertain=background(image,(10,10,90,40))
    assert color==(0,0,0,255) and not uncertain


def test_low_confidence_never_masks_source(tmp_path):
    router=FakeRouter()
    original=router.recognize
    def low(request):
        result=original(request)
        result.segments=[replace(s,confidence=.1) for s in result.segments]
        return result
    router.recognize=low
    scan=rasterize(make_pdf(tmp_path/'native.pdf'),tmp_path/'scan.pdf')
    with pytest.raises(Exception) as error:
        PdfDocument(scan,extractor=HybridPdfExtractor(router,DocumentConfig()))
    assert not list(tmp_path.glob('*_ru.pdf'))


def test_pause_then_cancel_at_ocr_checkpoint():
    from threading import Thread
    control=JobControl();control.pause();done=Event();errors=[]
    def run():
        try:control.checkpoint()
        except TranslationCancelledError:errors.append('cancelled')
        finally:done.set()
    thread=Thread(target=run);thread.start()
    assert not done.wait(.1)
    control.cancel()
    assert done.wait(1)
    thread.join()
    assert errors==['cancelled']


def test_mixed_uses_image_crop_and_preserves_native(tmp_path):
    from tools.ocr_fixtures import make_mixed
    router=FakeRouter()
    path=make_mixed(tmp_path/'mixed.pdf')
    doc=PdfDocument(path,extractor=HybridPdfExtractor(router,DocumentConfig()))
    assert {s.origin for s in doc.segments}=={'native','ocr'}
    assert len(router.calls)==1 and router.calls[0][1]<300
    assert doc.classification.value=='MIXED_PDF'


def test_manual_ui_language_is_normalized(tmp_path):
    router=FakeRouter();original=router.recognize
    def check(request):
        assert request.source_language=='ru'
        return original(request)
    router.recognize=check
    scan=rasterize(make_pdf(tmp_path/'native.pdf'),tmp_path/'scan.pdf')
    PdfDocument(scan,extractor=HybridPdfExtractor(router,DocumentConfig(source='Русский')))


def test_line_merge_keeps_original_masks():
    from app.ocr.postprocess.regions import merge_lines
    a=PdfSegment(0,'a','Long first paragraph',(10,80,100,90),0,(),10,origin='ocr',region_kind='ocr_region',confidence=.9)
    b=replace(a,block_id='b',text='continues below.',bbox=(10,66,100,76))
    for s in (a,b):s.available_bbox=s.bbox;s.raster_boxes=(s.bbox,)
    result=merge_lines([a,b],4000)
    assert len(result)==1 and len(result[0].raster_boxes)==2
    assert result[0].bbox==(10,66,100,90)


def test_columns_read_left_then_right():
    from app.ocr.postprocess.regions import reading_order
    lines=[PdfSegment(0,str(i),str(i),(x,y,x+100,y+10),i,(),10) for i,(x,y) in enumerate([(10,180),(300,180),(10,100),(300,100),(10,20),(300,20)])]
    assert [s.block_id for s in reading_order(lines,(0,0,500,200))]==['0','2','4','1','3','5']
