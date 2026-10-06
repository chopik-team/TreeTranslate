from dataclasses import asdict
from PIL import Image
import pytest
from app.ocr.runtime.hardware_plan import OCRCapabilities,OCRHardwarePlan,GIB
from app.ocr.runtime.resident_cache import ResidentModelCache
from app.ocr.runtime.result_cache import OCRResultCache


@pytest.mark.parametrize('ram,gpu,expected',[(8,0,1),(16,4,2),(32,12,4),(64,24,4)])
def test_planner_capabilities_only_and_headroom(ram,gpu,expected):
    c=OCRCapabilities(ram*GIB,int(ram*.75*GIB),16,bool(gpu),gpu*GIB,int(gpu*.85*GIB))
    p=OCRHardwarePlan.from_capabilities(c)
    assert p.resident_models==expected
    assert 0<=p.resident_ram_bytes<=c.ram_available-p.ram_reserve_bytes
    assert 0<=p.resident_vram_bytes<=max(0,c.vram_available-p.vram_reserve_bytes)
    assert p.result_cache_bytes+p.prepared_region_bytes<=c.ram_available
    assert p.batch_ceiling is None
    assert not {'dpi','threshold','threads','model','language'}&asdict(p).keys()


@pytest.mark.parametrize('free',[-1,0,1,10**30])
def test_pressure_and_invalid_capability_values_are_bounded(free):
    c=OCRCapabilities(8*GIB,free,1,True,4*GIB,free)
    p=OCRHardwarePlan.from_capabilities(c)
    assert min(p.resident_ram_bytes,p.resident_vram_bytes,p.result_cache_bytes,p.prepared_region_bytes)>=0
    assert p.resident_ram_bytes<=c.ram_total and p.resident_vram_bytes<=c.vram_total


def test_lru_reuse_protection_and_byte_pressure():
    events=[];c=ResidentModelCache(2,100,100,lambda *a:events.append(a))
    c.put('A','modelA',40,40);c.put('B','modelB',40,40)
    c.get('A');c.put('C','modelC',40,40)
    assert list(c.entries)==['A','C'] and events[0][0]=='B'
    c.entries['A'].active=1;c.entries['C'].active=1
    with pytest.raises(MemoryError):c.put('D','modelD',40,40)
    assert set(c.entries)=={'A','C'}
    c.entries['C'].active=0;c.evict_one('pressure')
    assert list(c.entries)==['A']


def test_oversized_bundle_is_not_retained_after_inference():
    c=ResidentModelCache(2,10,10);x=c.put('A',object(),20,20);x.active=1
    c.trim();assert len(c.entries)==1
    x.active=0;c.trim();assert not c.entries


def test_result_cache_identity_semantics_and_copy():
    c=OCRResultCache(5000);im=Image.new('RGB',(10,10),'white')
    cmd=dict(source_identity='docA',page_index=0,region=[0,0,1,1],render_identity=[200,10,10],
             recognizer='A',language='auto',options={'batch':6},device='gpu')
    key=c.key(im,cmd);value=dict(device='gpu',rows=[{'text':'123'}])
    c.put(key,value);hit=c.get(key,'gpu');hit['rows'][0]['text']='changed'
    assert c.get(key,'gpu')==value and c.get(key,'cpu') is None
    for field,val in [('source_identity','docB'),('page_index',1),('region',[1,0,2,1]),
                      ('render_identity',[240,10,10]),('recognizer','B'),('language','ru')]:
        assert c.key(im,dict(cmd,**{field:val}))!=key
    assert c.key(Image.new('RGB',(10,10),'black'),cmd)!=key
    assert c.key(im,dict(cmd,device='cpu'))==key


def test_result_cache_zero_and_eviction_budget():
    c=OCRResultCache(100);c.put('a',dict(device='gpu',rows=[]))
    c.put('b',dict(device='gpu',rows=[]))
    assert c.bytes<=c.budget and len(c.entries)<=1
    c=OCRResultCache(0);c.put('a',dict(device='cpu'));assert not c.entries


