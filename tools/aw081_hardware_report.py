"""Final hardware report from completed/equivalence-checked QA evidence."""
import json
import math
from pathlib import Path
from statistics import mean
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw081_hardware_scaling_20 import QA,ORDER
from tools.aw081_speed_calibration_100 import save


def generate():
    rows=[json.loads(line) for line in (QA/'runs.jsonl').read_text('utf8').splitlines()]
    main=[r for r in rows if r['label'] in ORDER]
    eligible=[r for r in main if r['eligible']]
    assert len(main)==9
    manifest=json.loads((QA/'sample_manifest.json').read_text('utf8'))
    experiment=json.loads((QA/'experiment_manifest.json').read_text('utf8'))
    hardware=json.loads((QA/'hardware_summary.json').read_text('utf8'))
    factor=json.loads((QA/'factorial_analysis.json').read_text('utf8'))
    raw=factor.get('raw_exploratory_contrasts')
    if raw:
        # Independent saturated log-linear least squares verifies normalization
        # and signs of the balanced contrast arithmetic, not output quality.
        import numpy as np
        cube=[r for r in main if r['config']!='mid'];matrix=[];target=[]
        for r in cube:
            a,b,c=[1 if r['configuration'][k]=='HIGH' else -1 for k in ['cpu','gpu','ram']]
            matrix.append([1,a,b,c,a*b,a*c,b*c,a*b*c]);target.append(math.log(r['docs_hour']))
        beta=np.linalg.solve(np.asarray(matrix,dtype=float),np.asarray(target))
        errors=[]
        for i,name in enumerate(['cpu','gpu','ram'],1):errors.append(abs(100*(math.exp(2*beta[i])-1)-raw['main_effects'][name]['throughput_gain_percent']))
        for i,name in enumerate(['cpuxgpu','cpuxram','gpuxram','cpuxgpuxram'],4):errors.append(abs(100*(math.exp((8 if i==7 else 4)*beta[i])-1)-raw['interactions'][name]['ratio_of_ratios_percent']))
        assert max(errors)<1e-8
        save(QA/'analysis_math_check.json',dict(status='PASS',method='independent 8-parameter log-throughput linear solve',
            maximum_difference_percentage_points=max(errors),output_equivalence_approval=False))
    mid=next(r for r in main if r['label']=='mid')
    best=max(eligible,key=lambda r:r['docs_hour']) if eligible else None
    eco=min(eligible,key=lambda r:(r['configuration']['threads'],r['configuration']['gpu']!='LOW',r['configuration']['ram_gib'])) if eligible else None
    gain=(best['docs_hour']/eco['docs_hour']-1)*100 if best and eco and len(eligible)>=2 else None
    ordered=sorted(eligible,key=lambda r:-r['docs_hour'])
    close=[r for r in ordered if r['docs_hour']>=.97*best['docs_hour']] if best else []
    efficient=min(close,key=lambda r:(r['configuration']['threads'],r['configuration']['ram_gib'],r['configuration']['vram_gib'])) if close else None
    verdict='RESOURCE MODES NOT JUSTIFIED' if gain is None or gain<7 else 'FEWER MODES JUSTIFIED'
    # Four resource modes require four demonstrated useful steps, not arbitrary
    # preset labels. This experiment's common pipeline depth remains one.
    recommendations={'ECO':eco,'BALANCED':mid if mid['eligible'] else efficient,'HIGH':efficient,'ULTRA':best}
    modes={}
    baseline_hours=229.50983164705343
    for name,r in recommendations.items():
        if r is None:modes[name]=dict(status='UNAVAILABLE');continue
        coefficient=r['docs_hour']/mid['docs_hour']
        modes[name]=dict(status='CANDIDATE_ONLY',measured_config=r['config'],configuration=r['configuration'],
            fixed20_docs_hour=r['docs_hour'],scaling_vs_current_mid=coefficient,
            estimated_full_hours=baseline_hours/coefficient,estimated_full_days=baseline_hours/coefficient/24,
            estimated_full_hours_range=[188.22832390519144/coefficient,303.9334322015724/coefficient],
            responsiveness='resource-utilization proxy only; interactive UI/game responsiveness not benchmarked',
            consumption=dict(cpu_average=r['cpu']['average_machine_percent'],rss_peak_bytes=r['ram']['peak_rss_bytes'],device_vram_peak_mib=r['gpu']['peak_device_vram_mib']))
    decisions=dict(verdict=verdict,eco_to_best_throughput_gain_percent=gain,modes=modes,
        approved_distinct_main_configurations=[r['label'] for r in eligible],
        supported_distinct_mode_count=len({r['config'] for r in recommendations.values() if r}),
        ultra_increment_vs_efficient_percent=(best['docs_hour']/efficient['docs_hour']-1)*100 if best and efficient and len(eligible)>=2 else None,
        adaptive_policy='Detect hardware; keep decoding/OCR quality constant. CPU below detected logical threads minus OS reserve, bounded by measured knee; memory ceilings above measured working demand without reservation. Global CT2 VRAM cap unsupported; do not claim a hard aggregate CUDA cap.',
        mode_names_not_existing_quality_profiles=True,implementation=False,
        uncertainty='Unreplicated factorial contrasts can contain drift/noise. 20 PDFs model relative controls, not corpus representation or a new hardware purchase.')
    decisions['new_validated_resource_mode_count']=max(0,decisions['supported_distinct_mode_count']-1)
    decisions['verdict_scope']='No demonstrated distinct quality-preserving resource levels warrant implementation from this evidence. A lone self-equivalent reference does not prove zero CPU/GPU/RAM elasticity; rejected variants and uncertain drift limit the inference.'
    control_repeats=[r for r in rows if r['config']=='mid' and r['label'] in ['best_repeat_original','mid_sustained']]
    decisions['mid_original_and_sustained_reproducibility']=dict(
        status='PASS' if len(control_repeats)==2 and all(r['eligible'] for r in control_repeats) else 'NOT_ESTABLISHED',
        trials=[dict(label=r['label'],equivalence=r['equivalence']['status'],eligible=r['eligible']) for r in control_repeats],
        limitation='MID self-comparison alone is a reference, not a reproducibility test. Rejected repetitions do not establish a resource-caused defect or a new speed winner.')
    save(QA/'mode_recommendations.json',decisions)
    n=lambda x:'UNAVAILABLE' if x is None else f'{x:.2f}'
    lines=['# AW0.81 — hardware scaling / resource profile, fixed 20 PDF','',f"**{verdict}**. Это исследование runtime limits на текущей машине; профили не внедрены.",'',
        f"Измерения завершены: {len(main)} основных прогонов, 2 сравнения порядка, 2 длительных повтора — {len(rows)} measured runs на одних и тех же 20 PDF. Каждый завершил 16 TRANSLATED / 4 FAILED_SOURCE_PRESERVED без fatal. Дополнительно выполнены 6 prepared-data GPU microtrials. Это завершение hardware benchmark; качество AW0.81 до релизного уровня здесь не переоценивалось.",'',
        'Вывод относится к обоснованности внедрения режимов по полученным данным. Единственная конфигурация, совпадающая сама с собой, не доказывает нулевое влияние ресурсов. Неэквивалентный вывод и возможный дрейф ограничивают причинные выводы о масштабировании.','',
        'Важные результаты: увеличение CPU с 6 до 14 потоков дало в трёх эквивалентных внутри пары сравнениях +5,61%, −0,58% и −1,73%; устойчивого большого выигрыша не видно. Для LOW GPU увеличение RAM/cache budget с 8 до 24 GiB дало +7,18% и +0,90% в двух эквивалентных парах. Это единичные замеры разных bundles; они не устанавливают универсальную точку насыщения физических CPU/RAM.','',
        'В HIGH GPU / LOW RAM прогонах зафиксирован OCR fallback на CPU около job commit cap8 GiB при значительном объёме свободной системной RAM. Тип исходной vendor-ошибки скрыт OCR worker, поэтому точный счётчик OCR OOM недоступен. Ограничение commit приложения и нехватка физической памяти ПК — разные причины. Самые большие сырые выигрыши RAM при HIGH GPU сопровождаются изменённым OCR/translation workload и не принимаются как ускорение с сохранением результата.','',
        f"Доступный VRAM budget не превращается автоматически в используемую память: фактический пик device VRAM в матрице около 3,4–4,2 GiB, а максимальный NMT batch — {max(r['gpu']['max_actual_nmt_batch_tokens'] or 0 for r in main)} source tokens. LOW cap равен384. OCR worker хранит один model key и перезагружает варианты распознавания при переключении. В этой задаче этот код не оптимизировался.",'',
        '## Hardware и scope','',f"Reference: Ryzen 7 5700X / {hardware['physical_cores']} cores / {hardware['logical_processors']} logical threads; RAM {hardware['ram_total_bytes']/1024**3:.2f} GiB; GPU {hardware['gpu']['name']}, {hardware['gpu']['total_mib']/1024:.2f} GiB VRAM, CUDA. Полный исходный snapshot — hardware_summary.json.",'',
        'Все trials используют AUTOMATIC quality policy: прежние NMT/OCR модели, beam, token/decoding limits, DPI, thresholds, orientation/structure, Knowledge/TM/glossary content, Router, guards, writer и recovery. Меняются только QA resource settings. Это фиксирует параметры качества, но не гарантирует идентичный результат: изменения OCR source/translation отдельно проверены ниже. Старые PerformanceProfile economy/fast/turbo меняют качество, поэтому ими нельзя подменять рекомендуемые resource modes.','',
        'CPU — реальные intra_threads/ocr_threads и OMP/MKL/OpenBLAS caps, inter_threads=1; это не Windows process CPU hard quota. RAM — Windows job-wide COMMIT cap, не искусственное выделение RAM и не строгий RSS cap. Job commit peak — lifetime high-water mark, включая исключённый warmup; RSS/private commit sampled только в measured window. Сумма RSS процессов может учитывать shared pages несколько раз. GPU — Paddle worker allocator cap, auto_growth без резервирования; CT2 общего CUDA allocator quota API не предоставляет, aggregate per-process VRAM cap UNAVAILABLE. Budget 10.5 GiB в coexistence arms оставляет 1 GiB номинального headroom для CT2.','',
        'Основная GPU utilization/VRAM/температура/clocks/power — device-wide nvidia-smi, включая другие приложения. nvidia-smi per-process WDDM memory unavailable. Дополнительные штатные Windows CIM counters дают per-PID dedicated/shared GPU accounting, busiest compute/3D engine utilization и system hard-fault disk reads. Sidecar добавлен во время run7: первые четыре завершённых trials этих данных не имеют, поэтому основное сравнение использует единый исходный one-second monitor. CPU actual clock/temperature, process-owned SM utilization и queue starvation — UNAVAILABLE. Child CPU time оценён по one-second process-tree samples: небольшое время между последним sample и exit worker может не попасть в сумму.','',
        '[Windows memory-limit semantics](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information) · [Paddle allocator strategy](https://www.paddlepaddle.org.cn/documentation/guides/flags/memory_cn.html).','',
        '## Методика и fixed sample','',
        f"20 PDF / 39 source pages, только из run 25825c3f75a7; 5 EASY_NATIVE / 5 MEDIUM / 5 OCR_MIXED / 5 HEAVY_OTHER. Полный метод и SHA в sample_manifest.json. Run order: `{experiment['run_order']}`. Одинаковый warmup по frozen sample перед каждым run, исключён из measured wall; конфигурации чередуются. Matrix HIGH GPU включает residency/persistence/batch как один bundle, RAM включает commit limit/cache entries: это не изолированный эффект физического объёма памяти.",'',
        '| # calibration | Bucket | Type | Pages | Member |','|---:|---|---|---:|---|']
    for x in manifest['documents']:lines.append(f"| {x['calibration_index']+1} | {x['bucket']} | {x['classification']} | {x['pages']} | {x['member_path']} |")
    lines+=['','## Factorial 8 + MID','', '| Run | CPU / OCR threads | GPU | RAM GiB | Wall s | docs/h | Δ MID % | T / F | EQ |','|---|---|---|---:|---:|---:|---:|---|---|']
    bylabel={r['label']:r for r in rows}
    for label in ORDER:
        r=bylabel[label];c=r['configuration']
        lines.append(f"| {label} | {c['threads']} / {c['ocr_threads']} | {c['gpu']} {c['vram_gib']}GiB | {c['ram_gib']} | {n(r['wall_seconds'])} | {n(r['docs_hour'])} | {n(100*(r['docs_hour']/mid['docs_hour']-1))} | {r['translated']} / {r['failed']} | {r['equivalence']['status']} |")
    lines+=['','## CPU, GPU and RAM resource curves','',
        'Each curve row retains its other-factor settings; LOW→HIGH gain is paired at equal other factors. MID changes several controls and is shown as a control, not an isolated midpoint.','',
        '| Run | NMT / OCR threads | Fixed GPU / RAM | Wall s | docs/h | CPU avg %machine | Paired CPU gain % |',
        '|---|---|---|---:|---:|---:|---:|']
    def paired_gain(label,factor_name):
        pair=next((p for p in factor['conditional_pairs'] if p['factor']==factor_name and p['high']==label),None)
        return pair.get('throughput_gain_percent') if pair else None
    for label in ORDER:
        r=bylabel[label];c=r['configuration']
        lines.append(f"| {label} | {c['threads']} / {c['ocr_threads']} | {c['gpu']} / {c['ram_gib']}GiB | {n(r['wall_seconds'])} | {n(r['docs_hour'])} | {n(r['cpu']['average_machine_percent'])} | {n(paired_gain(label,'cpu'))} |")
    lines+=['','| Run | GPU budget / observed device peak GiB | OCR batch / NMT token budget | Wall s | docs/h | GPU avg %device | Paired GPU gain % |',
        '|---|---|---|---:|---:|---:|---:|']
    for label in ORDER:
        r=bylabel[label];c=r['configuration'];g=r['gpu']
        lines.append(f"| {label} | {c['vram_gib']} / {n(g['peak_device_vram_mib']/1024 if g['peak_device_vram_mib'] is not None else None)} | {c['ocr_batch']} / {c['nmt_batch_tokens']} | {n(r['wall_seconds'])} | {n(r['docs_hour'])} | {n(g['average_device_utilization'])} | {n(paired_gain(label,'gpu'))} |")
    lines+=['','| Run | RAM commit cap GiB / observed RSS peak GiB | Cache cap / entries | Wall s | docs/h | Cache hits / misses | Paired RAM gain % |',
        '|---|---|---|---:|---:|---|---:|']
    for label in ORDER:
        r=bylabel[label];c=r['configuration'];m=r['ram']
        lines.append(f"| {label} | {c['ram_gib']} / {n(m['peak_rss_bytes']/1024**3 if m['peak_rss_bytes'] is not None else None)} | {c['glossary_cache_entries']} / {m['glossary_cache_entries']} | {n(r['wall_seconds'])} | {n(r['docs_hour'])} | {m['glossary_cache_hits']} / {m['glossary_cache_misses']} | {n(paired_gain(label,'ram'))} |")
    lines+=['','## Curves: conditional CPU/GPU/RAM comparisons','',
        '| Factor | LOW → HIGH runs | Throughput Δ % | Wall Δ s | CPU avg Δ points | RSS Δ GiB | Device VRAM Δ MiB | Class | Pair EQ / MID eligible |','|---|---|---:|---:|---:|---:|---:|---|---|']
    for p in factor['conditional_pairs']:
        if 'throughput_gain_percent' not in p:continue
        lines.append(f"| {p['factor']} | {p['low']} → {p['high']} | {n(p['throughput_gain_percent'])} | {n(p['wall_delta_seconds'])} | {n(p['cpu_average_delta'])} | {n(p['rss_peak_delta_bytes']/1024**3)} | {n(p['vram_device_peak_delta_mib'])} | {p['classification']} | {p.get('pairwise_equivalence','UNAVAILABLE')} / {p['eligible']} |")
    lines+=['',f"Pairwise invariant conditional main effects: `{factor.get('quality_preserving_conditional_main_effects',{})}`. Pair EQ only establishes invariance between that pair at fixed other-factor settings; a variant may still differ from current MID and remain ineligible for recommendation."]
    raw=factor.get('raw_exploratory_contrasts')
    if raw and not raw['output_equivalence_valid']:
        lines+=['','**Raw contrasts: output equivalence FAIL.** Эти значения приведены для полноты матрицы, но смешивают resource changes и изменённую OCR/translation workload. Они не доказывают ускорение с сохранением вывода.',
            '| Main factor | Raw throughput Δ % | Class |','|---|---:|---|']
        for name,value in raw['main_effects'].items():lines.append(f"| {name} | {n(value['throughput_gain_percent'])} | {value['classification']} |")
        lines+=['','| Interaction | Raw ratio-of-ratios Δ % |','|---|---:|']
        for name,value in raw['interactions'].items():lines.append(f"| {name} | {n(value['ratio_of_ratios_percent'])} |")
    lines+=['',f"Factorial status: **{factor['status']}**. Main effects: `{factor['main_effects']}`. CPU×GPU / CPU×RAM / GPU×RAM / three-way: `{factor['interactions']}`. Main effects use geometric HIGH/LOW throughput; interactions are log-throughput ratio-of-ratios contrasts. Ineligible/non-equivalent runs cannot establish a speed winner.",'',
        'The <3 / 3–7 / 7–15 / >15% bands describe measured differences, not statistical proof of a universal hardware knee. CPU6/14 and memory low/high give only two endpoints. An inactive cap does not locate a physical resource knee. MID changes multiple budgets and is not an isolated CPU curve point.','',
        '## Utilization, latency and milestones','', '| Run | CPU avg/peak %machine | CPU seconds | RSS peak GiB | Job lifetime commit peak GiB | Available min GiB | Cache hit/miss | GPU avg/peak %device | VRAM peak MiB | GPU temp peak C |','|---|---|---:|---:|---:|---:|---|---|---:|---:|']
    for r in rows:
        c=r['cpu'];mem=r['ram'];g=r['gpu'];t=r['thermal']
        lines.append(f"| {r['label']} | {n(c['average_machine_percent'])}/{n(c['peak_machine_percent'])} | {n(c['process_cpu_time_seconds'])} | {n((mem['peak_rss_bytes'] or 0)/1024**3)} | {n((mem['peak_job_commit_bytes'] or 0)/1024**3)} | {n((mem['available_system_min_bytes'] or 0)/1024**3)} | {mem['glossary_cache_hits']}/{mem['glossary_cache_misses']} | {n(g['average_device_utilization'])}/{n(g['peak_device_utilization'])} | {n(g['peak_device_vram_mib'])} | {n(t['gpu_peak_temperature_c'])} |")
    lines+=['','| Run | CPU idle samples (~s) | Device GPU idle samples (~s) | GPU clock avg / min MHz | Device power peak W | OCR successful GPU / CPU calls |',
        '|---|---:|---:|---|---:|---|']
    for r in rows:
        t=r['thermal'];devices=r['ocr']['actual_devices']
        lines.append(f"| {r['label']} | {r['cpu']['idle_sample_seconds']} | {r['gpu']['device_idle_sample_seconds']} | {n(t['gpu_average_clock_mhz'])}/{n(t['gpu_min_clock_mhz'])} | {n(t['gpu_peak_power_w'])} | {devices.get('gpu',0)}/{devices.get('cpu',0)} |")
    lines+=['','Периоды idle оцениваются по числу секундных samples: CPU ниже 5%, GPU не выше 3%; это приближение, а не точное непрерывное время. GPU counters относятся ко всей видеокарте. Низкая частота GPU во время простоя не доказывает thermal throttling. Независимой очереди подготовленных документов нет: queue starvation недоступен. Фактические устройства NMT по backend и успешные OCR вызовы сохранены в runs.jsonl.']
    lines+=['','| Run | pages/h | segments/s | Median/P90/P95 s | First start / processed / translated s | 25/50/75/100% processed s |','|---|---:|---:|---|---|---|']
    for r in rows:lines.append(f"| {r['label']} | {n(r['source_pages_hour'])} | {n(r['segments_second'])} | {' / '.join(n(r['latency'][k]) for k in ['median','p90','p95'])} | {n(r['first_document_start_seconds'])}/{n(r['first_document_complete_seconds'])}/{n(r['first_translated_document_complete_seconds'])} | {' / '.join(n(r['milestones_seconds'][k]) for k in ['25','50','75','100'])} |")
    lines+=['','## Model loads, actual batching and failures','',
        '| Run | NMT model loads / s | OCR loads >10ms / load s / inference s | Actual max NMT sequences/tokens | NMT failed attempts / fallback | Recorded NMT OOM |','|---|---|---|---|---|---|']
    for r in rows:
        loads=r['model_loads'];o=r['ocr'];g=r['gpu']
        lines.append(f"| {r['label']} | {sum(loads['counts'].values())} / {n(sum(loads['seconds'].values()))} | {o['load_calls_over_10ms']} / {n(o['model_load_seconds'])} / {n(o['inference_seconds'])} | {g['max_actual_nmt_batch_sequences']}/{g['max_actual_nmt_batch_tokens']} | {g['backend_failures']} / {g['fallback_attempts']} | {r['recorded_nmt_oom_events']} |")
    lines+=['','NMT failed attempts include TranslationError/guards and must not all be interpreted as CUDA allocation failures. OCR vendor exception types are masked by the isolated worker; precise OCR OOM count is UNAVAILABLE. Successful OCR device counts, error-type counts and inclusive stage calls retained in runs.jsonl.','',
        'The OCR worker has one cached model key. Auto alternates recognition candidates; switching recognizer invalidates that cache. Thus persistent process residency does not retain both OCR variants, and substantial model loading can remain despite extra nominal VRAM. This behavior was measured and inspected, not optimized in this task.']
    lines+=['','## Supplementary Windows counters','',
        '| Run | Samples / capture span % | Owned dedicated GPU peak GiB | Busiest owned engine avg/peak % | System page reads avg/s | System pages input/output peak/s |',
        '|---|---|---:|---|---:|---|']
    for r in rows:
        w=r['supplementary_windows_counters']
        lines.append(f"| {r['label']} | {w['samples']} / {n(w['capture_span_percent'])} | {n(w['owned_dedicated_gpu_peak_bytes']/1024**3 if w['owned_dedicated_gpu_peak_bytes'] is not None else None)} | {n(w['busiest_owned_engine_average_percent'])}/{n(w['busiest_owned_engine_peak_percent'])} | {n(w['system_page_reads_average'])} | {n(w['system_pages_input_peak'])}/{n(w['system_pages_output_peak'])} |")
    lines+=['','~20s supplemental samples may miss short bursts and do not replace the consistent one-second primary traces. Capture span is the first-to-last query interval, not continuous coverage. Run7 and easy-first have partial late capture; do not compare their supplemental averages as full-run means. WDDM per-PID accounting is not a model-tensor-only allocator footprint. System hard-fault disk reads include executable/file-backed pages and do not prove pagefile pressure or attribute paging to TreeTranslate. No CPU sensor namespace found; no monitoring package installed.']
    lines+=['','Milestones count processed PDFs including FAILED_SOURCE_PRESERVED, not 20 successful translations. Segments/s counts all processed segments including protected/noise segments; it is not semantic-only inference throughput. Final archive publication occurs after member20; total wall includes final archive validation/publish. Warmup, fingerprint/render inspection and report generation are excluded.','',
        '## Equivalence / scheduler / sustained / overlap','']
    lines+=['Сравнение включает status, полный candidate text и protected IDs/numbers, source-preserved segments, writer result, страницы и нормализованные PDF objects, RGB hashes первого/последнего листа четырёх фиксированных представителей, exact bytes/path failed originals. Округление геометрии objects — 1e-5 points. Это проверка идентичности результата, а не новая оценка его предметного качества.','',
        '| Run | Reference | EQ | Documents with differences | Different evidence records |',
        '|---|---|---|---:|---:|']
    for r in rows:
        eq=r['equivalence'];differences=eq.get('differences',[])
        lines.append(f"| {r['label']} | {eq.get('reference','mid')} | {eq['status']} | {len({d['member'] for d in differences})} | {len(differences)} |")
    diagnostics=json.loads((QA/'equivalence_diagnostics.json').read_text('utf8'))
    lines+=['','| Rejected run | Candidate-different PDFs | Source-string-different PDFs | Profiler-different PDFs | Changed targets for identical source strings |',
        '|---|---:|---:|---:|---:|']
    for trial in diagnostics['runs']:
        docs=trial['documents']
        lines.append(f"| {trial['label']} | {len(docs)} | {sum(bool(d['reference_only_source_strings'] or d['run_only_source_strings']) for d in docs)} | {sum(d['profiler_changed'] for d in docs)} | {sum(d['same_source_changed_target_count'] for d in docs)} |")
    lines+=['','Изменения распознанного исходного текста могут изменить существующий document profile и выбор терминов даже при неизменных моделях, Knowledge и правилах. Конфигурации проверялись как bundles; причинность одного параметра для каждого различия не установлена. Примеры строк и изменённые profiles сохранены в [equivalence_diagnostics.json](C:/TreeTranslate/qa/aw081/hardware_scaling_20/equivalence_diagnostics.json). Предметные переводы в этой задаче не исправлялись.']
    scheduler_path=QA/'scheduler_analysis.json'
    if scheduler_path.exists():
        scheduler=json.loads(scheduler_path.read_text('utf8'))
        lines+=['',f"**Easy-first** на `{scheduler['configuration']}`: throughput Δ {n(scheduler['throughput_gain_percent'])}%, eligible {scheduler['eligible']}; cheap metadata sort {scheduler['cheap_metadata_sort_seconds']:.6f}s.",
            '',
            '| Order | 25 / 50 / 75 / 100% processed s | First / 5 / 10 / 15 / 20 translations ready s |',
            '|---|---|---|']
        for label,key in [(scheduler['original_run'],'original_milestones'),(scheduler['easy_run'],'easy_milestones')]:
            lines.append(f"| {label} | {' / '.join(n(scheduler[key][str(i)]) for i in [25,50,75,100])} | {' / '.join(n(scheduler['translated_ready_seconds'][label][str(i)]) for i in [1,5,10,15,20])} |")
        lines+=['',scheduler['limitations']]
        lines+=['','Easy-first ускоряет ранний прогресс, но практически не меняет общий wall. В этих trials первый переведённый PDF упакован через 76,69s в original order и 3,81s в easy-first. Это внутренняя готовность member; выходной ZIP публикуется целиком в конце.']
        lines+=['','Этот scheduler experiment переиспользует metadata, уже собранную для 100-PDF sample. Для полного ZIP наличие page/native/raster metadata до обработки не доказано; archive inventory сразу даёт размеры и пути. Новый глобальный OCR/profiler/native pre-scan для сортировки не предлагается: запуск первого документа должен оставаться быстрым.']
    else:lines+=['','**Easy-first**: UNAVAILABLE / required trial not completed.']
    init_failure=QA/'initialization_failures/best_easy_first_ast_selector_01/initialization_failure.json'
    if init_failure.exists():
        lines+=['','QA initialization incident: the initial easy-first AST selector matched both the processing loop and directory-finalization loop and stopped before scan/warmup/DocumentJob. The failed initialization record is preserved in initialization_failures. A separate scheduler adapter selects only the loop constructing DocumentJob; its AST-only preflight passed. Frozen matrix runtime/support scripts and production code were not edited. This is not a failed measured resource trial.']
    sustained_path=QA/'sustained_analysis.json'
    if sustained_path.exists():
        sustained=json.loads(sustained_path.read_text('utf8'))
        from tools.aw081_hardware_analysis import equivalence
        for trial in sustained['trials']:
            trial['within_configuration_repeat_equivalence']=equivalence(trial['warm_run'],trial['cold_run'])
            trial['system_paging_supplementary']=bylabel[trial['warm_run']]['supplementary_windows_counters']
            trial['hard_paging_activity']='UNAVAILABLE_PER_PROCESS_PAGEFILE_ATTRIBUTION; supplemental system hard-fault counters retained separately'
        sustained['limitations']='One warm repetition per configuration; no statistical confidence interval. CPU thermal and per-process pagefile attribution unavailable. Supplemental system hard-fault counters are available for captured windows. Device telemetry includes ambient GPU workloads; full20 warmup also retains caches for duplicated inputs.'
        save(sustained_path,sustained)
        plan_path=QA/'post_matrix_manifest.json'
        if plan_path.exists():
            plan=json.loads(plan_path.read_text('utf8'))
            if not all(plan.get('top2_output_eligible',[True])):lines+=['','Only one main configuration passed MID equivalence. The second sustained trial diagnoses the fastest rejected configuration; it is not a speed winner or mode recommendation.']
        lines+=['','**Sustained / thermal / drift**','',
            '| Config | Cold / warm wall s | Warm throughput Δ % | Peak GPU temp cold / warm C | Warm active clock median MHz | Warm RSS peak GiB | EQ vs own cold / vs MID / eligible |',
            '|---|---|---:|---|---:|---:|---|']
        for trial in sustained['trials']:lines.append(f"| {trial['configuration']} | {n(trial['cold_wall_seconds'])} / {n(trial['warm_wall_seconds'])} | {n(trial['warm_throughput_gain_percent'])} | {n(trial['cold_thermal']['gpu_peak_temperature_c'])} / {n(trial['warm_thermal']['gpu_peak_temperature_c'])} | {n(trial['warm_median_active_gpu_clock_mhz'])} | {n(trial['warm_peak_rss_bytes']/1024**3)} | {trial['within_configuration_repeat_equivalence']['status']} / {trial['exact_equivalence']} / {trial['eligible']} |")
        lines+=['',f"Original-order repeat drift versus its main trial: {n(sustained['best_original_repeat_drift_percent'])}%. {sustained['method']} {sustained['limitations']}"]
        lines+=['','The full20 warmup also retains lookup caches for the same repeated inputs. Warm/cold speed differences can include cache reuse and filesystem/model warmup, not only thermal or worker effects. They are not used as a full-corpus hardware scaling coefficient. Compare measured cache hits/misses and model-load counts in the utilization tables before attributing a change to heat.']
    else:lines+=['','**Sustained**: UNAVAILABLE / required trials not completed.']
    probe_path=QA/'residency_overlap_probe.json'
    if probe_path.exists():
        probe=json.loads(probe_path.read_text('utf8'))
        lines+=['',f"**Prepared-data GPU overlap**: {probe['status']}; exact equivalence {probe['exact_equivalence']}; median parallel throughput Δ {n(probe['median_parallel_gain_percent'])}%; safe useful concurrent requests {probe['safe_useful_overlap']}. Estimated overlapping native inference calls: {n(probe.get('approximate_native_inference_overlap_seconds'))}s.",
            '',
            '| Trial | Parallel | Wall s | Exact OCR / NMT |','|---|---|---:|---|']
        for i,trial in enumerate(probe['trials'],1):lines.append(f"| {i} | {trial['parallel']} | {n(trial['seconds'])} | {trial['exact_ocr_equivalence']} / {trial['exact_nmt_equivalence']} |")
        lines+=['','| Residency snapshot | Device VRAM MiB | Owned WDDM dedicated GiB | Owned WDDM shared GiB |',
            '|---|---:|---:|---:|']
        for snapshot in probe['snapshots']:
            if snapshot['label'] not in ['idle_before','m2m100_isolated','m2m100_released','argos_isolated','argos_released','ocr_isolated','combined_resident']:continue
            device=snapshot['device_wide'];owned=snapshot.get('windows_owned_gpu',{})
            lines.append(f"| {snapshot['label']} | {n(device['used_mib'] if device else None)} | {n(owned['process_tree_dedicated_gpu_bytes']/1024**3 if 'process_tree_dedicated_gpu_bytes' in owned else None)} | {n(owned['process_tree_shared_gpu_bytes']/1024**3 if 'process_tree_shared_gpu_bytes' in owned else None)} |")
        lines+=['',f"Observed device peak {n(probe.get('peak_observed_device_vram_mib'))}MiB; within HIGH budget: {probe.get('observed_within_high_gpu_budget','UNAVAILABLE')}. This is observed fit on the prepared sample, not a worst-case guarantee or aggregate CUDA cap."]
        lines+=['','На подготовленном workload совместная residency поместилась в budget, но полезного большого выигрыша не показала. Параллельные requests дали слабый эффект; пересечение оценённых native inference intervals не обнаружено. Это не доказывает невозможность другого overlap и не даёт коэффициент ускорения полного pipeline.','',
            'Isolated and combined device VRAM snapshots and Paddle allocator measurements: [residency_overlap_probe.json](C:/TreeTranslate/qa/aw081/hardware_scaling_20/residency_overlap_probe.json).',probe['limitations']]
        if probe['error']:lines+=['',f"Probe limitation: `{probe['error']}`"]
    else:lines+=['','**Overlap**: UNAVAILABLE / required probe not completed.']
    saturation_path=QA/'saturation_decision.json'
    if saturation_path.exists():
        saturation=json.loads(saturation_path.read_text('utf8'))
        lines+=['',f"**Optional saturation sweep**: {saturation['status']}; {len(saturation['additional_runs'])} additional runs, maximum4. {saturation['limitation']}",
            '',
            '| Factor | Strong valid effect | Binding among equivalent HIGH arms |','|---|---|---|']
        for check in saturation['checks']:lines.append(f"| {check['factor']} | {check['strong']} | {check['high_budget_observed_binding']} |")
        lines+=['','Sweep decisions require output-equivalent HIGH-arm evidence. An empty eligible HIGH set does not prove that the hardware itself is saturated.']
    else:lines+=['','**Saturation**: UNAVAILABLE / decision not completed.']
    lines+=['','Текущий production pipeline последовательный, GPU queue depth=1. PDF_LOCK охватывает extraction/recognition и writer operations; RuntimeManager сериализует NMT-вызовы своим lock. Совместное присутствие моделей в памяти не означает одновременный inference. GPU microprobe использует только уже подготовленные image/text, без параллельного writer и изменения extraction architecture.','',
        '| Stage | Observed scheduling / overlap limit |',
        '|---|---|',
        '| ZIP inventory / path reservation | Выполняется до цикла документов; независимой ready-document queue нет. |',
        '| CPU extraction / OCR preparation | PDF_LOCK сохраняется во время соответствующей операции; overlapping extraction следующего PDF не измерялся. |',
        '| GPU OCR + GPU NMT | В обычном document pipeline перекрытия не наблюдалось; prepared-data probe отдельно проверяет coexistence и concurrent requests. |',
        '| Knowledge / glossary / NMT | Выполняются внутри текущего document/segment flow; отдельная очередь подготовки не реализована и не проверялась. |',
        '| CPU PDF writer | Защищён PDF_LOCK; параллельные небезопасные writer operations не запускались. |',
        '| Archive append / validation / publish | Один владелец выходного ZIP, последовательное добавление; отдельные ранние PDF пользователю не публикуются. |','',
        'Основание: [PdfDocument / PDF_LOCK](C:/TreeTranslate/app/documents/pdf_document.py:141), [ArchiveJob processing loop](C:/TreeTranslate/app/documents/archive_job.py:203), [RuntimeManager lock](C:/TreeTranslate/app/engine/runtime/runtime_manager.py:71). Эти ограничения описывают текущую архитектуру; новый scheduler или pipeline в этой задаче не создавался.','',
        '## Resource-only candidates and full ZIP estimate','',
        '| Mode | Measured config | CPU/OCR threads | RAM cap GiB | GPU budget GiB | Pipeline depth | Sample docs/h | Full hours | Days | PC responsiveness |','|---|---|---|---:|---:|---:|---:|---:|---:|---|']
    for name,mode in modes.items():
        if mode['status']=='UNAVAILABLE':lines.append(f'| {name} | UNAVAILABLE | | | | | | | | UNAVAILABLE |');continue
        c=mode['configuration'];lines.append(f"| {name} | {mode['measured_config']} | {c['threads']}/{c['ocr_threads']} | {c['ram_gib']} | {c['vram_gib']} | 1 | {n(mode['fixed20_docs_hour'])} | {n(mode['estimated_full_hours'])} | {n(mode['estimated_full_days'])} | Не измерялась; загрузка ресурсов — только косвенный показатель |")
    lines+=['',f"Конфигурации, совпавшие с текущим MID: `{decisions['approved_distinct_main_configurations']}`. Четыре строки выше сводятся к одному контрольному набору настроек; они не представляют четыре доказанных режима. Рекомендация — сохранить текущие настройки, без новых ECO/HIGH/ULTRA. Другие варианты не прошли сравнение вывода с MID."]
    lines+=['',f"MID repeat reproducibility: **{decisions['mid_original_and_sustained_reproducibility']['status']}**. Self-equivalence of the reference does not alone validate repeat stability. A NOT_ESTABLISHED result strengthens the reason to retain current settings without promoting a faster variant."]
    lines+=['',f"Прогноз по прежней 100-PDF corpus model: {baseline_hours:.2f} часа / {baseline_hours/24:.2f} суток; оптимистичный–консервативный сценарий188,23–303,93h (не доверительный интервал). Hardware coefficient = throughput эквивалентной fixed20 конфигурации / throughput MID fixed20; прогноз = corpus hours / coefficient. Нового эквивалентного ускорителя не найдено, поэтому коэффициент1 и прогноз сохранён. 20 PDF намеренно содержат много тяжёлой работы и не используются как самостоятельная модель всего корпуса. Прогноз считает обработку с FAILED_SOURCE_PRESERVED и не гарантирует успешный перевод всех17211 PDF.",'',
        f"Дополнительный выигрыш Ultra относительно более экономного варианта в пределах3% максимума: {n(decisions['ultra_increment_vs_efficient_percent'])}. Сравнение разных одобренных уровней недоступно: есть только MID. Лишняя RAM/VRAM искусственно не выделялась. Отзывчивость UI не измерялась.",'',
        'For future machines detect CPU count, available RAM and CUDA/VRAM first, retain OS headroom and choose only measured useful resource ceilings. Do not copy Ryzen5700X/RTX3080 constants into production. Preserve original semantic/quality settings and OOM/fallback/recovery behavior. Four distinct useful performance levels are not established merely by naming four presets.','',
        '## Evidence and STOP','',
        '[Sample manifest](C:/TreeTranslate/qa/aw081/hardware_scaling_20/sample_manifest.json) · [Runs](C:/TreeTranslate/qa/aw081/hardware_scaling_20/runs.jsonl) · [Factorial](C:/TreeTranslate/qa/aw081/hardware_scaling_20/factorial_analysis.json) · [Recommendations](C:/TreeTranslate/qa/aw081/hardware_scaling_20/mode_recommendations.json).','',
        'experiment_manifest.json, hardware_summary.json, resource_samples.jsonl and per-run execution/log/candidate/writer/fingerprint files retained. No heavy monitoring frameworks installed.','',
        '[Финальный аудит](C:/TreeTranslate/qa/aw081/hardware_scaling_20/final_evidence_audit.json): CRC, ровно20 файлов PDF в каждом output (отдельно45 directory entries), одинаковые directory paths, точное сохранение failed originals, пустая QA TM, неизменность248 production-файлов и двух frozen QA core scripts. Operational audit не принимает качество отклонённых конфигураций.','',
        '**STOP.** Полный17211-PDF прогон не запускался. Production defaults, модели, Knowledge и quality policy не менялись; режимы, UI и scheduler не внедрялись. OCR/glossary не оптимизировались. PHASE B/C, Frozen B, AW0.82 и commit не выполнялись.']
    (ROOT/'docs/AW0.81_HARDWARE_SCALING_20PDF.md').write_text('\n'.join(lines)+'\n','utf8')
    print('FINAL_REPORT_GENERATED',verdict)


if __name__=='__main__':generate()
