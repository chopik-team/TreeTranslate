"""Measurement only. A fixed 100-member subset prevents a full CN7C run."""
from collections import Counter, defaultdict
from hashlib import sha256
import argparse
import json
import logging
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import sys
from time import perf_counter, time
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.aw081_large_zip import ARCHIVE, production_hashes
from app.documents.run_metrics import file_hash
QA = ROOT / 'qa/aw081/speed_calibration_100'
EXPECTED_SOURCE_SHA = 'ecc0fd54bbc421af33febcb4f971e9a4735b15102aae9c451334a449c3a85330'


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf8')
    os.replace(temporary, path)


def frozen_hashes():
    result = production_hashes()
    # Include manifests, UI resources and all authored Knowledge sources too.
    for path in sorted((ROOT / 'assets').rglob('*')):
        if path.is_file() and path.suffix in {'.json', '.qss', '.ts', '.qm'}:
            result[str(path.relative_to(ROOT))] = file_hash(path)
    result['vendor/models/models_manifest.json'] = file_hash(ROOT / 'vendor/models/models_manifest.json')
    return result


def prepare():
    QA.mkdir(exist_ok=False)
    before = frozen_hashes()
    from app.documents.control import JobControl
    from app.documents.scanner import scan_sources
    from app.documents.zip_archive import inventory
    from app.knowledge.profile import DocumentProfiler
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    started = perf_counter()
    scanned = scan_sources([ARCHIVE], JobControl())
    scan_seconds = perf_counter()-started
    assert len(scanned.files) == 17211 and scanned.files[0].archive_hash == EXPECTED_SOURCE_SHA
    members = [m for m in inventory(ARCHIVE, JobControl(), verify_crc=False)
               if not m.directory and PurePosixPath(m.name).suffix.lower() == '.pdf']
    families = defaultdict(list)
    for index, member in enumerate(members):
        families[PurePosixPath(member.name).parts[1]].append((index, member))
    ideal = {name: len(rows)*100/len(members) for name, rows in families.items()}
    quotas = {name: max(1, math.floor(value)) for name, value in ideal.items()}
    while sum(quotas.values()) < 100:
        name = max(quotas, key=lambda key: (ideal[key]-quotas[key], key))
        quotas[name] += 1
    while sum(quotas.values()) > 100:
        name = max((key for key in quotas if quotas[key] > 1), key=lambda key: (quotas[key]-ideal[key], key))
        quotas[name] -= 1
    selected = []
    for family, rows in families.items():
        ordered = sorted(rows, key=lambda row: (row[1].size, row[1].name))
        for slot in range(quotas[family]):
            rank = math.floor((slot+.5)*len(ordered)/quotas[family])
            index, member = ordered[rank]
            selected.append((index, member, family, rank, slot))
    selected.sort(key=lambda row: row[0])
    assert len(selected) == 100 and len({row[1].name for row in selected}) == 100
    source = QA / (ARCHIVE.stem + '_SPEED100.zip')
    profiler = DocumentProfiler()
    documents = []
    with ZipFile(ARCHIVE) as original, ZipFile(source, 'w', compression=ZIP_DEFLATED, compresslevel=6) as subset:
        for number, (index, member, family, rank, slot) in enumerate(selected):
            data = original.read(member.name)  # ZIP CRC verified by read as well.
            digest = sha256(data).hexdigest()
            subset.writestr(member.name, data)
            pages = None
            native_chars = 0
            large_image_pages = 0
            empty_native_pages = 0
            texts = []
            inspection_error = None
            try:
                pdf = pdfium.PdfDocument(data)
                try:
                    pages = len(pdf)
                    for page_index in range(pages):
                        page = pdf[page_index]
                        try:
                            textpage = page.get_textpage()
                            try: text = textpage.get_text_range()
                            finally: textpage.close()
                            count = sum(c.isalpha() for c in text)
                            native_chars += count
                            empty_native_pages += count == 0
                            if sum(len(t) for t in texts) < 8000:
                                texts.append(text[:4000])
                            width, height = page.get_size()
                            images = [obj for obj in page.get_objects() if obj.type == raw.FPDF_PAGEOBJ_IMAGE]
                            if any((obj.get_bounds()[2]-obj.get_bounds()[0])*(obj.get_bounds()[3]-obj.get_bounds()[1])
                                   >= width*height*.15 for obj in images):
                                large_image_pages += 1
                        finally: page.close()
                finally: pdf.close()
            except Exception as error:
                inspection_error = type(error).__name__
            kind = ('unknown' if pages is None else 'image-only' if native_chars == 0
                    else 'mixed' if large_image_pages or empty_native_pages else 'native')
            profile = profiler.profile('zh', 'ru', identity=digest, filename=PurePosixPath(member.name).name,
                folders=PurePosixPath(member.name).parts[:-1], segments=tuple(texts))
            documents.append(dict(index=number, inventory_pdf_index=index, member_path=member.name,
                source_sha256=digest, source_size=member.size, pages=pages,
                classification=kind, classification_basis='read-only native text and large raster presence; provisional, not OCR-used',
                source_inspection=dict(native_alphabetic_chars=native_chars, large_raster_pages=large_image_pages,
                    empty_native_pages=empty_native_pages, error_type=inspection_error),
                domain=profile.primary_domain, subdomains=dict(profile.subdomains),
                family=family, family_population=len(families[family]), family_sample=quotas[family],
                population_weight=len(families[family])/quotas[family], size_rank=rank,
                selection_reason=f'family proportional quota {quotas[family]}/{len(families[family])}; size midpoint quantile slot {slot+1}/{quotas[family]}'))
    with ZipFile(source) as subset:
        assert len(subset.infolist()) == 100 and subset.testzip() is None
    assert frozen_hashes() == before
    manifest = dict(schema=1, method='deterministic family-proportional quotas with size midpoint quantiles',
        exact_method=dict(family_key='second POSIX path component', allocation='floor(N_family*100/17211), minimum one; largest quota deficit until total=100',
            within_family='sort(size,path); select floor((slot+0.5)*N_family/quota), then restore original inventory order', randomness=False),
        input_archive=str(ARCHIVE), input_archive_sha256=EXPECTED_SOURCE_SHA, inventory_pdf_count=17211,
        inventory_pdf_bytes=sum(m.size for m in members), scan_seconds=scan_seconds,
        sample_archive=str(source), sample_archive_sha256=file_hash(source), sample_count=100,
        preparation_seconds=perf_counter()-started, classification_counts=dict(Counter(d['classification'] for d in documents)),
        corpus_families={name:dict(population=len(rows),sample=quotas[name]) for name,rows in families.items()},
        training=False, knowledge_changes=False, documents=documents)
    save(QA / 'sample_manifest.json', manifest)
    save(QA / 'production_before.json', before)
    print('PREPARED',len(documents),'pages',sum(d['pages'] or 0 for d in documents),manifest['classification_counts'],flush=True)


