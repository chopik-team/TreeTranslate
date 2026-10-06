"""Offline analysis only; does not launch translations or edit production."""
from collections import Counter
import itertools
import json
import math
import re
import sqlite3
from pathlib import Path
from statistics import mean
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw081_hardware_scaling_20 import QA,CONFIGS,ORDER
from tools.aw081_speed_calibration_100 import save
from tools.aw081_speed_calibration_report import percentile


def equivalence(label,reference='mid'):
    a=QA/'runs'/reference;b=QA/'runs'/label
    required=['fingerprints.json','candidates.json','writer.json']
    if not all((p/file).exists() for p in (a,b) for file in required):
        return dict(status='UNAVAILABLE',reference=reference,reason='reference/run output evidence incomplete')
    differences=[]
    for name in required:
        before=json.loads((a/name).read_text('utf8'));after=json.loads((b/name).read_text('utf8'))
        for member in sorted(set(before)|set(after)):
            if before.get(member)!=after.get(member):
                fields=[]
                if isinstance(before.get(member),dict) and isinstance(after.get(member),dict):
                    fields=[k for k in set(before[member])|set(after[member]) if before[member].get(k)!=after[member].get(k)]
                differences.append(dict(evidence=name,member=member,fields=fields))
    return dict(status='PASS' if not differences else 'FAIL',reference=reference,differences=differences,
        policy='exact candidate text/status/protected IDs/source-preserved counts/writer result; normalized PDF object geometry rounds at 1e-5 points; first/last-page RGB hashes on four fixed bucket representatives; failed exact source SHA/path')


