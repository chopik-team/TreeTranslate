"""Supplementary Windows counters; no models, no configuration changes."""
from collections import defaultdict
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
from time import time,sleep,perf_counter
import psutil
ROOT=Path(__file__).resolve().parents[1];QA=ROOT/'qa/aw081/hardware_scaling_20'


def snapshot(pids):
    ids=','.join(str(int(pid)) for pid in sorted(set(pids))) or '-1'
    script=r'''$ErrorActionPreference='Stop'; $ids=@(PID_LIST)
    $m=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object { $_.Name -match '^pid_(\d+)_' -and $ids -contains [int]$Matches[1] } | Select-Object Name,DedicatedUsage,SharedUsage)
    $e=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | Where-Object { $_.Name -match '^pid_(\d+)_' -and $ids -contains [int]$Matches[1] } | Select-Object Name,UtilizationPercentage)
    $p=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory | Select-Object PageReadsPersec,PagesInputPersec,PagesOutputPersec,AvailableMBytes
    [ordered]@{gpu_process_memory=$m;gpu_engines=$e;system_paging=$p}|ConvertTo-Json -Depth 5 -Compress
    '''.replace('PID_LIST',ids)
    encoded=base64.b64encode(script.encode('utf-16le')).decode()
    started=perf_counter()
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',encoded],
        capture_output=True,text=True,encoding='utf8',errors='replace',timeout=30,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Windows counter query failed: '+result.stderr[:160])
    data=json.loads(result.stdout);data['query_seconds']=perf_counter()-started
    data['process_tree_dedicated_gpu_bytes']=sum(int(r['DedicatedUsage']) for r in data['gpu_process_memory'])
    data['process_tree_shared_gpu_bytes']=sum(int(r['SharedUsage']) for r in data['gpu_process_memory'])
    engines=defaultdict(float)
    for row in data['gpu_engines']:
        name=re.sub(r'^pid_\d+_','',row['Name'])
        if '_engtype_3D' in name or '_engtype_Compute' in name:engines[name]+=float(row['UtilizationPercentage'])
    data['busiest_owned_compute_or_3d_engine_percent']=max(engines.values(),default=None)
    data['scope']='WDDM per-PID dedicated/shared accounting; busiest sum of owned PID utilization per compute/3D engine, not nvidia-smi SM utilization. System hard-fault disk counters include image/file-backed reads, not just pagefile and not process attribution.'
    return data


def run():
    path=QA/'windows_resource_sidecar.jsonl'
    with path.open('a',encoding='utf8',buffering=1) as output:
        while not (QA/'completion_receipt.json').exists():
            groups=defaultdict(set)
            for process in psutil.process_iter(['pid','cmdline']):
                try:
                    cmd=process.info['cmdline'] or []
                    if any(str(x).endswith(('aw081_hardware_scaling_20.py','aw081_hardware_easy_first.py')) for x in cmd) and 'run' in cmd and '--label' in cmd:
                        label=cmd[cmd.index('--label')+1]
                    elif any(str(x).endswith('aw081_hardware_probe.py') for x in cmd):label='residency_probe'
                    else:continue
                    groups[label].add(process.pid)
                    groups[label].update(p.pid for p in process.children(recursive=True))
                except (psutil.Error,IndexError):continue
            if groups:
                all_pids=set().union(*groups.values());started=time()
                try:
                    data=snapshot(all_pids)
                    for label,pids in groups.items():
                        row=dict(label=label,utc_started=started,utc_completed=time(),pids=sorted(pids),**data)
                        sampler=QA/('residency_probe' if label=='residency_probe' else 'runs/'+label)/'resource_samples.jsonl'
                        row['measured_window_observed']=sampler.exists() and sampler.stat().st_size>0 and time()-sampler.stat().st_mtime<6
                        output.write(json.dumps(row)+'\n')
                except Exception as exc:output.write(json.dumps(dict(utc_started=started,error_type=type(exc).__name__,error=str(exc)[:200]))+'\n')
            sleep(20)


if __name__=='__main__':run()
