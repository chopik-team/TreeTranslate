"""Read-only baseline/replay analysis and full tests of restored production."""
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean,median
from time import perf_counter
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

from tools.aw081_nmt_batch_scheduler_5pdf import ROOT,QA,read,save,frozen_hashes


def lines(path):return [json.loads(s) for s in Path(path).read_text('utf8').splitlines() if s.strip()]


def full_pytest():
    assert frozen_hashes()==read(QA/'baseline.json')['production_before']
    assert not (QA/'full_pytest.json').exists()
    before=frozen_hashes();start=perf_counter()
    with (QA/'pytest_stdout.txt').open('x',encoding='utf8') as output:
        result=subprocess.run([sys.executable,'-X','utf8','-m','pytest','-q','--junitxml='+str(QA/'pytest.xml')],cwd=ROOT,
                              stdout=output,stderr=subprocess.STDOUT)
    after=frozen_hashes();totals=Counter()
    for suite in ET.parse(QA/'pytest.xml').getroot().iter('testsuite'):
        for name in ('tests','failures','errors','skipped'):totals[name]+=int(suite.get(name,0))
    receipt=dict(status='PASS' if result.returncode==0 and before==after else 'FAIL',
        passed=totals['tests']-totals['failures']-totals['errors']-totals['skipped'],**totals,duration_seconds=perf_counter()-start,
        production_hashes_before=before,production_hashes_after=after,production_exact_measured_baseline=after==read(QA/'baseline.json')['production_before'],
        scope='Restored production plus six new benchmark replay gate regression tests; rejected prototype is archived, not imported')
    save(QA/'full_pytest.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if not k.startswith('production_hashes')}),flush=True)


def analyze():
    baseline=read(QA/'baseline.json');receipt=read(QA/'runs/baseline/run_manifest.json');raw=QA/'runs/baseline/raw'
    logs=Path(receipt['logs']);summary=read(logs/'run_summary.json');nmt=baseline['nmt'];routing=lines(logs/'routing.jsonl')
    stages=defaultdict(lambda:dict(calls=0,seconds=0.,failures=0))
    for row in lines(logs/'stages.jsonl'):
        for key,value in [('calls',row['count']),('seconds',row['seconds']),('failures',row['failures'])]:stages[row['stage']][key]+=value
    attempts=[r for r in routing if r.get('event')=='backend_attempt']
    resources=lines(raw/'resource_samples_tree.jsonl');gpu=[r['gpu_device_wide'] for r in resources if r.get('gpu_device_wide')]
    deltas=[max(0,resources[i]['elapsed']-resources[i-1]['elapsed']) for i in range(1,len(resources))]
    resource=dict(cpu_average_percent=sum(resources[i]['process_tree_cpu_percent']*deltas[i-1] for i in range(1,len(resources)))/sum(deltas),
        gpu_average_percent=mean(r['utilization'] for r in gpu) if gpu else None,
        peak_rss_bytes=max(r['rss_bytes'] for r in resources),peak_vram_mib=max(r['used_mib'] for r in gpu) if gpu else None,
        samples=len(resources),scope='CPU process tree, 100%=one logical core; GPU/VRAM device-wide, one-second samples; not kernel utilization')
    batchcounts=Counter(r['sequences'] for r in nmt['batches']);calls=nmt['calls']
    modelmetrics=dict(wall_seconds=baseline['wall_seconds'],docs_per_hour=5*3600/baseline['wall_seconds'],
        semantic_model_requests=len(nmt['requests']),physical_CT2_calls=calls,
        batch1=batchcounts[1],batch2=batchcounts[2],batch3_4=sum(v for k,v in batchcounts.items() if k in (3,4)),
        batch5_8=sum(v for k,v in batchcounts.items() if 5<=k<=8),average_sequences=nmt['sequences']/calls,
        median_sequences=nmt['median_sequences'],max_sequences=max(batchcounts),source_tokens=nmt['tokens'],average_tokens=nmt['tokens']/calls,
        median_tokens=nmt['median_tokens'],p90_tokens=sorted(r['tokens'] for r in nmt['batches'])[int(.9*(calls-1))],
        actual_CT2_seconds=nmt['inference_seconds'],model_translation_seconds=stages['model_translation']['seconds'],
        backend_attempts=len(attempts),failure_attempts=sum(not r['success'] for r in attempts),fallback_attempts=sum(r['fallback'] for r in attempts),
        m2m_requests=sum(r['backend']=='m2m100' for r in nmt['requests']),argos_requests=sum(r['backend']=='argos' for r in nmt['requests']),
        actual_CT2_model_loads=len(nmt['loads']),m2m_load_or_reuse=nmt['counts']['m2m100_load_or_reuse'],
        m2m_real_loads=sum('m2m100' in r.get('model','') for r in nmt['loads']),
        argos_real_loads=sum('m2m100' not in r.get('model','') for r in nmt['loads']))
    modelmetrics['m2m_resident_reuse']=modelmetrics['m2m_load_or_reuse']-modelmetrics['m2m_real_loads']
    lifecycle=lines(raw/'ocr_lifecycle.jsonl')
    modelmetrics.update(ocr=dict(recognize=stages['ocr_recognize'],inference_seconds=sum(r.get('seconds',0) for r in lifecycle if r['event']=='inference'),
                               model_loads=sum(r['event']=='model_load' for r in lifecycle)),
        glossary=receipt['lookup_profile'],writer=stages['pdf_write'],resources=resource)
    baseline['measurement_summary']=modelmetrics;baseline['document_summary']=summary
    baseline['label_note']='Baseline inherited /100 console label and FINAL_100PDF scope string only; scanner and archive both exactly five. Corrected future helper labels without repeating baseline.'
    save(QA/'baseline.json',baseline)
    replay=read(QA/'batch_replay.json')
    from app.engine.backends.m2m100_tokenizer import LocalM2M100Tokenizer
    tokenizer=LocalM2M100Tokenizer(ROOT/'vendor/models/m2m100-418m-int8/tokenizer')
    for size,stat in replay['results'].items():
        for row in stat['mismatches']:
            row['before_decoded']=tokenizer.decode(row['before'][0]);row['after_decoded']=tokenizer.decode(row['after'][0])
        stat['decoded_text_mismatches']=sum(r['before_decoded']!=r['after_decoded'] for r in stat['mismatches'])
        stat['inference_reduction_percent']=100*(1-stat['seconds']/replay['results']['1']['seconds'])
        stat['physical_call_reduction_percent']=100*(1-stat['calls']/replay['results']['1']['calls'])
    replay['interpretation']='Native replay speed only. Hypotheses and decoded text change without any model/options/token changes; larger batch is not universally equivalent. No final PDF benchmark.'
    save(QA/'batch_replay.json',replay)
    restored=frozen_hashes()==baseline['production_before']
    save(QA/'scheduler_design.json',dict(status='REJECTED_AND_ROLLED_BACK',prototype='rejected_prototype.zip',production_enabled=False,
        cause='DocumentJob loops synchronously: classify -> lookup_direct -> protected representation -> Knowledge/Glossary -> Router selects attempt -> Runtime.run -> CT2 -> placeholder restoration -> output guards -> serial retries/fallback -> next segment.',
        dependency_boundary='Only first immutable routed model attempt before original circuit check can enter frontier. Dependent guard/placeholder retry/fallback cannot enter same frontier. Known-only guard also stops admission until canonical commit.',
        design='Bounded intra-document suspended continuations on a persistent pool; only ONE semantic owner active; one native owner; canonical resume; no cross-document concurrency or artificial fill wait.',
        envelope=['request_id','document_sequence_id','segment_sequence_id','backend','model_root','device','source_language','target_language','prepared_source','frozen_options','fallback_kind'],
        compatibility='Same backend/model/source-target/options/device/compute/beam/input-output limits/threads/fallback kind. Exact source arrays and CT2 kwargs retained except expanded target_prefix.',
        limits=dict(max_sequences=8,max_source_tokens=256,max_short_sequence_tokens=32,max_prepared_bytes=1048576),
        hardware='Existing PipelineCapabilities; conservative residency/reserve; CPU, low RAM/VRAM or pressure reduces 8/4/2/1 without quality option changes.',
        errors='Batch-level error replays first singleton; later owners recheck original breaker/device/fallback. Per-item guard and decode-limit failure affects only owner. Cancellation wakes/discards suspended continuations.',
        targeted_tests=dict(passed=51,failures=0,errors=0,duration_seconds=33.20,scheduler_cases=20,
            coverage=['1/2/4/8','Unicode and Chinese','mixed lengths','IDs/numbers/placeholders','empty/noise','near input-token limit',
                      'one failing neighbor','fallback','circuit recheck','guard retry','canonical order','known guard boundary',
                      'cancel before/native/preparation wait','depth1/2 contexts','CPU/low VRAM/pressure']),
        veto='Broader captured native replay fails even batch2. No supported ceiling >1 proven. Changing models, compute type, beam or decoding to repair would cross frozen scope.',
        production_restored_exact=restored))
    save(QA/'nmt_profile.json',dict(before=modelmetrics,after=None,after_reason='Mandatory exact replay FAIL; no accepted scheduler, no final run',
        replay_only={size:{k:v for k,v in r.items() if k!='mismatches'} for size,r in replay['results'].items()},
        semantic_vs_physical='Baseline Runtime semantic requests include original fallback attempts; replay batches are native execution only, not new semantic requests'))
    save(QA/'fixed5_result.json',dict(verdict='NMT SCHEDULER REJECTED',reason='Captured exact-output prerequisite failed at batch2/4/8',
        baseline=dict(run_id=baseline['run_id'],wall_seconds=baseline['wall_seconds'],translated=3,failed_source_preserved=2,fatal=0),
        final=dict(status='NOT_RUN',reason='Only permitted after accepted exact replay; no repeat baseline or no-op final'),
        production_restored_exact=restored,overall_speedup=None,wall_reduction_percent=None,unique_pdf=5,measured_baseline_runs=1,measured_final_runs=0,
        broader_pdf_runs=0,prototype_tests_passed=51))
    checks=dict(native_batch1_exact=replay['results']['1']['exact_outputs'],native_batch2_exact=replay['results']['2']['exact_outputs'],
                native_batch4_exact=replay['results']['4']['exact_outputs'],native_batch8_exact=replay['results']['8']['exact_outputs'])
    save(QA/'output_equivalence.json',dict(status='FAIL',gate='Native per-request exact outputs BEFORE final PDF benchmark',checks=checks,
        mismatches={n:dict(hypotheses=len(r['mismatches']),decoded_text=r['decoded_text_mismatches']) for n,r in replay['results'].items()},
        counterexamples=next(r for r in replay['results']['2']['mismatches'] if r['before_decoded']!=r['after_decoded']),
        full_pdf_equivalence='NOT_EVALUATED: no accepted final run; do not claim statuses/OCR/glossary/candidates/writer/render equivalence for rejected prototype',
        source_and_dictionary_immutable=receipt['source_unchanged'] and receipt['sample_unchanged'] and receipt['dictionary_unchanged'],
        production_exact_baseline=restored,rollback_proof='rollback.json'))
    print('ANALYSIS',json.dumps(dict(metrics=modelmetrics,native_mismatches={n:len(r['mismatches']) for n,r in replay['results'].items()}),ensure_ascii=False),flush=True)


def report():
    baseline=read(QA/'baseline.json');b=baseline['measurement_summary'];replay=read(QA/'batch_replay.json');tested=read(QA/'full_pytest.json')
    assert tested['status']=='PASS' and tested['production_exact_measured_baseline'] and frozen_hashes()==baseline['production_before']
    names=[('Wall, s','wall_seconds'),('Attempted docs/hour (all five)','docs_per_hour'),('Semantic Runtime requests','semantic_model_requests'),('Physical CT2 calls','physical_CT2_calls'),
           ('batch1','batch1'),('batch2','batch2'),('batch3–4','batch3_4'),('batch5–8','batch5_8'),('Average sequences/call','average_sequences'),
           ('Median sequences/call','median_sequences'),('Max sequences/call','max_sequences'),('Source tokens','source_tokens'),('Average tokens/call','average_tokens'),
           ('Median tokens/call','median_tokens'),('p90 tokens/call','p90_tokens'),('CT2 inference, s','actual_CT2_seconds'),('model_translation inclusive, s','model_translation_seconds'),
           ('M2M requests','m2m_requests'),('Argos requests','argos_requests'),('Fallback attempts','fallback_attempts'),('Failure attempts','failure_attempts'),
           ('Real CT2 model loads','actual_CT2_model_loads'),('M2M resident reuse','m2m_resident_reuse')]
    table='\n'.join('| '+label+' | '+(f'{b[key]:.2f}' if isinstance(b[key],float) else str(b[key]))+' | N/A | N/A |' for label,key in names)
    table+='\n'+'\n'.join(f'| {label} | {value:.2f} | N/A | N/A |' for label,value in [
        ('GPU average, device-wide %',b['resources']['gpu_average_percent']),
        ('VRAM peak, MiB',b['resources']['peak_vram_mib']),
        ('CPU average, process-tree %',b['resources']['cpu_average_percent']),
        ('RSS peak, GiB',b['resources']['peak_rss_bytes']/1024**3),
        ('OCR inference, s',b['ocr']['inference_seconds']),
        ('OCR recognize inclusive, s',b['ocr']['recognize']['seconds']),
        ('Glossary lookup, s',b['glossary']['seconds']),
        ('Writer pdf_write inclusive, s',b['writer']['seconds'])])
    native='\n'.join(f"| {size} | {r['calls']} | {r['seconds']:.3f} | {len(r['mismatches'])} | {r['decoded_text_mismatches']} | {'PASS' if r['exact_outputs'] else 'FAIL'} |"
                     for size,r in replay['results'].items())
    r=b['resources'];first=read(QA/'output_equivalence.json')['counterexamples']
    text=f'''# AW0.81 NMT SEMANTIC BATCH SCHEDULER — FIXED5

## 1. Fixed5 sample

**NMT SCHEDULER REJECTED на обязательном native replay gate. Production восстановлен точно.** Из сохранённой telemetry `736fc7a72805` выбраны уникальные максимумы CT2 calls/time/short batch1/backend transitions и mixed-OCR NMT. Категории: 56,82,76,64,49; canonical order: **49,56,64,76,82**. Ровно пять PDF, 27 source pages. Manifest заморожен; исходный большой ZIP и 49 Knowledge DB неизменны. Один baseline `2bf4fd0f345e`, без warmup/ресурсных caps: **{b['wall_seconds']:.2f}s; 3 TRANSLATED, 2 FAILED_SOURCE_PRESERVED, 0 fatal**. Старый `/100` console label у наследованного helper был только меткой: scanner проверил ровно 5; повтор baseline не делался.

## 2. Why batch1 happens

Trace: segment → direct Knowledge/TM lookup → protected representation/Glossary → Router fixes backend/languages/options → synchronous Runtime/CT2 → placeholder restoration/guards → retries/fallback → next segment. Следующий model request ещё не существует во время текущего inference. {b['physical_CT2_calls']} CT2 calls, все batch1; median {b['median_tokens']:.0f} tokens. Resident reuse работает; это не задача нового model cache.

## 3. Scheduler design

Разработан и проверен прототип bounded intra-document continuations. Один активный semantic owner, один GPU execution owner; suspended stacks хранят исходные protected планы, broker получает immutable envelope. Пул максимум 8; no cross-document semantic concurrency, no artificial fill wait. Архив `rejected_prototype.zip` содержит код и 20 scheduler tests. После отказа все четыре изменённые production files восстановлены по SHA baseline; добавленный runtime module удалён из production. Никакие остальные оптимизации не внесены.

## 4. Safe batch frontier

Первый routed model attempt приостанавливался ДО mutable circuit check. Совпадали backend/model/device/languages/все frozen options; short source ≤32 pieces, batch ≤8/256 tokens/1MiB prepared estimate. Guards, retries, fallback и known-only result guards проходили canonical commit barrier. Capability planner снижал ceiling 8→4→2→1. Эти структурные гарантии оказались недостаточными: native outputs меняются при batch shape. Точная причина на уровне CUDA kernels не установлена; совпадение настроек не доказывает exactness.

## 5. Before → after NMT metrics

| Metric | Before | After | Gain |
|---|---:|---:|---:|
{table}

After отсутствует: unsafe patch не допущен к PDF benchmark. Native replay использовал **994 captured short CUDA M2M requests** с исходными token arrays, `int8_float16`, threads8, beam4 и неизменными decoding/token options. Один excluded native warmup; не PDF warmup. Replay не является whole-pipeline ускорением.

| Replay batch | CT2 calls | Inference s | Hypothesis differences | Decoded text differences | Exact |
|---|---:|---:|---:|---:|---|
{native}

Старый PASS на 64 requests не распространяется на эту более широкую выборку. Batch16 не запускался. Статистика physical-call reduction и replay time reduction сохранена в `batch_replay.json`; production batched-request fraction и semantic_requests/CT2_call after — N/A.

## 6. Before → after wall

Baseline **{b['wall_seconds']:.2f}s ({b['wall_seconds']/60:.2f}min)**. Final **NOT RUN**: пользователь разрешил его только после принятой реализации и exact replay PASS. Gate FAIL означает, что запуск с этим scheduler нарушил бы frozen contract. No-op final на восстановленном baseline не создавался. Overall ≥8%/≥15% gain не измерен, не заявляется. Всего 1 baseline, 0 final, 0 новых 20/100/full-corpus benchmark runs.

## 7. Equivalence

**FAIL до финального PDF benchmark.** Batch1 совпал со всеми 994 captured native outputs. Batch2/4/8 дали {len(replay['results']['2']['mismatches'])}/{len(replay['results']['4']['mismatches'])}/{len(replay['results']['8']['mismatches'])} hypothesis differences. Пример batch2: `{first['before_decoded']}` → `{first['after_decoded']}`. Есть лексические изменения и перемещения protected placeholder, а не только пунктуация. Full PDF statuses/OCR/glossary/candidates/writer/render/path/CRC equivalence прототипа **не оценивалась**, PASS ей не присваивается. Baseline captures сохранены для всех этих будущих сравнений. Production exact baseline SHA восстановлен; source/sample/Knowledge SHA сохранены.

## 8. Failures/fallback invariance

Прототип: **51 targeted PASS**, 20 новых scheduler cases +31 существующих runtime/pipeline tests, 33.20s. Проверены failing neighbor, original singleton replay, confirmed device breaker, serial guard retry, Unicode/IDs/numbers/placeholders, mixed lengths, empty/noise, near token limit, cancellation before/native/preparation wait, deterministic order, depth1/2 contexts, CPU/low VRAM/pressure и known-only guard barrier. Это protocol tests с контролируемыми backend outputs, не доказательство native exactness. Реальные before→after failure/fallback counts не заявляются без final. Production breakpoint/fallback code вернулся к baseline. Добавлен fail-closed benchmark gate и шесть его regression tests.

## 9. Resource use

Baseline CPU average **{r['cpu_average_percent']:.1f}%** process tree (100%=1 logical core), GPU average **{r['gpu_average_percent']:.1f}%** device-wide; RSS peak **{r['peak_rss_bytes']/1024**3:.2f}GiB**, VRAM peak **{r['peak_vram_mib']:.0f}MiB**. One-second observations; after N/A. OCR inference {b['ocr']['inference_seconds']:.2f}s; parent recognize inclusive {b['ocr']['recognize']['seconds']:.2f}s; glossary lookup {b['glossary']['seconds']:.2f}s; writer pdf_write inclusive {b['writer']['seconds']:.2f}s. Nested stages не суммируются как exclusive wall.

## 10. Full pytest

На восстановленном production: **{tested['passed']} passed, {tested['failures']} failures, {tested['errors']} errors, {tested['skipped']} skipped**, {tested['duration_seconds']:.2f}s. Production SHA до/после совпадают и точно равны baseline; Knowledge/models/settings тоже frozen. Новый quality/performance code не активирован. Prototype tests сохранены в архиве; шесть новых replay-gate tests включены в full suite.

## 11. Remaining bottleneck

Baseline synchronous native CT2 {b['actual_CT2_seconds']:.2f}s = {100*b['actual_CT2_seconds']/b['wall_seconds']:.2f}% wall. Полное массовое batching на текущих model/options не удовлетворяет exact-output контракту. OCR, glossary, writer только измерены, без изменения. Нельзя переносить replay acceleration на общий ZIP или прогноз 17211 PDF. Модель, quantization или decoding для восстановления batch exactness не менялись; новые работы не начаты.

## 12. Verdict

**NMT SCHEDULER REJECTED.** Это законченный эксперимент с отрицательным результатом обязательной приёмки; безопасный production сохранился. Performance optimization не принята, whole-pipeline speedup отсутствует. QA содержит все восемь требуемых central artifacts и архив прототипа. Final не выполнен по указанной выше prerequisite, не объявляется выполненным. STOP. No AW0.82, new resource modes, quality edits, document-failure fixes or commits.
'''
    path=ROOT/'docs/AW0.81_NMT_BATCH_SCHEDULER_5PDF.md';path.write_text(text,'utf8')
    print(str(path),flush=True)


if __name__=='__main__':
    {'pytest':full_pytest,'analyze':analyze,'report':report}[sys.argv[1]]()