def analyze_run(directory):
    e=json.loads((directory/'execution.json').read_text('utf8'));wall=e['wall_seconds']
    s=json.loads((directory/'run_summary.json').read_text('utf8')) if (directory/'run_summary.json').exists() else {}
    samples=[json.loads(x) for x in (directory/'resource_samples.jsonl').read_text('utf8').splitlines()] if (directory/'resource_samples.jsonl').exists() else []
    starts={x['member']:x['elapsed'] for x in e['events'] if x['event']=='document_start'}
    completions=[x for x in e['events'] if x['event']=='member_packaged']
    fingerprints=json.loads((directory/'fingerprints.json').read_text('utf8')) if (directory/'fingerprints.json').exists() else {}
    translated_completions=[x['elapsed'] for x in completions if fingerprints.get(x['source_member'],{}).get('status')=='TRANSLATED']
    latencies=[x['elapsed']-starts[x['source_member']] for x in completions]
    gpu=[x['gpu_device_wide'] for x in samples if x.get('gpu_device_wide')]
    cpu=[x['process_tree_cpu_percent']/16 for x in samples]
    stages=Counter();calls=Counter()
    for line in (directory/'timing_events.jsonl').read_text('utf8').splitlines():
        x=json.loads(line);stages[x['stage']]+=x['seconds'];calls[x['stage']]+=1
    batches=json.loads((directory/'batch_calls.json').read_text('utf8')) if (directory/'batch_calls.json').exists() else []
    model_loads=Counter();model_load_seconds=Counter()
    for line in (directory/'timing.log').read_text('utf8').splitlines():
        if 'run='+str(e['run_id'])+' ' not in line:continue
        match=re.search(r'process=(m2m100_model_load|argos_model_load) event=end .*seconds=([0-9.]+)',line)
        if match:model_loads[match[1]]+=1;model_load_seconds[match[1]]+=float(match[2])
    eq=equivalence(e['label'])
    sidecar=QA/'windows_resource_sidecar.jsonl'
    windows=[json.loads(x) for x in sidecar.read_text('utf8').splitlines()] if sidecar.exists() else []
    windows=[x for x in windows if x.get('label')==e['label'] and x.get('measured_window_observed')]
    row=dict(label=e['label'],config=e['config'],configuration=e['resource_configuration'],
        order=e['order'],sustained=e['sustained'],run_id=e['run_id'],wall_seconds=wall,
        processed=len(completions),translated=s.get('translated_documents'),failed=s.get('failed_documents'),fatal=e['fatal'],
        docs_hour=len(completions)*3600/wall,source_pages_hour=39*3600/wall if len(completions)==20 else None,
        segments_second=s.get('counters',{}).get('processed_segments',0)/wall,
        latency=dict(median=percentile(latencies,.5),p90=percentile(latencies,.9),p95=percentile(latencies,.95)),
        milestones_seconds={str(p):completions[i-1]['elapsed'] if len(completions)>=i else None for p,i in [(25,5),(50,10),(75,15),(100,20)]},
        first_document_start_seconds=min(starts.values()) if starts else None,
        first_document_complete_seconds=completions[0]['elapsed'] if completions else None,
        first_translated_document_complete_seconds=translated_completions[0] if translated_completions else None,
        cpu=dict(average_machine_percent=mean(cpu) if cpu else None,peak_machine_percent=max(cpu) if cpu else None,
            process_cpu_time_seconds=e['cpu_time_seconds'],idle_sample_seconds=sum(x<5 for x in cpu),
            queue_starvation='UNAVAILABLE: no independent prepared-document work queue',
            threads=e['resource_configuration']['threads'],ocr_threads=e['resource_configuration']['ocr_threads'],
            scope='process tree core-percent divided by 16 logical processors; existing backend pools, not a Windows CPU hard quota'),
        ram=dict(average_rss_bytes=mean(x['rss_bytes'] for x in samples) if samples else None,
            peak_rss_bytes=max((x['rss_bytes'] for x in samples),default=None),
            peak_sampled_private_commit_bytes=max((x['private_commit_bytes'] for x in samples),default=None),
            peak_job_commit_bytes=max((x['job_peak_commit_bytes'] or 0 for x in samples),default=None),
            commit_peak_scope='Windows Job lifetime high-water mark includes excluded warmup; sampled RSS/private commit cover measured window only. Summed process RSS can count shared pages more than once.',
            available_system_min_bytes=min((x['system_available_ram_bytes'] for x in samples),default=None),
            glossary_cache_entries=e['glossary_cache_size'],glossary_cache_hits=e.get('glossary_cache_hits'),
            glossary_cache_misses=e.get('glossary_cache_misses'),hard_paging_activity='SYSTEM_SCOPE_SUPPLEMENTARY_CIM' if windows else 'UNAVAILABLE_NOT_CAPTURED'),
        gpu=dict(average_device_utilization=mean(x['utilization'] for x in gpu) if gpu else None,
            peak_device_utilization=max((x['utilization'] for x in gpu),default=None),
            peak_device_vram_mib=max((x['used_mib'] for x in gpu),default=None),
            average_resident_device_vram_mib=mean(x['used_mib'] for x in gpu) if gpu else None,
            device_idle_sample_seconds=sum(x['utilization']<=3 for x in gpu),process_gpu_utilization='SUPPLEMENTARY_WDDM_ENGINE_ACCOUNTING' if windows else 'UNAVAILABLE_NOT_CAPTURED',
            treetranslate_gpu_idle_time='UNAVAILABLE: device telemetry includes unrelated applications',
            process_vram='SUPPLEMENTARY_WDDM_CIM_ACCOUNTING' if windows else 'UNAVAILABLE_NOT_CAPTURED',allocator_scope=e['vram_limit_scope'],
            actual_backend_devices=dict(Counter(x['backend']+'/'+x['device'] for x in e['models'])),
            backend_failures=sum(not x['success'] for x in e['models']),fallback_attempts=sum(x['fallback'] for x in e['models']),
            max_actual_nmt_batch_sequences=max((x['sequences'] for x in batches),default=None),
            max_actual_nmt_batch_tokens=max((x['tokens'] for x in batches),default=None),
            gpu_queue_depth=1,simultaneous_ocr_model_samples=sum(bool(x.get('active_ocr')) and bool(x.get('active_model')) for x in samples)),
        ocr=dict(successful_worker_calls=len(e['ocr_calls']),actual_devices=dict(Counter(x['device'] for x in e['ocr_calls'])),
            model_load_seconds=sum(x.get('load_seconds') or 0 for x in e['ocr_calls']),
            inference_seconds=sum(x.get('inference_seconds') or 0 for x in e['ocr_calls']),
            load_calls_over_10ms=sum((x.get('load_seconds') or 0)>.01 for x in e['ocr_calls']),
            worker_oom_count='UNAVAILABLE: worker vendor exceptions become generic OCR error codes'),
        model_loads=dict(counts=dict(model_loads),seconds=dict(model_load_seconds)),
        backend_error_types=dict(Counter(x['error_type'] for x in e['models'] if not x['success'])),
        recorded_nmt_oom_events=s.get('counters',{}).get('gpu_oom_events'),
        supplementary_windows_counters=dict(status='CAPTURED_SUPPLEMENTARY' if windows else 'UNAVAILABLE_NOT_CAPTURED',
            samples=len(windows),approximate_period_seconds=20,
            capture_span_percent=min(100,100*(max(x['utc_completed'] for x in windows)-min(x['utc_started'] for x in windows))/wall) if windows else None,
            owned_dedicated_gpu_peak_bytes=max((x['process_tree_dedicated_gpu_bytes'] for x in windows),default=None),
            owned_dedicated_gpu_average_bytes=mean(x['process_tree_dedicated_gpu_bytes'] for x in windows) if windows else None,
            busiest_owned_engine_average_percent=mean(x['busiest_owned_compute_or_3d_engine_percent'] or 0 for x in windows) if windows else None,
            busiest_owned_engine_peak_percent=max((x['busiest_owned_compute_or_3d_engine_percent'] or 0 for x in windows),default=None),
            system_page_reads_average=mean(x['system_paging']['PageReadsPersec'] for x in windows) if windows else None,
            system_pages_input_peak=max((x['system_paging']['PagesInputPersec'] for x in windows),default=None),
            system_pages_output_peak=max((x['system_paging']['PagesOutputPersec'] for x in windows),default=None),
            scope='Started during run7; first four completed runs lack counters, and the scheduler adapter was added to observer matching during easy-first. Capture span is first-to-last query span, not continuous coverage. WDDM per-PID accounting and busiest compute/3D engine are supplemental; 20s sampling can miss short bursts. System hard-fault reads include file/image-backed disk reads; no per-process hard-paging attribution.'),
        thermal=dict(gpu_peak_temperature_c=max((x['temperature_c'] for x in gpu),default=None),
            gpu_average_clock_mhz=mean(x['clock_mhz'] for x in gpu) if gpu else None,
            gpu_min_clock_mhz=min((x['clock_mhz'] for x in gpu),default=None),
            gpu_peak_power_w=max((x['power_w'] for x in gpu),default=None),
            cpu_temperature='UNAVAILABLE',cpu_actual_clock='UNAVAILABLE'),
        stages_inclusive_seconds=dict(stages),stage_calls=dict(calls),equivalence=eq,
        eligible=eq['status']=='PASS' and not e['fatal'] and len(completions)==20 and not e['monitor_errors'],
        production_unchanged=e['production_unchanged'],source_immutable=e['source_immutable'],monitor_errors=e['monitor_errors'])
    return row


