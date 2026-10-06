"""Prepared-data GPU microprobe. Never schedules document jobs or writes PDFs."""
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import perf_counter
from zipfile import ZipFile
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw081_hardware_scaling_20 import QA,CONFIGS,controls
from tools.aw081_hardware_support import CommitBudget,Monitor,gpu_once
from tools.aw081_speed_calibration_100 import save,frozen_hashes
from tools.aw081_hardware_windows import snapshot as windows_snapshot


def run(config_name):
    cfg=dict(CONFIGS[config_name],persistent_ocr=True,gpu_residency='prepared_data_microprobe')
    before=frozen_hashes();manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'))
    source=Path(manifest['sample_archive']);source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    assert source_hash==manifest['sample_archive_sha256']
    directory=QA/'residency_probe';directory.mkdir(exist_ok=False)
    os.environ.update(QT_QPA_PLATFORM='offscreen',OMP_NUM_THREADS=str(cfg['threads']),
        OPENBLAS_NUM_THREADS=str(cfg['threads']),MKL_NUM_THREADS=str(cfg['threads']))
    budget=CommitBudget(cfg['ram_gib'])
    from PySide6.QtWidgets import QApplication
    qt=QApplication.instance() or QApplication([])
    from app.documents.control import JobControl
    from app.engine.factory import create_translation_engine
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.engine.runtime.cuda_libraries import load_cuda_libraries
    from app.engine.types import TranslationRequest,PairKind,PerformanceProfile
    from app.engine.runtime.device_manager import DeviceManager
    from app.engine.router.routing_policy import RoutingPolicy
    from app.ocr.types import OcrRequest
    from app.ocr.router.ocr_router import OcrRouter
    import pypdfium2 as pdfium
    control=JobControl();engine=create_translation_engine(memory=TranslationMemoryEngine(directory/'empty-tm.db'),
        glossary=GlossaryEngine(directory/'empty-user.db',builtin_paths=bundled_paths()))
    state=dict(order='original',phase='prepared_probe',stage=None,member=None,active_ocr=0,
        active_model=0,ocr_calls=[],batch_calls=[])
    before_ocr,shared=controls(cfg,engine,control,state);load_cuda_libraries()
    import ctranslate2
    native_translator=ctranslate2.Translator
    nmt_intervals=[];ocr_intervals=[]
    class TranslatorObserver:
        def __init__(self,*args,**kwargs):self.native=native_translator(*args,**kwargs)
        def __getattr__(self,name):return getattr(self.native,name)
        def translate_batch(self,*args,**kwargs):
            started=perf_counter();state['active_model']+=1
            try:return self.native.translate_batch(*args,**kwargs)
            finally:
                nmt_intervals.append(dict(start=started,end=perf_counter(),trial=state.get('stage')))
                state['active_model']-=1
    ctranslate2.Translator=TranslatorObserver
    from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager
    observed_ocr=OcrRuntimeManager.run
    def ocr_observer(runtime,image,command):
        result=observed_ocr(runtime,image,command);ended=perf_counter()
        ocr_intervals.append(dict(start=ended-(result.get('inference_seconds') or 0),end=ended,
            trial=state.get('stage'),backend=command['backend'],recognizer=command['recognizer']))
        return result
    OcrRuntimeManager.run=ocr_observer
    native_member=next(d['member_path'] for d in manifest['documents'] if d['bucket']=='MEDIUM')
    image_member=manifest['documents'][0]['member_path']
    with ZipFile(source) as archive:
        native=pdfium.PdfDocument(archive.read(native_member));page=native[0];tp=page.get_textpage()
        text=tp.get_text_range()[:1600];tp.close();page.close();native.close()
        document=pdfium.PdfDocument(archive.read(image_member));page=document[0]
        bitmap=page.render(scale=1.25);image=bitmap.to_pil().convert('RGB')
        bitmap.close();page.close();document.close()
    policy=RoutingPolicy().profile(PerformanceProfile.AUTOMATIC)
    options=DeviceManager().options('cuda',policy)[0]
    request=TranslationRequest(text,'zh','ru');ocr_request=OcrRequest(image,complexity=dict(lines=9,regions=0,columns=0))
    router=OcrRouter(checkpoint=control.checkpoint,before_ocr=before_ocr)
    snapshots=[];trials=[];error=None;monitor=None;isolated={}
    def snap(label):
        value=gpu_once()
        import psutil
        process=psutil.Process()
        try:owned=windows_snapshot([process.pid,*[p.pid for p in process.children(recursive=True)]])
        except Exception as exc:owned=dict(status='UNAVAILABLE',error_type=type(exc).__name__)
        snapshots.append(dict(label=label,device_wide=value,windows_owned_gpu=owned));return value
    def translate(backend,kind):
        return engine.runtime.run(backend,request,kind,options,control.cancelled).text
    def ocr_signature():
        result=router.recognize(ocr_request)
        return dict(device=result.device,backend=result.backend,segments=[asdict(s) for s in result.segments],
            layout=result.layout,warnings=result.warnings)
    def nmt_pair():return dict(m2m100=translate('m2m100',PairKind.DIRECT),argos=translate('argos',PairKind.PIVOT))
    try:
        snap('idle_before')
        with engine.runtime.keep_warm():
            for backend,kind in [('m2m100',PairKind.DIRECT),('argos',PairKind.PIVOT)]:
                started=perf_counter();value=translate(backend,kind)
                isolated[backend]=dict(output_sha256=hashlib.sha256(value.encode()).hexdigest(),seconds=perf_counter()-started,
                    snapshot=snap(backend+'_isolated'))
                engine.runtime.release_models()
                snap(backend+'_released')
            started=perf_counter();ocr_signature()
            isolated['ocr']=dict(seconds=perf_counter()-started,snapshot=snap('ocr_isolated'))
            # OCR worker remains resident; load both NMT backends with identical
            # decoding options. Independent worker/process allocators are used.
            serial_nmt=nmt_pair();serial_ocr=ocr_signature();snap('combined_resident')
            nmt_intervals.clear();ocr_intervals.clear()
            state['phase']='serial_and_parallel_inference';monitor=Monitor(directory/'resource_samples.jsonl',budget,state);monitor.start()
            for parallel in [False,True,True,False,False,True]:
                state['stage']='parallel' if parallel else 'serial';started=perf_counter()
                if parallel:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        a=pool.submit(ocr_signature);b=pool.submit(nmt_pair)
                        ocr_result=a.result();nmt_result=b.result()
                else:ocr_result=ocr_signature();nmt_result=nmt_pair()
                trials.append(dict(parallel=parallel,seconds=perf_counter()-started,
                    exact_ocr_equivalence=ocr_result==serial_ocr,exact_nmt_equivalence=nmt_result==serial_nmt))
                snap('parallel_trial' if parallel else 'serial_trial')
    except Exception as exc:error=dict(type=type(exc).__name__,detail=str(exc)[:300])
    finally:
        records=monitor.finish() if monitor else []
        if shared:shared.shutdown()
        engine.shutdown()
        ctranslate2.Translator=native_translator;OcrRuntimeManager.run=observed_ocr
    from statistics import median
    serial=[t['seconds'] for t in trials if not t['parallel']];parallel=[t['seconds'] for t in trials if t['parallel']]
    equivalent=bool(trials) and all(t['exact_ocr_equivalence'] and t['exact_nmt_equivalence'] for t in trials)
    gain=100*(median(serial)/median(parallel)-1) if serial and parallel else None
    device_samples=[s['device_wide']['used_mib'] for s in snapshots if s['device_wide']]
    device_samples += [r['gpu_device_wide']['used_mib'] for r in records if r.get('gpu_device_wide')]
    peak_device_mib=max(device_samples,default=None)
    high_budget_gib=CONFIGS['run8']['vram_gib']
    fits_high=peak_device_mib is not None and peak_device_mib<=high_budget_gib*1024
    result=dict(status='COMPLETE' if error is None and len(trials)==6 else 'UNAVAILABLE_OR_FAILED',
        configuration=cfg,inference_options=asdict(options),source_members=dict(text=native_member,image=image_member),snapshots=snapshots,
        isolated=isolated,trials=trials,exact_equivalence=equivalent,median_parallel_gain_percent=gain,
        peak_observed_device_vram_mib=peak_device_mib,
        observed_within_high_gpu_budget=fits_high,high_gpu_budget_gib=high_budget_gib,
        observed_within_nominal_probe_budget=peak_device_mib is not None and peak_device_mib<=cfg['vram_gib']*1024,
        budget_fit_scope='Observed device-wide samples for this prepared workload only; not an aggregate allocator cap or worst-case full-document residency guarantee.',
        concurrent_ocr_rpc_nmt_inference_samples=sum(bool(r.get('active_ocr')) and bool(r.get('active_model')) for r in records),
        approximate_native_inference_overlap_seconds=sum(max(0,min(a['end'],b['end'])-max(a['start'],b['start'])) for a in nmt_intervals for b in ocr_intervals),
        nmt_inference_intervals=nmt_intervals,ocr_inference_intervals_estimated=ocr_intervals,
        ocr_calls=state['ocr_calls'],error=error,
        production_unchanged=frozen_hashes()==before,source_immutable=hashlib.sha256(source.read_bytes()).hexdigest()==source_hash,
        limitations='Prepared image/text only; first sample page rendered at scale1.25, not a worst-case full200DPI document footprint. No extraction/writer/archive concurrency or full-pipeline speed claim. OCR native inference interval estimated backwards from RPC completion and worker duration; includes small IPC/serialization error. Overlapping native calls does not prove simultaneous GPU kernels without device tracing. Device-wide VRAM deltas include ambient applications; supplemental Windows per-PID dedicated/shared GPU accounting is captured separately when available. Argos pivot is a diagnostic resource probe, not a changed production route.',
        safe_useful_overlap=bool(error is None and equivalent and fits_high and gain is not None and gain>7))
    assert result['production_unchanged'] and result['source_immutable']
    save(QA/'residency_overlap_probe.json',result);print('RESIDENCY_PROBE',result['status'],gain,equivalent,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args();run(args.config)
