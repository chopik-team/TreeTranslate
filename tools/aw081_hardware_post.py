"""Bounded post-matrix experiments. Waits; never overlaps GPU trials."""
import json
import subprocess
import sys
from pathlib import Path
from time import sleep,perf_counter
from statistics import median
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw081_hardware_scaling_20 import QA,CONFIGS,ORDER
from tools.aw081_speed_calibration_100 import save


def command(*args):
    result=subprocess.run([sys.executable,'-X','utf8',*args],cwd=ROOT)
    if result.returncode:raise RuntimeError(f'QA command failed: {args[0]} / exit {result.returncode}')


def measure(label,config,order='original',sustained=False):
    path=QA/'runs'/label
    if (path/'execution.json').exists():
        receipt=json.loads((path/'execution.json').read_text('utf8'))
        if receipt['fatal']:raise RuntimeError(f'Previously failed run {label}; no automatic retry')
        assert (path/'fingerprints.json').exists();return
    entry='tools/aw081_hardware_easy_first.py' if order=='easy_first' else 'tools/aw081_hardware_scaling_20.py'
    args=[entry,'run','--label',label,'--config',config,'--order',order]
    if sustained:args.append('--sustained')
    command(*args)
    receipt=json.loads((path/'execution.json').read_text('utf8'))
    if receipt['fatal']:raise RuntimeError(f'Global failure in {label}; no automatic retry')