def test_gate_preserves_native_priority_and_local_image_regions():
    from types import SimpleNamespace
    import pypdfium2.raw as raw
    from app.ocr.page_gate import decide_page
    from app.ocr.pdf_extractor import usable_native_chars
    def image(box):return SimpleNamespace(type=raw.FPDF_PAGEOBJ_IMAGE,get_bounds=lambda:box)
    segment=SimpleNamespace(text='Engine configuration and repair procedures',bbox=(0,80,100,100))
    full=decide_page((0,0,100,100),[image((0,0,100,100))],[segment],usable_native_chars)
    assert full.status=='NATIVE_SUFFICIENT' and full.regions==() and full.avoided_regions==1
    crop=decide_page((0,0,100,100),[image((0,0,100,50))],[segment],usable_native_chars)
    assert crop.status=='MIXED_NEEDS_REGION_OCR' and crop.regions==((0,0,100,50),)
    scan=decide_page((0,0,100,100),[image((0,0,100,100))],[],usable_native_chars)
    assert scan.status=='IMAGE_ONLY_NEEDS_OCR' and scan.regions==((0,0,100,100),)


def test_uncertain_graphical_page_keeps_full_page_fallback():
    from types import SimpleNamespace
    import pypdfium2.raw as raw
    from app.ocr.page_gate import decide_page
    from app.ocr.pdf_extractor import usable_native_chars
    objects=[SimpleNamespace(type=raw.FPDF_PAGEOBJ_PATH) for _ in range(8)]
    protected=[SimpleNamespace(text='ETM',bbox=(0,0,10,10))]
    result=decide_page((0,0,100,100),objects,protected,usable_native_chars)
    assert result.status=='UNCERTAIN_FALLBACK' and result.quality_fallback
    assert result.regions==((0,0,100,100),)


def test_runtime_result_replay_avoids_worker_and_respects_cancellation(monkeypatch):
    from types import SimpleNamespace
    from queue import Queue
    import io
    import psutil
    from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(total=16*GIB,available=12*GIB))
    checkpoints=[]
    runtime=OcrRuntimeManager(checkpoint=lambda:checkpoints.append(True),run_scoped=True)
    starts=[];stream=io.StringIO()
    def start(device):
        starts.append(device)
        runtime.process=SimpleNamespace(poll=lambda:None,stdin=stream)
        runtime._device=device;runtime._replies=Queue()
        runtime._replies.put(dict(device=device,rows=[{'text':'D 44 ± 5'}],load_seconds=1,inference_seconds=2))
    monkeypatch.setattr(runtime,'_start',start)
    image=Image.new('RGB',(10,10),'white')
    command=dict(device='cpu',source_identity='unique-source',page_index=0,region=[0,0,10,10],
                 render_identity=[200,10,10],options={'batch':6},recognizer='A')
    result=runtime.run(image,command);result['rows'][0]['text']='mutated'
    replay=runtime.run(image,command)
    assert replay['rows']==[{'text':'D 44 ± 5'}] and replay['result_cache_hit']
    assert replay['load_seconds']==replay['inference_seconds']==0
    assert starts==['cpu'] and len(stream.getvalue().splitlines())==1
    assert len(checkpoints)==3 and runtime._timer is None


def test_router_borrowed_runtime_keeps_owner_lifetime(monkeypatch):
    from types import SimpleNamespace
    from app.ocr.router import ocr_router
    shutdowns=[]
    borrowed=SimpleNamespace(shutdown=lambda:shutdowns.append('borrowed'))
    ocr_router.OcrRouter(runtime=borrowed).shutdown()
    assert shutdowns==[]
    owned=SimpleNamespace(shutdown=lambda:shutdowns.append('owned'))
    monkeypatch.setattr(ocr_router,'OcrRuntimeManager',lambda **kwargs:owned)
    ocr_router.OcrRouter().shutdown()
    assert shutdowns==['owned']