def run():
    manifest = json.loads((QA / 'sample_manifest.json').read_text('utf8'))
    before = json.loads((QA / 'production_before.json').read_text('utf8'))
    assert frozen_hashes() == before
    source = Path(manifest['sample_archive'])
    assert source != ARCHIVE and file_hash(source) == manifest['sample_archive_sha256']
    with ZipFile(source) as subset:
        assert len(subset.infolist()) == 100 and all(i.filename.endswith('.pdf') for i in subset.infolist())
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.documents.archive_job import ArchiveJob
    from app.documents.control import JobControl
    from app.documents.job import DocumentJob, DocumentConfig
    from app.documents.scanner import scan_sources
    from app.documents import run_metrics as metrics
    from app.engine.factory import create_translation_engine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    engine = create_translation_engine(memory=TranslationMemoryEngine(QA/'isolated-tm.db'),
        glossary=GlossaryEngine(QA/'isolated-user.db',builtin_paths=bundled_paths()))
    handler = logging.FileHandler(QA / 'timing.log',encoding='utf8')
    handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s'))
    logger = logging.getLogger('treetranslate');logger.setLevel(logging.INFO);logger.addHandler(handler)
    control = JobControl()
    start = perf_counter()
    scan = scan_sources([source],control)
    sample_scan_seconds = perf_counter()-start
    assert len(scan.files) == 100
    cfg = DocumentConfig(source='auto',target='ru',domain='auto',translate_directories=True,translate_filenames=True,
        output=QA/'output',metrics_directory=QA/'logs')
    job = DocumentJob(scan.files,cfg,control,engine.translate,engine.languages.resolve,before_ocr=engine.runtime.release_models)
    job.metrics_metadata = dict(scope='SPEED_CALIBRATION_100_ONLY',sample_manifest=str(QA/'sample_manifest.json'),
        input_corpus=str(ARCHIVE),scan_seconds=sample_scan_seconds,selected_files=100,training=False)
    timing = (QA/'timing_events.jsonl').open('x',encoding='utf8',buffering=65536)
    measurements = dict(started_unix=time(),documents_started=0,documents_packaged=0,events=[],path_cache=None,
        observer_errors=[],sample_scan_seconds=sample_scan_seconds)
    original_stage = metrics.LocalRun.stage
    original_event = metrics.LocalRun.archive_event
    original_model = metrics.LocalRun.model_event
    original_archive = ArchiveJob._run
    def snapshot(): save(QA/'live_progress.json',measurements)
    def stage(observer,name,seconds,state='ok',page=None,block=None):
        result = original_stage(observer,name,seconds,state,page,block)
        try:
            timing.write(json.dumps(dict(stage=name,seconds=seconds,state=state,page=page,block=block,
                document_id=getattr(metrics._doc.get(),'document_id',None),elapsed_since_run_start=perf_counter()-start))+'\n')
        except Exception as error: measurements['observer_errors'].append(type(error).__name__)
        return result
    def event(observer,event,**data):
        result = original_event(observer,event,**data)
        try:
            measurements['events'].append(dict(event=event,elapsed_since_run_start=perf_counter()-start,**data))
            if event=='document_start':
                measurements['documents_started']+=1
                assert measurements['documents_started']<=100
                print('START',measurements['documents_started'],'/100',round(perf_counter()-start,2),flush=True)
            if event=='member_packaged':
                measurements['documents_packaged']+=1
                print('PACKAGED',measurements['documents_packaged'],'/100',round(perf_counter()-start,2),flush=True)
            if event in {'document_start','member_packaged','preflight_completed','summary'}:
                timing.flush();snapshot()
        except Exception as error: measurements['observer_errors'].append(type(error).__name__)
        return result
    def model(observer,backend,device,success,fallback,error_type=None):
        result = original_model(observer,backend,device,success,fallback,error_type)
        try:
            observer.emit('routing',dict(event='backend_attempt',backend=backend,device=device,success=success,
                fallback=fallback,exception_type=error_type))
        except Exception as error: measurements['observer_errors'].append(type(error).__name__)
        return result
    def archive(archive_job):
        try: return original_archive(archive_job)
        finally:
            cache=archive_job.path_translation
            measurements['path_cache']=dict(hits=cache.hits,misses=cache.misses,entries=len(cache.cache),
                folder_components=len(archive_job.folder_names),capacity=cache.capacity,
                unique_component_scope='distinct successful context/language/cache keys, not unique source words')
    metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event=stage,event,model
    ArchiveJob._run=archive
    outputs=[];failure=None
    try:
        with engine.runtime.keep_warm(): outputs=job.run()
    except BaseException as error:
        failure=dict(exception_type=type(error).__name__,status=getattr(job,'run_status','FAILED'))
    finally:
        measurements['wall_seconds']=perf_counter()-start
        measurements['finished_unix']=time()
        measurements['glossary_counters']=dict(engine.glossary.counters)
        measurements['tm_counters']=dict(engine.memory.counters)
        measurements['context_counters']=engine.last_context_metrics
        metrics.LocalRun.stage,metrics.LocalRun.archive_event,metrics.LocalRun.model_event=original_stage,original_event,original_model
        ArchiveJob._run=original_archive
        timing.close();engine.shutdown();logger.removeHandler(handler);handler.close()
    measurements.update(run_id=job.run_id,logs=str(getattr(job,'metrics_path','')),failure=failure,
        outputs=[str(p) for p in outputs],production_unchanged=frozen_hashes()==before,
        sample_source_immutable=file_hash(source)==manifest['sample_archive_sha256'],
        full_source_immutable=file_hash(ARCHIVE)==EXPECTED_SOURCE_SHA,whole_corpus_run=False)
    save(QA/'execution.json',measurements)
    if getattr(job,'metrics_path',None):
        for name in ('run_summary.json','stages.jsonl','documents.jsonl','routing.jsonl','warnings.jsonl','errors.jsonl','resource_samples.jsonl','archive_events.jsonl','run_manifest.json','index.sqlite3'):
            shutil.copy2(job.metrics_path/name,QA/name)
    assert measurements['production_unchanged'] and measurements['sample_source_immutable'] and measurements['full_source_immutable']
    print('CALIBRATION_FINISHED',measurements['documents_packaged'],round(measurements['wall_seconds'],2),failure,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','run'])
    args=parser.parse_args()
    prepare() if args.mode=='prepare' else run()
