"""Offline raw QA and resource benchmark; one model/device per process."""
import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw084_backend import backend
from app.engine.runtime.runtime_manager import RuntimeManager
from app.engine.types import InferenceOptions,PairKind,TranslationRequest
from app.engine.runtime.offline import offline_scope


def memory():
    import ctypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),
            *[(k,ctypes.c_size_t) for k in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
                'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]
    ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p
    api=ctypes.windll.psapi.GetProcessMemoryInfo
    api.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
    api.restype=ctypes.c_int
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not api(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(counters),counters.cb):
        raise OSError('GetProcessMemoryInfo failed')
    return {'rss_bytes':counters.WorkingSetSize,'peak_rss_bytes':counters.PeakWorkingSetSize}


def gpu():
    try:
        data=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],
            creationflags=subprocess.CREATE_NO_WINDOW,timeout=5,text=True)
        return int(data.strip().splitlines()[0])*1024*1024
    except (OSError,subprocess.SubprocessError,ValueError):
        return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('model');parser.add_argument('device',choices=['cpu','cuda'])
    args=parser.parse_args();os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    if args.device=='cuda':
        from app.engine.runtime.cuda_libraries import load_cuda_libraries
        load_cuda_libraries()
    import ctranslate2
    compute=os.environ.get('AW084_COMPUTE') or ('int8_float16' if args.device=='cuda' else 'int8')
    options=InferenceOptions(args.device,compute,8,4,2048,384,512)
    assert options.compute_type in ctranslate2.get_supported_compute_types(args.device)
    b=backend(args.model);runtime=RuntimeManager({'m2m100':b},idle_timeout_seconds=0)
    data={'model':args.model,'device':args.device,'options':dict(device=options.device,compute_type=options.compute_type,
          threads=8,beam=4,batch_tokens=2048,max_input_tokens=384,max_decode=512),'memory':{},'rows':[],'smoke':[]}
    data['model_resource_root']=str(getattr(b,'root',getattr(b.models,'root',None)))
    startgpu=gpu();data['memory']['before']={**memory(),'gpu_total_used_bytes':startgpu}
    stop=threading.Event();samples=[]
    def sample():
        while not stop.wait(.2):samples.append({**memory(),'gpu_total_used_bytes':gpu()})
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    cancelled=threading.Event()
    def translate(text,source='zh',target='ru'):
        with offline_scope():
            return runtime.run('m2m100',TranslationRequest(text,source,target),PairKind.DIRECT,options,cancelled).text
    try:
        started=time.perf_counter();b._load(options);data['load_seconds']=time.perf_counter()-started
        data['memory']['loaded']={**memory(),'gpu_total_used_bytes':gpu()}
        started=time.perf_counter();translate('请检查测量点。');data['first_inference_seconds']=time.perf_counter()-started
        data['memory']['idle_loaded']={**memory(),'gpu_total_used_bytes':gpu()}
        cases=json.loads((ROOT/'qa/aw084/semantic_gold.json').read_text('utf-8'))['entries']
        for case in cases:
            started=time.perf_counter()
            try:row={'id':case['id'],'text':translate(case['source_zh'])}
            except Exception as error:row={'id':case['id'],'error':type(error).__name__,'detail':str(error)}
            row['seconds']=time.perf_counter()-started;data['rows'].append(row)
            print(args.model,args.device,len(data['rows']),len(cases),row['seconds'],flush=True)
        latency=[r['seconds'] for r in data['rows']]
        total=sum(latency)
        data['warm']={'total_seconds':total,'median_seconds':statistics.median(latency),
                      'p95_seconds':sorted(latency)[int(.95*(len(latency)-1))],
                      'segments_per_second':len(cases)/total,'characters_per_second':sum(len(c['source_zh']) for c in cases)/total}
        if args.device=='cuda':
            for src,tgt,text in [('ru','zh','Если длина наконечника регулируется, удлините его на разницу высот.'),
                                 ('ru','zh','Не снимайте крышку радиатора при горячем двигателе.'),
                                 ('en','ru','Do not start the pump before the valve is open.'),
                                 ('ru','en','Не запускайте насос до открытия клапана.'),
                                 ('en','de','Do not start the pump before the valve is open.'),
                                 ('de','en','Starten Sie die Pumpe nicht, bevor das Ventil geöffnet ist.'),
                                 ('en','fr','Do not start the pump before the valve is open.'),
                                 ('fr','en','Ne démarrez pas la pompe avant que la vanne soit ouverte.'),
                                 ('en','es','Do not start the pump before the valve is open.'),
                                 ('es','en','No arranque la bomba antes de abrir la válvula.'),
                                 ('en','ja','Do not start the pump before the valve is open.'),
                                 ('ja','en','バルブを開く前にポンプを始動しないでください。')]:
                try:data['smoke'].append({'source':src,'target':tgt,'input':text,'output':translate(text,src,tgt)})
                except Exception as e:data['smoke'].append({'source':src,'target':tgt,'error':type(e).__name__})
        data['memory']['inference_samples']=samples[:]
        runtime.release_models();data['memory']['after_unload']={**memory(),'gpu_total_used_bytes':gpu()}
        assert b._translator is None
        data['runtime_imports']={name:bool(name in sys.modules) for name in ['torch','transformers','huggingface_hub']}
    except Exception as error:
        data['failure']={'type':type(error).__name__,'detail':str(error)}
        import traceback;traceback.print_exc()
    finally:
        stop.set();thread.join(10);runtime.shutdown()
        (ROOT/'qa/aw084'/f'{args.model}-{args.device}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
        print('COMPLETE',args.model,args.device,data.get('warm'),data.get('failure'),flush=True)


if __name__=='__main__':main()