def effect_class(gain):
    if gain < -3:return 'regression'
    return 'practical saturation/no demonstrated gain' if gain<3 else 'weak' if gain<7 else 'noticeable' if gain<=15 else 'strong'


def factorial(rows):
    data={r['config']:r for r in rows if r['label'] in ORDER and r['config']!='mid'}
    eligible=len(data)==8 and all(r['eligible'] for r in data.values())
    completed=len(data)==8 and all(r['processed']==20 and not r['fatal'] for r in data.values())
    result=dict(status='COMPLETE' if eligible else 'COMPLETE_TRIALS_OUTPUT_NON_EQUIVALENT' if completed else 'INCOMPLETE_OR_FAILED_TRIALS',
        recorded_factorial_arms=len(data),planned_factorial_arms=8,operational_matrix_complete=completed,
        default_output_equivalence_valid=eligible,
        main_effects={},interactions={},conditional_pairs=[],factor_scope='Bundled runtime-resource controls, not CPU/GPU hardware replacement or isolated memory-cap elasticity.')
    for factor in ['cpu','gpu','ram']:
        for low in data.values():
            if low['configuration'][factor]!='LOW':continue
            high=next((r for r in data.values() if r['configuration'][factor]=='HIGH' and all(r['configuration'][k]==low['configuration'][k] for k in ['cpu','gpu','ram'] if k!=factor)),None)
            if high:
                if low['docs_hour']<=0 or high['docs_hour']<=0 or low['cpu']['average_machine_percent'] is None or high['cpu']['average_machine_percent'] is None:
                    result['conditional_pairs'].append(dict(factor=factor,low=low['label'],high=high['label'],eligible=False,reason='fatal/incomplete telemetry'))
                    continue
                gain=100*(high['docs_hour']/low['docs_hour']-1)
                pair_eq=equivalence(high['label'],low['label'])
                result['conditional_pairs'].append(dict(factor=factor,low=low['label'],high=high['label'],
                    eligible=low['eligible'] and high['eligible'],throughput_gain_percent=gain,
                    pairwise_equivalence=pair_eq['status'],
                    within_pair_output_equivalent=pair_eq['status']=='PASS',
                    wall_delta_seconds=high['wall_seconds']-low['wall_seconds'],docs_hour_delta=high['docs_hour']-low['docs_hour'],
                    cpu_average_delta=high['cpu']['average_machine_percent']-low['cpu']['average_machine_percent'],
                    rss_peak_delta_bytes=high['ram']['peak_rss_bytes']-low['ram']['peak_rss_bytes'],
                    vram_device_peak_delta_mib=(high['gpu']['peak_device_vram_mib'] or 0)-(low['gpu']['peak_device_vram_mib'] or 0),classification=effect_class(gain)))
    result['quality_preserving_conditional_main_effects']={}
    for factor in ['cpu','gpu','ram']:
        pairs=[p for p in result['conditional_pairs'] if p['factor']==factor]
        if len(pairs)==4 and all(p.get('within_pair_output_equivalent') for p in pairs):
            gain=100*(math.exp(mean(math.log(1+p['throughput_gain_percent']/100) for p in pairs))-1)
            result['quality_preserving_conditional_main_effects'][factor]=dict(throughput_gain_percent=gain,
                classification=effect_class(gain),scope='Pairwise output invariant within four fixed other-factor strata; does not establish equivalence to current MID or approve a mode differing from MID.')
    def contrasts(data):
        effects={};interactions={}
        for factor in ['cpu','gpu','ram']:
            low=mean(math.log(r['docs_hour']) for r in data.values() if r['configuration'][factor]=='LOW')
            high=mean(math.log(r['docs_hour']) for r in data.values() if r['configuration'][factor]=='HIGH')
            gain=100*(math.exp(high-low)-1)
            effects[factor]=dict(throughput_gain_percent=gain,classification=effect_class(gain),method='geometric mean HIGH/LOW throughput')
        for size in [2,3]:
            for factors in itertools.combinations(['cpu','gpu','ram'],size):
                beta=mean(math.log(r['docs_hour'])*math.prod(1 if r['configuration'][f]=='HIGH' else -1 for f in factors) for r in data.values())
                interactions['x'.join(factors)]=dict(log_coefficient=beta,ratio_of_ratios_percent=100*(math.exp((2**size)*beta)-1),method='log-throughput full-factorial contrast; 2-way exp(4 beta), 3-way exp(8 beta)')
        return effects,interactions
    if eligible:result['main_effects'],result['interactions']=contrasts(data)
    if len(data)==8 and all(r['processed']==20 and not r['fatal'] and r['docs_hour']>0 for r in data.values()):
        effects,interactions=contrasts(data)
        result['raw_exploratory_contrasts']=dict(main_effects=effects,interactions=interactions,
            output_equivalence_valid=eligible,
            limitation='When output equivalence fails, these numbers mix resource changes and changed OCR/translation workload. They cannot justify quality-preserving acceleration, resource modes or full-corpus scaling.')
    return result


