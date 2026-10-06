"""Read-only AW0.8.2 instrumentation and ordinary Qt batch baseline.

No production modules are edited. Wrappers call each original exactly once;
input/output objects, exceptions, scheduling and model policies are unchanged.
Run prepare, then run (exactly two batches), then analyze separately.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from functools import wraps
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unicodedata
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
QA = ROOT / 'docs/qa/aw083-baseline'
BUILD = ROOT / 'build/aw083-baseline'
CORPUS = BUILD / 'source/车身尺寸'
ARCHIVE = Path('C:/Users/PC/Downloads/车身尺寸.zip')


def safe(value):
    if is_dataclass(value): return asdict(value)
    if isinstance(value, Path): return str(value)
    if isinstance(value, set): return sorted(value)
    raise TypeError(type(value).__name__)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=safe)+'\n', 'utf-8')


def digest(path): return sha256(path.read_bytes()).hexdigest()
def normalized(text): return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def pdf_inventory(path):
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    texts, pages = [], []
    with pdfium.PdfDocument(path) as doc:
        for i in range(len(doc)):
            page = doc[i]
            tp = page.get_textpage()
            text = tp.get_text_range()
            texts.append(text)
            objects = list(page.get_objects(max_depth=1))
            pages.append(dict(page=i+1, size=page.get_size(), native_chars=len(text),
                              images=sum(o.type == raw.FPDF_PAGEOBJ_IMAGE for o in objects),
                              paths=sum(o.type == raw.FPDF_PAGEOBJ_PATH for o in objects)))
            tp.close(); page.close()
    return dict(pages=len(pages), page_inventory=pages, size=path.stat().st_size, sha256=digest(path)), texts


def prepare():
    QA.mkdir(parents=True, exist_ok=True); BUILD.mkdir(parents=True, exist_ok=True)
    assert not (QA/'cold-run.json').exists(), 'Existing measurements must not be overwritten'
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for base in ('app', 'assets/config', 'vendor/models')
              for p in (ROOT/base).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    save(BUILD/'production-before.json', hashes)
    (QA/'git-status-before.txt').write_bytes(subprocess.check_output(['git','status','--short'], cwd=ROOT))
    (BUILD/'working-before.diff').write_bytes(subprocess.check_output(['git','diff','--binary'], cwd=ROOT))
    with ZipFile(ARCHIVE) as archive:
        for entry in archive.infolist():
            target = (CORPUS/entry.filename).resolve()
            assert target.is_relative_to(CORPUS.resolve())
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            data = archive.read(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): assert target.read_bytes() == data
            else: target.write_bytes(data)
    rows = []
    for path in sorted(CORPUS.rglob('*.pdf')):
        info, texts = pdf_inventory(path)
        rel = path.relative_to(CORPUS).as_posix()
        rows.append(dict(file=rel, **info))
        dest = QA/'source-text'/Path(rel).with_suffix('.txt')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('\n\n'.join(f'=== PAGE {i+1} ===\n{text}' for i,text in enumerate(texts)), 'utf-8')
    inventory = dict(archive=str(ARCHIVE), archive_sha256=digest(ARCHIVE), files=rows,
                     count=len(rows), pages=sum(r['pages'] for r in rows), bytes=sum(r['size'] for r in rows))
    save(QA/'corpus-inventory.json', inventory)
    assert inventory['count'] == 7 and inventory['pages'] == 22, inventory
    print(json.dumps(inventory, ensure_ascii=False, indent=2))


class Recorder:
    def __init__(self):
        self.run = None; self.file = None; self.start = time.perf_counter()
        self.local = threading.local()
        self.events = []; self.ocr = []; self.opens = []; self.domains = []
        self.results = []; self.backend = []; self.inference = []; self.chunks = []
        self.documents = []; self.published = []; self.model_loads = []; self.network = []

    def wrap(self, owner, name, stage, before=None, after=None):
        original = getattr(owner, name)
        @wraps(original)
        def call(*args, **kwargs):
            if before: before(args, kwargs)
            if self.run is None: return original(*args, **kwargs)
            stack = getattr(self.local, 'stack', None)
            if stack is None: self.local.stack = stack = []
            start = time.perf_counter(); frame = [0.0]; stack.append(frame)
            result = None; error = None
            try:
                result = original(*args, **kwargs)
                return result
            except BaseException as exc:
                error = type(exc).__name__; raise
            finally:
                duration = time.perf_counter()-start
                stack.pop()
                if stack: stack[-1][0] += duration
                event = dict(run=self.run, file=self.file, stage=stage, start=start-self.start,
                             seconds=duration, self_seconds=max(0,duration-frame[0]), error=error)
                self.events.append(event)
                if after: after(args, kwargs, result, event)
        # Preserve static method binding; otherwise normal Python wrappers suffice.
        import inspect
        descriptor = inspect.getattr_static(owner, name)
        setattr(owner, name, staticmethod(call) if isinstance(descriptor, staticmethod) else call)
        return original

    def install(self):
        import app.documents.job as job
        import app.documents.pdf_document as pdf
        import app.ocr.pdf_extractor as extraction
        from app.ocr.router.ocr_router import OcrRouter
        from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager
        from app.translation_memory.knowledge import TranslationKnowledgeEngine
        from app.translation_memory.engine import TranslationMemoryEngine
        from app.glossary.engine import GlossaryEngine
        from app.engine.runtime.runtime_manager import RuntimeManager
        from app.engine.backends.m2m100_backend import M2M100Backend
        from app.documents.control import JobControl

        def enter_file(args, kwargs):
            self.file = Path(args[0]).relative_to(CORPUS).as_posix()
            print(self.run, 'OPEN', self.file, flush=True)
        def opened(args, kwargs, doc, event):
            if doc is not None:
                self.opens.append(dict(**event, classification=str(doc.classification), pages=len(doc.pages),
                                       segments=len(doc.segments), source_sha256=doc.source_hash,
                                       ocr_segments=sum(s.origin=='ocr' for s in doc.segments)))
        self.wrap(job, 'open_document', 'open_extract_preflight', enter_file, opened)
        self.wrap(pdf.PdfDocument, '_open', 'pdf_parse')
        self.wrap(pdf, 'page_info', 'page_structure')
        self.wrap(pdf.NativeTextExtractor, 'extract', 'native_extraction_grouping')
        self.wrap(extraction.HybridPdfExtractor, 'extract', 'hybrid_classify_postprocess')
        self.wrap(extraction, 'render_region', 'raster_render')
        self.wrap(extraction, 'complexity', 'raster_complexity')
        for name in ('allocate', 'merge_lines', 'reading_order', 'background', 'duplicate'):
            self.wrap(extraction, name, 'ocr_postprocess')
        def ocr_done(args, kwargs, result, event):
            if result is not None:
                request=args[1]
                self.ocr.append(dict(**event, page=request.page_index+1, backend=result.backend,
                    device=result.device, timings=result.timings, segments=len(result.segments),
                    region=request.pdf_bbox if hasattr(request,'pdf_bbox') else str(request.region_bbox) if hasattr(request,'region_bbox') else None,
                    image_size=request.image.size, image_sha256=sha256(request.image.tobytes()).hexdigest(),
                    recognized=[dict(text=s.text, confidence=s.confidence, bbox=s.bbox) for s in result.segments],
                    route_reason=result.route_reason))
        self.wrap(OcrRouter, 'recognize', 'ocr_total', after=ocr_done)
        self.wrap(OcrRuntimeManager, 'run', 'ocr_worker_roundtrip')
        self.wrap(OcrRouter, 'shutdown', 'ocr_shutdown')
        def domain_done(args, kwargs, result, event):
            if result is not None:self.domains.append(dict(**event, evidence=asdict(result), source=args[2], target=args[3]))
        self.wrap(TranslationKnowledgeEngine, 'detect_domain', 'domain_detection', after=domain_done)
        self.wrap(TranslationMemoryEngine, 'lookup_many', 'tm_lookup_prefetch')
        self.wrap(TranslationMemoryEngine, 'record_use', 'tm_record_use')
        self.wrap(GlossaryEngine, 'lookup', 'glossary_lookup')
        def translated(args, kwargs, result, event):
            if result is not None:self.results.append(dict(**event, request=asdict(args[1]), result=asdict(result)))
        self.wrap(TranslationKnowledgeEngine, 'translate', 'knowledge_translate', after=translated)
        self.wrap(TranslationKnowledgeEngine, 'lookup_direct', 'knowledge_direct', after=translated)
        self.wrap(TranslationKnowledgeEngine, 'prefetch', 'prefetch')
        self.wrap(job.DocumentJob, '_pdf_translation', 'segment_translation')
        self.wrap(job.DocumentJob, '_destination', 'destination')
        def backend_done(args, kwargs, result, event):
            self.backend.append(dict(**event, backend=args[1], request=asdict(args[2]), options=asdict(args[4]),
                                     model_ids=list(result.model_ids) if result else []))
        self.wrap(RuntimeManager, 'run', 'translation_backend', after=backend_done)
        self.wrap(RuntimeManager, 'release_models', 'model_release_for_ocr')
        def load_done(args, kwargs, result, event):
            self.model_loads.append(dict(**event, backend='m2m100'))
        self.wrap(M2M100Backend, '_load', 'translation_load_or_reuse', after=load_done)
        for module_name in ('m2m100_backend', 'argos_backend'):
            from importlib import import_module
            module = import_module('app.engine.backends.'+module_name)
            original = module.translate_segments
            def segmented(text, target, encode, decode, infer, options, cancelled, *, _original=original, **kwargs):
                total_chunks=0; unique=set(); sent=0
                def counted_encode(value):
                    nonlocal total_chunks
                    tokens=encode(value)
                    for offset in range(0,len(tokens),options.max_input_tokens):
                        total_chunks+=1; unique.add(tuple(tokens[offset:offset+options.max_input_tokens]))
                    return tokens
                def counted_infer(batch):
                    nonlocal sent
                    started=time.perf_counter(); sent+=len(batch)
                    try:return infer(batch)
                    finally:self.inference.append(dict(run=self.run,file=self.file,seconds=time.perf_counter()-started,
                                                        chunks=len(batch)))
                try:return _original(text,target,counted_encode,decode,counted_infer,options,cancelled,**kwargs)
                finally:self.chunks.append(dict(run=self.run,file=self.file,total=total_chunks,unique=len(unique),sent=sent,
                                                avoided=total_chunks-len(unique)))
            module.translate_segments=segmented
        self.wrap(pdf, 'flow_boxes', 'layout_reflow')
        self.wrap(pdf, 'fit', 'font_fit')
        for name in ('resolve', 'prepare', 'embed'):
            self.wrap(pdf.FontResolver, name, 'font_'+name)
        self.wrap(pdf.PdfDocument, 'write', 'pdf_write')
        def validated(args, kwargs, result, event):
            doc=args[0]
            self.documents.append(dict(**event, validated=event['error'] is None, warnings=list(doc.warnings),
                segments=[asdict(s) for s in doc.segments], classification=str(doc.classification),
                pages=len(doc.pages), continuations=getattr(doc,'continuation_count',0)))
        self.wrap(pdf.PdfDocument, 'validate', 'validation', after=validated)
        def published(args,kwargs,result,event):
            self.published.append(event)
            print(self.run, 'PUBLISHED', self.file, flush=True)
        self.wrap(JobControl, 'publish', 'publication', after=published)


class MemorySampler:
    def __init__(self, recorder):
        import psutil
        self.psutil=psutil; self.process=psutil.Process(); self.recorder=recorder
        self.stop=threading.Event(); self.ram=[]; self.gpu=[]
    def point(self):
        main=self.process.memory_info().rss; children=[]
        for child in self.process.children(recursive=True):
            try:
                if 'app.ocr.runtime.worker' in ' '.join(child.cmdline()):
                    children.append(dict(pid=child.pid,rss=child.memory_info().rss))
            except (self.psutil.NoSuchProcess,self.psutil.AccessDenied):pass
        return dict(t=time.perf_counter()-self.recorder.start,run=self.recorder.run,file=self.recorder.file,
                    main_rss=main,ocr_children=children,combined=main+sum(c['rss'] for c in children))
    def gpu_point(self):
        try:
            value=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.total,utilization.gpu',
                '--format=csv,noheader,nounits'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=5,text=True)
            return dict(t=time.perf_counter()-self.recorder.start,run=self.recorder.run,file=self.recorder.file,
                        devices=[list(map(int,line.split(','))) for line in value.strip().splitlines()])
        except Exception as error:return dict(error=type(error).__name__)
    def start(self):
        def ram_loop():
            while not self.stop.is_set():self.ram.append(self.point());self.stop.wait(.2)
        def gpu_loop():
            while not self.stop.is_set():self.gpu.append(self.gpu_point());self.stop.wait(1)
        self.threads=[threading.Thread(target=f,daemon=True) for f in (ram_loop,gpu_loop)]
        for t in self.threads:t.start()
    def finish(self):
        self.stop.set()
        for t in self.threads:t.join(8)


def measure():
    assert (QA/'corpus-inventory.json').exists()
    assert not (QA/'cold-run.json').exists(), 'Exactly two passes; do not silently repeat'
    for key in ('TREETRANSLATE_TM_PATH','TREETRANSLATE_GLOSSARY_PATH'):
        assert not os.environ.get(key), 'Use existing user knowledge stores'
    recorder=Recorder()
    def network_audit(event,args):
        if event.startswith(('socket.connect','socket.getaddrinfo','socket.sendto','socket.gethostby')) or event=='urllib.Request':
            recorder.network.append(dict(event=event,run=recorder.run))
            raise PermissionError('AW083_BASELINE_OFFLINE')
    sys.addaudithook(network_audit)
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from app.config.constants import APP_NAME, ORGANIZATION_NAME
    from app.services.settings_service import SettingsService
    from app.services.hardware_profile_service import HardwareProfileService
    from app.engine.runtime.device_manager import DeviceManager
    from app.models.translation_job import JobState
    import app.gui.main_window as main_module
    app=QApplication([]);app.setApplicationName(APP_NAME);app.setOrganizationName(ORGANIZATION_NAME)
    existing=QSettings(); local=QSettings(str(BUILD/'baseline-settings.ini'),QSettings.Format.IniFormat)
    for key in existing.allKeys():local.setValue(key,existing.value(key))
    settings=SettingsService(local)
    for key,value in {'language/source':'Определить автоматически','language/target':'Русский',
                      'performance/device':'Auto','general/output_location':'custom','general/open_output':False,
                      'general/restore_job':False,'general/output_template':'{name}_{lang}',
                      'translation/translate_folders':False,'translation/translate_filenames':False}.items():
        settings.save_value(key,value)
    main_module.SettingsService=lambda:settings
    hardware=asdict(HardwareProfileService().detect());hardware['cuda_available']=DeviceManager().gpu_available()
    save(QA/'hardware.json',hardware)
    recorder.install()
    window=main_module.MainWindow(); window.show()
    from app.gui.styles.theme import load_stylesheet
    app.setStyleSheet(load_stylesheet())
    service=window.translation_service;engine=service.engine
    sampler=MemorySampler(recorder);sampler.start()
    def wait(predicate,timeout=14400):
        deadline=time.monotonic()+timeout
        while not predicate():
            if time.monotonic()>deadline:raise TimeoutError('Baseline job timeout')
            app.processEvents();time.sleep(.01)
        app.processEvents()
    def runtime_state():
        return dict(warm_backend=engine.runtime._warm,tm_cache_entries=len(engine.memory.cache),
            tm_path=str(engine.memory.db.path),glossary_path=str(engine.glossary.db.path),
            tm_counters=dict(engine.memory.counters),glossary_counters=dict(engine.glossary.counters),
            backends={name:dict(translator_loaded=getattr(b,'_translator',None) is not None,
                translators=len(getattr(b,'_translators',{}))) for name,b in engine.runtime.backends.items()})
    errors=[]; service.files.failed.connect(errors.append)
    initial=runtime_state();save(QA/'cache-initial.json',initial)
    try:
        for name in ('cold','warm'):
            recorder.file=None;recorder.run=name
            settings.save_value('general/output_path',str(QA/'output'/name))
            scan_start=time.perf_counter()
            window.translation.accept_paths([CORPUS]);wait(lambda:not service.files.busy)
            assert service.state==JobState.READY,service.state
            scan_seconds=time.perf_counter()-scan_start
            assert len(service.files.selected)==7
            before=runtime_state();rss_before=sampler.point();vram_before=sampler.gpu_point()
            started=time.perf_counter()
            assert window.file_page.start_button.isEnabled()
            window.file_page.start_button.click()
            wait(lambda:not service.files.busy)
            total=time.perf_counter()-started
            result=dict(run=name,wall_seconds=total,scan_seconds=scan_seconds,active_seconds=service.files.control.active_seconds,
                state=service.state.name,outputs=[str(p) for p in window.file_page.progress.output_paths],
                warnings=list(service.files.warnings),errors=list(errors),config=asdict(service.files.config),
                runtime_before=before,runtime_after=runtime_state(),rss_before=rss_before,
                rss_after=sampler.point(),vram_before=vram_before,vram_after=sampler.gpu_point())
            save(QA/(name+'-run.json'),result)
            window.grab().save(str(QA/(name+'-ui.png')))
            print(name,'DONE',round(total,3),'s',service.state.name,flush=True)
            if service.state!=JobState.COMPLETED:break
        recorder.run=None
    finally:
        window.close()
        sampler.finish()
        save(QA/'memory.json',dict(ram_sample_interval_s=.2,gpu_sample_interval_s=1,
             ram=sampler.ram,gpu=sampler.gpu,after_shutdown=sampler.gpu_point(),
             note='GPU values are device-wide MiB; sampled peaks may miss short spikes. Main+OCR excludes unrelated processes.'))
        save(QA/'raw-instrumentation.json',{k:v for k,v in vars(recorder).items() if isinstance(v,list)})
        settings.sync()


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('prepare','run'))
    args=parser.parse_args()
    prepare() if args.mode=='prepare' else measure()