def main():
    # The suite publishes execution after shutting down its workers and performs
    # output fingerprinting afterwards. Waiting for both avoids compute overlap.
    def finished(label):
        path=QA/'runs'/label/'execution.json'
        return path.exists() and (json.loads(path.read_text('utf8'))['fatal'] or (path.parent/'fingerprints.json').exists())
    while not all(finished(label) for label in ORDER):
        sleep(10)
    command('tools/aw081_hardware_analysis.py')
    rows=[json.loads(x) for x in (QA/'runs.jsonl').read_text('utf8').splitlines()]
    eligible=sorted([r for r in rows if r['label'] in ORDER and r['eligible']],key=lambda r:-r['docs_hour'])
    if not eligible:raise RuntimeError('No equivalent completed control available for scheduler trial')
    best=eligible[0]
    if len(eligible)>=2:second=eligible[1]
    else:
        completed=sorted([r for r in rows if r['label'] in ORDER and r['processed']==20 and not r['fatal'] and r['config']!=best['config']],key=lambda r:-r['docs_hour'])
        if not completed:raise RuntimeError('No second completed configuration available for diagnostic sustained trial')
        second=completed[0]
    plan=dict(top2=[best['config'],second['config']],scheduler_config=best['config'],
        scheduler_order=['best_repeat_original','best_easy_first'],sustained_order=[second['config'],best['config']],
        output_reference='mid',maximum_additional_saturation_runs=4,
        top2_output_eligible=[best['eligible'],second['eligible']],
        selection_note='If fewer than two variants pass output equivalence, the second sustained run diagnoses the fastest rejected configuration; it is not a speed winner or mode candidate.',
        main_scripts_unchanged=True,all_inputs='same frozen 20 PDFs, no full ZIP')
    save(QA/'post_matrix_manifest.json',plan)
    factor=json.loads((QA/'factorial_analysis.json').read_text('utf8'))
    # An unused ceiling is not evidence for a higher ceiling. Extra sweeps are
    # permitted only when a strong contrast and a binding HIGH cap coincide.
    candidates=[];checks=[]
    for name in ['cpu','gpu','ram']:
        effect=factor['main_effects'].get(name,{})
        high=[r for r in eligible if r['configuration'][name]=='HIGH']
        if name=='gpu':binding=any((r['gpu']['peak_device_vram_mib'] or 0)>r['configuration']['vram_gib']*1024*.90 for r in high)
        elif name=='ram':binding=any((r['ram']['peak_job_commit_bytes'] or 0)>r['configuration']['ram_gib']*1024**3*.90 or r['ram']['glossary_cache_entries']>=r['configuration']['glossary_cache_entries']*.95 for r in high)
        else:binding=any(r['cpu']['average_machine_percent']>75 for r in high)
        strong=effect.get('classification')=='strong'
        checks.append(dict(factor=name,strong=strong,high_budget_observed_binding=binding,
            reason='Additional sweep requires useful strong gain and remaining observed resource pressure; inactive ceilings are not filled artificially.'))
        if strong and binding:candidates.append(name)
    # At most four QA refinements; keep source/models/quality constant. CPU and
    # RAM refinements lie between measured endpoints and keep OS reserve.
    specs=[]
    for factor_name in candidates:
        values=[10,12] if factor_name=='cpu' else [16,20] if factor_name=='ram' else [11.0]
        for value in values:
            if len(specs)>=4:break
            cfg=dict(best['configuration'])
            if factor_name=='cpu':cfg.update(threads=value,ocr_threads=value,cpu='SWEEP')
            elif factor_name=='ram':cfg.update(ram_gib=value,ram='SWEEP')
            else:cfg.update(vram_gib=value,gpu='SWEEP')
            specs.append(dict(label=f'sweep_{factor_name}_{value}',configuration=cfg))
    save(QA/'saturation_decision.json',dict(status='PLANNED' if specs else 'NO_ADDITIONAL_SWEEP_JUSTIFIED',checks=checks,
        additional_runs=specs,max_runs=4,limitation='Two endpoints alone do not establish a universal hardware knee; cap binding is an observed operational criterion, not proof of a causal hardware bottleneck.'))
    for spec in specs:
        label=spec['label']
        if not (QA/'runs'/label/'execution.json').exists():
            code='from tools.aw081_hardware_scaling_20 import CONFIGS,run; CONFIGS['+repr(label)+']='+repr(spec['configuration'])+'; run('+repr(label)+','+repr(label)+')'
            command('-c',code)
        if json.loads((QA/'runs'/label/'execution.json').read_text('utf8'))['fatal']:raise RuntimeError(f'Sweep fatal {label}')
    measure('best_repeat_original',best['config'])
    measure('best_easy_first',best['config'],'easy_first')
    for row in [second,best]:measure(row['config']+'_sustained',row['config'],sustained=True)
    if not (QA/'residency_overlap_probe.json').exists():command('tools/aw081_hardware_probe.py','--config',best['config'])
    command('tools/aw081_hardware_analysis.py')
    rows=[json.loads(x) for x in (QA/'runs.jsonl').read_text('utf8').splitlines()];by={r['label']:r for r in rows}
    original=by['best_repeat_original'];easy=by['best_easy_first']
    manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'))
    def key(d):
        i=d['source_inspection'];likelihood=2 if i['empty_native_pages'] or not i['native_alphabetic_chars'] else 1 if i['large_raster_pages'] else 0
        return likelihood,d['pages'],d['source_size'],d['member_path']
    started=perf_counter();sorted_sample=sorted(manifest['documents'],key=key);sort_seconds=perf_counter()-started
    ready={}
    for row in [original,easy]:
        receipt=json.loads((QA/'runs'/row['label']/'execution.json').read_text('utf8'))
        fp=json.loads((QA/'runs'/row['label']/'fingerprints.json').read_text('utf8'));events=[e for e in receipt['events'] if e['event']=='member_packaged']
        translated=[e['elapsed'] for e in events if fp[e['source_member']]['status']=='TRANSLATED']
        ready[row['label']]={str(i):translated[i-1] if len(translated)>=i else None for i in [1,5,10,15,20]}
    save(QA/'scheduler_analysis.json',dict(configuration=best['config'],original_run=original['label'],easy_run=easy['label'],
        exact_output_equivalence=original['equivalence']['status']=='PASS' and easy['equivalence']['status']=='PASS',
        throughput_gain_percent=100*(easy['docs_hour']/original['docs_hour']-1),
        eligible=original['eligible'] and easy['eligible'],original_milestones=original['milestones_seconds'],easy_milestones=easy['milestones_seconds'],
        translated_ready_seconds=ready,cheap_metadata_sort_seconds=sort_seconds,
        easy_order=[d['member_path'] for d in sorted_sample],
        limitations='Only iteration order changed; original inventory/context sampling/path reservation preserved. Metadata from frozen sample source inspection, no new OCR/model/profiler for sorting. Early readiness is member-packaging time, not a separately published archive.'))
    sustained=[]
    for row in [second,best]:
        warm=by[row['config']+'_sustained'];cold=by[row['label']]
        samples=[json.loads(x) for x in (QA/'runs'/warm['label']/'resource_samples.jsonl').read_text('utf8').splitlines()]
        active=[s['gpu_device_wide']['clock_mhz'] for s in samples if s.get('gpu_device_wide') and s['gpu_device_wide']['utilization']>=30]
        sustained.append(dict(configuration=row['config'],cold_run=cold['label'],warm_run=warm['label'],
            cold_wall_seconds=cold['wall_seconds'],warm_wall_seconds=warm['wall_seconds'],
            warm_throughput_gain_percent=100*(warm['docs_hour']/cold['docs_hour']-1),
            eligible=warm['eligible'] and cold['eligible'],exact_equivalence=warm['equivalence']['status'],
            cold_thermal=cold['thermal'],warm_thermal=warm['thermal'],warm_median_active_gpu_clock_mhz=median(active) if active else None,
            warm_peak_rss_bytes=warm['ram']['peak_rss_bytes'],warm_min_available_ram_bytes=warm['ram']['available_system_min_bytes'],
            cpu_temperature='UNAVAILABLE',hard_paging_activity='UNAVAILABLE'))
    save(QA/'sustained_analysis.json',dict(trials=sustained,best_original_repeat_drift_percent=100*(original['docs_hour']/best['docs_hour']-1),
        method='Each sustained trial first executes the same full20 as excluded warmup in the same process, then measures the fixed20 again. Top2 interleaved in reverse order. Device clocks at low utilization must not be interpreted as thermal throttling.',
        limitations='One warm repetition per configuration; no statistical confidence interval. CPU thermal and hard paging unavailable; device telemetry includes ambient GPU workloads.'))
    decision=json.loads((QA/'saturation_decision.json').read_text('utf8'))
    if specs:decision.update(status='COMPLETED',results=[dict(label=s['label'],eligible=by[s['label']]['eligible'],docs_hour=by[s['label']]['docs_hour']) for s in specs]);save(QA/'saturation_decision.json',decision)
    command('tools/aw081_hardware_report.py')
    save(QA/'completion_receipt.json',dict(status='EXPERIMENTS_COMPLETED',main_runs=9,
        additional_sweeps=len(specs),scheduler_runs=2,sustained_runs=2,source_members_per_run=20,
        source_pages_per_run=39,full_archive_run=False,production_changes=False,
        report=str(ROOT/'docs/AW0.81_HARDWARE_SCALING_20PDF.md')))
    print('POST_MATRIX_COMPLETE',flush=True)


if __name__=='__main__':main()
