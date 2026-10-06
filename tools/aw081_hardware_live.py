"""Compact read-only progress snapshot; never starts engines or OCR."""
from collections import deque
import json
from pathlib import Path
from statistics import mean
import psutil
root=Path(__file__).resolve().parents[1]/'qa/aw081/hardware_scaling_20'
progress=json.loads((root/'live_progress.json').read_text('utf8'))
path=root/'runs'/progress['label']/'resource_samples.jsonl'
result={k:progress[k] for k in ('label','config','completed','total','phase')}
workers=[]
for process in psutil.process_iter(['pid','cmdline']):
    try:
        cmd=process.info['cmdline'] or []
        if any(str(x).endswith(('aw081_hardware_scaling_20.py','aw081_hardware_easy_first.py')) for x in cmd) and '--label' in cmd and cmd[cmd.index('--label')+1]==progress['label']:
            for child in process.children(recursive=True):
                args=child.cmdline()
                if 'app.ocr.runtime.worker' in args:workers.append(dict(pid=child.pid,cuda_visible_devices=child.environ().get('CUDA_VISIBLE_DEVICES','UNSET')))
    except (psutil.Error,IndexError):continue
result['ocr_worker_device_visibility']=list({w['pid']:w for w in workers}.values())
if path.exists():
    with path.open(encoding='utf8') as f:samples=[json.loads(x) for x in deque(f,maxlen=45)]
    if samples:
        last=samples[-1];logical=json.loads((root/'hardware_summary.json').read_text('utf8'))['logical_processors']
        result.update(elapsed_minutes=round(last['elapsed']/60,2),
            cpu_machine_percent_last45=round(mean(x['process_tree_cpu_percent']/logical for x in samples),2),
            rss_gib=round(last['rss_bytes']/1024**3,2),commit_peak_gib=round(last['job_peak_commit_bytes']/1024**3,2),
            available_ram_gib=round(last['system_available_ram_bytes']/1024**3,2),
            ocr_rpc_active=last['active_ocr'],nmt_native_inference_active=last['active_model'])
        gpu=[x['gpu_device_wide'] for x in samples if x.get('gpu_device_wide')]
        if gpu:result.update(gpu_device_util_last45=round(mean(x['utilization'] for x in gpu),2),
            vram_device_mib=last['gpu_device_wide']['used_mib'],gpu_temperature_c=last['gpu_device_wide']['temperature_c'])
print(json.dumps(result,ensure_ascii=False))