def equivalence_diagnostics(rows):
    reference=QA/'runs'/'mid'
    if not (reference/'candidates.json').exists():return
    manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'))
    metadata={d['member_path']:d for d in manifest['documents']}
    def profiles(directory):
        receipt=json.loads((directory/'execution.json').read_text('utf8'))
        if not receipt.get('logs'):return {}
        path=Path(receipt['logs'])/'index.sqlite3'
        if not path.exists():return {}
        with sqlite3.connect(path) as con:
            documents=[json.loads(x[0]) for x in con.execute('SELECT payload FROM documents')]
        return {d['archive_member_path']:d.get('profiler') for d in documents}
    baseline=json.loads((reference/'candidates.json').read_text('utf8'));base_profiles=profiles(reference)
    result=[]
    for row in rows:
        if row['equivalence']['status']!='FAIL':continue
        directory=QA/'runs'/row['label'];candidates=json.loads((directory/'candidates.json').read_text('utf8'))
        run_profiles=profiles(directory);documents=[]
        for member in sorted(set(baseline)|set(candidates)):
            a=baseline.get(member,[]);b=candidates.get(member,[])
            if a==b:continue
            ca=Counter(x['source'] for x in a);cb=Counter(x['source'] for x in b)
            targets_a={};targets_b={}
            for x in a:targets_a.setdefault(x['source'],set()).add(json.dumps({k:v for k,v in x.items() if k!='source'},ensure_ascii=False,sort_keys=True))
            for x in b:targets_b.setdefault(x['source'],set()).add(json.dumps({k:v for k,v in x.items() if k!='source'},ensure_ascii=False,sort_keys=True))
            same_source_changes=[dict(source=s,reference_targets=sorted(targets_a[s]),run_targets=sorted(targets_b[s])) for s in targets_a.keys()&targets_b.keys() if targets_a[s]!=targets_b[s]]
            documents.append(dict(member=member,classification=metadata[member]['classification'],
                reference_candidates=len(a),run_candidates=len(b),
                reference_only_source_strings=[dict(source=s,count=c) for s,c in (ca-cb).items()],
                run_only_source_strings=[dict(source=s,count=c) for s,c in (cb-ca).items()],
                same_source_changed_target_count=len(same_source_changes),same_source_changed_target_examples=same_source_changes[:8],
                reference_profiler=base_profiles.get(member),run_profiler=run_profiles.get(member),
                profiler_changed=base_profiles.get(member)!=run_profiles.get(member)))
        result.append(dict(label=row['label'],documents=documents,conclusion='Rejected for exact output equivalence. Changed OCR source can alter existing document profiling and term selection; multiple bundled controls prevent attributing endpoint differences to one factor before factorial contrasts. No manual semantic grade or term correction performed.'))
    save(QA/'equivalence_diagnostics.json',dict(reference='mid',runs=result))


def main():
    runs=[analyze_run(p.parent) for p in sorted((QA/'runs').glob('*/execution.json'))]
    (QA/'runs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in runs),'utf8')
    with (QA/'resource_samples.jsonl').open('w',encoding='utf8') as destination:
        for r in runs:
            for line in (QA/'runs'/r['label']/'resource_samples.jsonl').read_text('utf8').splitlines():
                destination.write(json.dumps(dict(label=r['label'],config=r['config'],sample_kind='primary_1s',**json.loads(line)))+'\n')
        sidecar=QA/'windows_resource_sidecar.jsonl'
        if sidecar.exists():
            for line in sidecar.read_text('utf8').splitlines():destination.write(json.dumps(dict(sample_kind='supplementary_windows_20s',**json.loads(line)))+'\n')
    result=factorial(runs);save(QA/'factorial_analysis.json',result)
    equivalence_diagnostics(runs)
    save(QA/'analysis_checkpoint.json',dict(completed_runs=len(runs),eligible=[r['label'] for r in runs if r['eligible']],factorial_status=result['status']))
    for r in runs:print(r['label'],round(r['wall_seconds'],2),round(r['docs_hour'],2),r['translated'],r['failed'],r['equivalence']['status'])
    print('FACTORIAL',json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
