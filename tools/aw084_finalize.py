"""Consolidate measured evidence and write the Russian decision report."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];QA=ROOT/'qa/aw084'
MODELS=['m2m100-418m','m2m100-1.2b','madlad-3b']


def read(name):return json.loads((QA/name).read_text('utf-8'))
def write(name,data):(QA/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
def gb(value):return f'{value/1e9:.2f}'


def main():
    frozen=read('frozen_state.json')
    changed=[p for p,h in frozen['files'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    review=read('semantic_review.json');metrics=read('automatic_metrics.json')['metrics'];installer=read('installer_impact.json')
    benchmarks={};memory={}
    for model in MODELS:
        memory[model]={}
        for device in ['cuda','cpu']:
            run=read(f'{model}-{device}.json');assert len(run['rows'])==75
            assert not any(run['runtime_imports'].values())
            if model!='m2m100-418m':assert 'fp32-int8' in run['model_resource_root']
            benchmarks.setdefault(device,{})[model]={k:run[k] for k in ['options','load_seconds','first_inference_seconds','warm','runtime_imports']}
            benchmarks[device][model]['failures']=[r for r in run['rows'] if 'error' in r]
            mem=run['memory'];samples=mem.get('inference_samples',[])
            memory[model][device]={k:v for k,v in mem.items() if k!='inference_samples'}
            memory[model][device]['peak_rss_bytes']=max([mem[k]['peak_rss_bytes'] for k in ['before','loaded','idle_loaded','after_unload']]+[s['peak_rss_bytes'] for s in samples])
            memory[model][device]['gpu_peak_total_used_bytes']=max([s['gpu_total_used_bytes'] or 0 for s in samples]+[mem['loaded']['gpu_total_used_bytes'] or 0])
            memory[model][device]['gpu_peak_increment_bytes']=max(0,memory[model][device]['gpu_peak_total_used_bytes']-(mem['before']['gpu_total_used_bytes'] or 0))
    write('gpu_benchmark.json',{'definition':'cold process load, not cold OS disk cache; warm single-segment sequential requests; failed attempts included in total',
        'hardware':'RTX 3080 12 GB','runs':benchmarks['cuda']})
    write('cpu_benchmark.json',{'definition':'8 threads, int8; same 75 requests; failed attempts included in total',
        'hardware':'Ryzen 7 5700X','runs':benchmarks['cpu']})
    write('memory.json',{'method':'Windows working-set counters including process peak; GPU-wide nvidia-smi samples every ~200 ms. GPU increment includes desktop/background fluctuations, not exact per-process allocation.',
        'runtime_unload':'RuntimeManager.release_models; Translator reference cleared; native unload_model(to_cpu=False). CUDA context can remain.',
        'runs':memory})
    accepted=json.loads((ROOT/'qa/aw083/accepted_segments.json').read_text('utf-8'))
    baseline=Path(accepted['outputs'][0]);expected='225196e28ef69788b2722c62c50ee2dd285a017a8e6be1919eb72a156e82ac27'
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()==expected
    with ZipFile(baseline) as archive:assert archive.testzip() is None
    end={'candidate_runs':'SKIPPED after failed semantic/production quality gates, per AW0.8.4 section 40; no winner integration',
        'accepted_baseline':{'run':'5582364caf97','source_pages':22,'output_pages':23,'segments':365,
            'canonical_published':'119/131','canonical_before_placement':'127/131','protected':'419/419',
            'OCR_noise_overlays':0,'OCR_continuations':0,'known_remaining_errors':4,'job_seconds':76.03,
            'zip':str(baseline),'sha256':expected,'CRC':'passed, rechecked; not a new document run'},
        'limitation':'No claim of candidate page/layout/publication validation. Production segment replay does not replace a full PDF run.'}
    write('end_to_end.json',end)
    decision={'decision':'NO WINNER FOR PRODUCTION','primary_backend':'existing M2M100 418M',
        'knowledge_changed':False,'production_integration':False,'new_release_zip':False,
        'reasons':{'m2m100-1.2b':'Measurable independent-set benefit and fewer nonsensical outputs, but body MAJOR+CATASTROPHIC 46/55 vs 45/55; production canonical 124/131 vs 127/131. No clear regression-free primary replacement.',
                   'madlad-3b':'Body critical failures 49/55; fabricated content; a decoder-limit failure; production guarded source residue 17 segments vs 8. FP16 diagnostic unreliable, int8_float32 does not fix all errors.'},
        'next_option':'Targeted terminology/compound-label coverage with independent holdout evaluation; recommendation only, no glossary expansion performed.',
        'stop':'AW0.8.4 only; no training, downloader, installer build or AW0.8.5 optimization',
        'frozen_state_verified':True}
    write('decision.json',decision)
    import xml.etree.ElementTree as ET
    xml=ET.parse(QA/'regression.xml').getroot();suite=xml.find('testsuite')
    regression={k:int(suite.attrib[k]) for k in ['tests','failures','errors','skipped']}
    assert regression['failures']==regression['errors']==regression['skipped']==0
    write('regression.json',regression)
    lines=['# TreeTranslate AW0.8.4 — оценка офлайн-движков',
        '', 'Дата отчёта: 02.10.2026. Решение: **NO WINNER FOR PRODUCTION**. Основной движок остаётся M2M100 418M.',
        '', 'У 1.2B есть измеримый прирост на независимых предложениях и меньше бессмысленных ответов. Однако это не равно безопасной замене: кузовные подписи остаются неточными, а действующие терминологические ограничения местами работают хуже. MADLAD в проверенном CT2 int8-развёртывании ненадёжна. Словарь и модель решают разные задачи.',
        '', '## 1. Зачем проводилась оценка',
        '', 'После AW0.8.3 четыре ошибки затрагивают связи внутри предложений: состояние рулетки, проекцию на плоскость, разницу высот и отсутствие люфта. Нужно было отделить качество модели от результата Knowledge/OCR и проверить возможность офлайн-поставки.',
        '', '## 2. Принятая база',
        '', 'База AW0.8.3 сохранена: 7 PDF, 22 исходные страницы, 365 сегментов (121 native / 244 OCR), 23 выходные страницы; 119/131 канонических в опубликованном PDF и 127/131 до размещения; 419/419 защищённых значений; 0 шумовых OCR-наложений, 0 OCR-продолжений; четыре известные ошибки; job 76.03 s, прежняя регрессия 663 passed. Это исторический accepted-run 5582364caf97, а не переоценка этих чисел.',
        '', f'Исходный accepted ZIP повторно проверен по SHA256 `{expected}` и CRC. Новый прогон документов не выдаётся за прежний результат.',
        '', '## 3. Кандидаты и одинаковые условия',
        '', 'Сравнивались 418M, M2M100 1.2B и MADLAD-400 3B-MT. NLLB не скачивалась и не включалась. Все тесты читают один замороженный semantic_gold; Knowledge, пользовательский glossary и TM одинаковы (последние два изолированы и пусты). Хеши пакетов, manifest, runtime requirements и gold проверены до решения. Никаких записей в пользовательскую TM.',
        '', 'Raw: beam=4, max decoding=512, batch tokens=2048, 8 CPU threads. M2M GPU — int8_float16; MADLAD GPU — int8_float32 после диагностически подтверждённой ненадёжности FP16. CPU — int8. Особенности compute явно записаны; разные режимы не скрыты.',
        '', '## 4. Лицензии и происхождение',
        '', '| Модель | Источник | Лицензия | Коммерческое использование / распространение | Условия |',
        '|---|---|---|---|---|',
        '| M2M100 418M / 1.2B | Facebook/Meta, официальные HF checkpoints | MIT | Разрешены условиями MIT | Сохранить copyright и текст лицензии |',
        '| MADLAD-400 3B-MT | Google HF repository; upstream Google Research | Apache-2.0 | Разрешены условиями Apache-2.0 | Лицензия, атрибуция, отметка конвертации; сохранить upstream NOTICE, если он предоставлен |',
        '', 'MADLAD HF checkpoint сам является опубликованной Google конверсией из T5X, с атрибуцией Juarez Bochi. Готовая сторонняя CT2 binary не использовалась: CT2 conversion выполнена локально. Полные лицензии и хеши сохранены в `qa/aw084/licenses` и `license_audit.json`. Аудит моделей не означает готовый коммерческий installer всего приложения: прежние вопросы других bundled-компонентов остаются вне этого цикла.',
        '', 'Первичные источники: [M2M100 1.2B](https://huggingface.co/facebook/m2m100_1.2B), [лицензия fairseq](https://github.com/facebookresearch/fairseq/blob/main/LICENSE), [MADLAD model card](https://huggingface.co/google/madlad400-3b-mt), [Google Research license](https://github.com/google-research/google-research/blob/master/LICENSE).',
        '', '## 5. Конвертация и runtime',
        '', 'Developer environment `.venv-build` использует Torch/Transformers для локальной подготовки. Production `.venv` выполняет CT2/SentencePiece без импорта Torch, Transformers или HF Hub. Сеть блокируется существующим offline_scope. Production requirements, Router и manifest не изменены; кандидаты находятся только в build/aw084.',
        '', 'Начальная конвертация с промежуточным FP16 сохранена в fp16-load-pilot. После сравнения с исходной MADLAD FP32 выполнена повторная прямая FP32→CT2 int8-конвертация обеих моделей. В итоговых замерах используются именно эти ресурсы. MADLAD float16 diagnostic выдал replacement/unknown-последовательности и отвергнут. Это вывод о проверенном развёртывании, не доказательство плохого качества любых возможных вариантов MADLAD.',
        '', 'Токенизация MADLAD проверена относительно официального slow tokenizer, включая <2ru>/<2zh>, Chinese, Russian и числа. Decoder start соответствует опубликованному config. Полный FP32 HF inference использовался только как ограниченная developer-диагностика пяти случаев. Архитектура адаптеров следует существующим BaseBackend, translate_segments, ModelManager, DeviceManager и RuntimeManager. [Документация CT2](https://opennmt.net/CTranslate2/guides/transformers.html).',
        '', '## 6. Raw-смысл, две отдельные группы',
        '', 'В корпусе 55 буквальных кузовных фрагментов: 12 предложений/пояснений и 43 подписи. Сорок уникальных длинных предложений в исходном gold отсутствуют; подписи не названы предложениями. Ещё 20 независимых примеров взяты из существующих локальных QA: 12 authored cases, 6 coolant excerpts и 2 явно отмеченные извлечённые части предложений. Production не читает gold.',
        '', 'Покейсная оценка Codex сохранена с source/reference/output/обоснованием и PASS/MINOR/MAJOR/CATASTROPHIC. Это проверяемая AI-assisted оценка, а не независимая сертификация человеком. Сырые ошибки ниже не являются числом ошибок опубликованного AW0.8.3 PDF: exact Knowledge в этом suite отключена.',
        '', '| Движок | Кузовные: MAJOR + CATA / 55 | Из них CATA | Независимые: MAJOR + CATA / 20 | Из них CATA | chrF++ кузов / независимые |',
        '|---|---:|---:|---:|---:|---:|']
    for model in MODELS:
        summaries=review['summary'][model]
        body=summaries['body'];ind=summaries['independent']
        lines.append(f"| {model} | {body.get('MAJOR',0)+body.get('CATASTROPHIC',0)} | {body.get('CATASTROPHIC',0)} | {ind.get('MAJOR',0)+ind.get('CATASTROPHIC',0)} | {ind.get('CATASTROPHIC',0)} | {metrics[model]['body']['chrF++']:.2f} / {metrics[model]['independent']['chrF++']:.2f} |")
    lines += ['', 'chrF/chrF++/BLEU — вспомогательные показатели, не критерий победы. Они считаются отдельно для prose/labels/independent. В одном coolant-reference записана политика сохранения спорных единиц, поэтому его MT score особенно условен. Перечень автоматических flags включает числа, protected guard, Chinese residue, empty, length ratio, repetition, replacement и language-tag garbage. Полные данные: automatic_metrics.json.',
        '', '## 7. Четыре оставшиеся ошибки — все тексты',
        '', 'Ниже показаны raw переводы трёх моделей и final production. Последний остаётся принятой AW0.8.3 версией 418M: новый движок не интегрирован. Результаты с текущим Knowledge отдельно доступны в production replay.']
    gold=read('semantic_gold.json')['entries'];raw={m:{r['id']:r for r in read(f'{m}-cuda.json')['rows']} for m in MODELS}
    prod={m:read(f'{m}-production.json')['rows'] for m in MODELS}
    for case_id in ['body-03','body-05','body-06','body-10']:
        case=next(c for c in gold if c['id']==case_id)
        lines += ['', f"### {case_id}",'',f"**ZH:** {case['source_zh']}",'',f"**Gold RU:** {case['reference_ru']}",'', '| Вариант | Текст |','|---|---|']
        for model in MODELS:
            lines.append(f"| Raw {model} | {raw[model][case_id].get('text','ERROR')} |")
        for model in MODELS:
            row=next(r for r in prod[model] if r['source']==case['source_zh'])
            lines.append(f"| С Knowledge: {model} | {row['text']} |")
        accepted_row=next(s for d in accepted['documents'] for s in d['segments'] if s['text']==case['source_zh'])
        lines.append(f"| Final production (418M, unchanged) | {accepted_row['translated']} |")
    lines += ['', '1.2B лучше сохраняет проекцию и разницу высот, но орбитальный прибор и «нет пробелов» остаются ошибками. MADLAD с Knowledge улучшает некоторые из этих инструкций, однако это не отменяет большого числа других искажений. Все четыре production outputs проходят текущие структурные проверки: fallback только по числам/мусору не умеет обнаружить ошибочный смысл. См. quality_fallback.json.',
        '', '## 8. Все 365 production-сегментов',
        '', 'Replay использует прежние сегменты, настоящий DocumentJob._pdf_translation, тот же Knowledge/glossary, Router и guards. OCR не запускалась заново; placement не измеряется этим suite. У MADLAD сохраняется обычный Router fallback, включая Argos, поэтому эти результаты нельзя выдавать за чистый MADLAD inference.',
        '', '| Вариант | Protected | Канонические до размещения | Сегменты с Chinese residue, включая сохранённый OCR noise | Guard-preserve |',
        '|---|---|---|---:|---:|']
    for model in MODELS:
        p=metrics[model]['production'];assert p['segments']==365
        lines.append(f"| {model} | {p['protected_preserved']}/{p['protected_total']} | {p['canonical_before_placement'][0]}/{p['canonical_before_placement'][1]} | {p['Chinese_residue_segments']} | {p['guard_preserved_segments']} |")
    lines += ['', '1.2B теряет три канонических попадания: срабатывает прежний возврат к unconstrained output, и отдельные термины из инструкции/подписи перестают соответствовать Pack. Это не исправлялось добавлением exact entries. MADLAD чаще сохраняет исходник через guards; рост терминологической цифры до 128 не доказывает сохранение смысла предложения.',
        '', '## 9. Обобщение на независимых документах',
        '', 'У 1.2B критических ошибок 6/20 вместо 12/20; при этом остаются непрерывное литьё, материал «расплавленная сталь», балка/кран, режим заполнения ITM и спорные единицы. MADLAD — 10/20 и четыре catastrophic, включая выдуманную плотину/вопрос, потерю запрета и decoder limit. Корпус маленький; универсального рейтинга по нему нет. unknown_terms.json связывает шесть отсутствующих в AW0.8.3 body Pack понятий с уже замороженными случаями.',
        '', '## 10. RU→ZH',
        '', 'Для каждого проверены две отдельные русские инструкции. Обе M2M-модели сохраняют общую структуру, но неверно называют наконечник/радиатор; MADLAD может лучше передать радиатор, но это два smoke cases, а не доказательство общего превосходства. Направление RU→ZH не меняется. Все тексты находятся в полях smoke исходных benchmark-файлов.',
        '', 'EN↔RU/DE/FR/ES/JA проверены отдельным коротким smoke; язык и теги работают. Это не quality audit всех 42 направлений и не основание менять backend для всех языков.',
        '', '## 11–12. GPU и CPU: загрузка отдельно от тёплого перевода',
        '', '| Движок | GPU load / first inference, s | GPU median / p95 / total, s | CPU load / first inference, s | CPU median / p95 / total, s | GPU / CPU segments/s |',
        '|---|---|---|---|---|---|']
    for model in MODELS:
        g=benchmarks['cuda'][model];c=benchmarks['cpu'][model];gw=g['warm'];cw=c['warm']
        lines.append(f"| {model} | {g['load_seconds']:.2f} / {g['first_inference_seconds']:.2f} | {gw['median_seconds']:.3f} / {gw['p95_seconds']:.3f} / {gw['total_seconds']:.2f} | {c['load_seconds']:.2f} / {c['first_inference_seconds']:.2f} | {cw['median_seconds']:.3f} / {cw['p95_seconds']:.3f} / {cw['total_seconds']:.2f} | {gw['segments_per_second']:.2f} / {cw['segments_per_second']:.2f} |")
    lines += ['', 'Total: 75 одинаковых запросов, включая неуспешные попытки; у MADLAD одна decoder-limit ошибка. Её CPU-попытка занимает около 137 s, поэтому средний total нельзя объяснять только median. Characters/s и полные latency сохранены. Cold означает первый load в новом процессе; файловый кеш Windows не очищался. После прерывания результаты с прежними ресурсами исключены; concurrent/FP16 pilot-файлы сохранены отдельно.',
        '', 'Это raw-инференс, не время ZIP-задачи. Knowledge обычно обходят большую часть сегментов; ~76.03 s accepted-job включает OCR/PDF/publication и не сопоставляется напрямую с raw totals.',
        '', '## 13. RAM, VRAM и выгрузка',
        '', '| Движок | GPU-process peak RSS, GB | CPU-process peak RSS, GB | Пиковая прибавка VRAM, GB | Общая GPU VRAM после unload, GB |',
        '|---|---:|---:|---:|---:|']
    for model in MODELS:
        g=memory[model]['cuda'];c=memory[model]['cpu']
        lines.append(f"| {model} | {gb(g['peak_rss_bytes'])} | {gb(c['peak_rss_bytes'])} | {gb(g['gpu_peak_increment_bytes'])} | {gb(g['after_unload']['gpu_total_used_bytes'])} |")
    lines += ['', 'Нативные модели реально выгружены RuntimeManager; GPU context/desktop не должны исчезать вместе с весами. Замер GPU-wide, возможны колебания фоновых приложений; пики sampled, не абсолютная аппаратная граница. Ни кандидат, ни его тесты не меняют последовательную политику освобождения translation VRAM перед PaddleOCR.',
        '', '## 14–15. Размер модели и прибавка к поставке',
        '', '| Движок | Оригинальные веса/ресурсы, GB | CT2 int8 с tokenizer, GB | Tokenizer, MB | Сжатая прибавка модели, GB | Текущий payload + модель, GB |',
        '|---|---:|---:|---:|---:|---:|']
    for model in MODELS:
        s=installer['candidates'][model];original=s['original_source_bytes']
        if model=='m2m100-418m':original=read('baseline_inventory.json')['original_pytorch_bytes']
        lines.append(f"| {model} | {gb(original)} | {gb(s['converted_quantized_bytes'])} | {s['tokenizer_bytes']/1e6:.2f} | {gb(s['model_deflate6_bytes'])} | {gb(s['current_plus_candidate_deflate6_estimate_bytes'])} |")
    lines += ['', 'Десятичные GB/MB. Baseline уже входит в текущий payload; его сжатый размер показан справочно, не добавляется второй раз. Для кандидатов baseline сохраняется как fallback. Runtime additions — 0: новые Torch/Transformers не нужны.',
        '', 'Метод: streaming DEFLATE level 6 выбранных production wheels, изолированного OCR runtime, Python, ресурсов/моделей/лицензий приложения и кандидата. Это частичная оценка payload, не размер готового installer: рецепт упаковки ещё не задан, wrapper/headers не измерены, повторённые DLL учитываются консервативно. В этом подсчёте отсутствуют metadata-selected distributions colorama, packaging, PySide6, PySide6-Addons, PySide6-Essentials и shiboken6; абсолютные итоги поставки неполны. Сжатая прибавка файлов каждой модели измерена отдельно и от этого пропуска не зависит. Developer trees, исходные веса, caches и .venv-build исключены. Полный метод и missing distributions — installer_impact.json. Даже при хорошем качестве MADLAD заметно увеличивает поставку; надёжный float16-вариант не подтверждён.',
        '', '## 16. Регрессия и fault checks',
        '', f"**{regression['tests']} passed, 0 failed, 0 errors, 0 skipped.** Полная existing regression плюс девять новых QA tests. JUnit: regression.xml. Отдельный targeted run: 38 passed.",
        '', 'Проверены candidate manifest/checksum mismatch/missing file, CPU/GPU load options и reuse/unload, cancel до load, языковой контракт, возможность fallback к существующему 418 contract, отсутствие production imports developer/QA modules и скрытого чтения gold. Existing tests проверяют Auto, protected numbers, exact Knowledge bypass, offline/no-network и runtime lifecycle. Реальные CPU/GPU/offline/import/unload probes подтверждены benchmark-артефактами. Fake fault tests не выдаются за реальные загрузки больших моделей.',
        '', '## 17–18. Решение и его причина',
        '', '**NO WINNER FOR PRODUCTION.** 418M остаётся основной. 1.2B перспективна на независимом set и менее часто выдаёт бессмысленный текст, но не проходит весь quality gate без регрессии: критические raw-ошибки кузовных фрагментов 46/55 против 45/55 и канонические 124/131 против 127/131. MADLAD не проходит semantic/residue/reliability gate, даже после bounded repair и смены compute.',
        '', 'Suite C после этих провалов не запускалась, в соответствии с требованием сначала дешёвого gate. Не заявляется, что новые движки прошли layout/7-PDF/publication. Production не усложнена, новый release ZIP не создан. Accepted 7-PDF ZIP и закрытые OCR/PDF/ZIP/Knowledge изменения сохранены.',
        '', '## Практические варианты развития: что они действительно меняют',
        '', '| Вариант | Что может исправить | Что остаётся нерешённым | Цена и сложность | Вывод сейчас |',
        '|---|---|---|---|---|',
        '| 418M + текущий Pack | Проверенный baseline; точные известные термины, защищённые значения, существующий PDF/OCR | Четыре известные ошибки смысла, неизвестные составные подписи | Дополнительных ресурсов нет; самая проверенная конфигурация | Оставить текущей production-базой |',
        '| 418M + расширенный технический словарь | Названия деталей, инструменты, отверстия, составные подписи; при надёжном полном совпадении можно обходить модель | Отрицание, условие, порядок операций, сравнение и грамматическое согласование вне точных правил | Обычно малая прибавка SQLite относительно гигабайтов модели; нужны отбор и техническая проверка каждой записи | Наиболее прямой следующий эксперимент для подписей; прирост ещё не измерен |',
        '| 1.2B + текущий Pack | Меньше бессмысленных ответов; лучше разница высот/проекция; independent critical 12→6 | Body critical 45→46; канонические 127→124; люфт и сложные названия остаются | Модель около 1.26 GB, slower raw inference; тот же CT2 runtime | Полезный QA-кандидат, недостаточно для замены primary |',
        '| MADLAD int8 + текущий Pack | Некоторые предупреждения и предложения передаются лучше | Выдуманные армии/население/плотина, потеря запретов, decoder limit, residue 8→17 | Около 2.96 GB; более медленная, особенно CPU; GPU int8_float32 требуется вместо предпочтительного FP16 | Отвергнуть проверенное развёртывание |',
        '| Расширенный словарь + 1.2B | Словарь может закрыть термины, 1.2B — часть связей предложения | Более крупная модель всё равно может терять смысл; нельзя обещать сумму улучшений без проверки | Качество словаря плюс размер/скорость 1.2B; нужен новый одинаковый holdout для обеих моделей | Возможный последующий эксперимент, не доказанный выигрыш |',
        '| 418M → quality engine по структурной ошибке | Ошибочные числа, Chinese residue, decoder garbage, empty/length anomalies | Четыре известные ошибки проходят guards; ошибочный смысл не создаёт trigger | Повторный перевод только части сегментов; требуется строгий критерий и освобождение VRAM | Не решает текущую смысловую проблему автоматически |',
        '| Domain adaptation / другой класс модели | Потенциально технические связи и терминология как часть общего языка | Требуются новые данные/оценка; результат неизвестен | Отдельное исследование, обучение/лицензии/ресурсы не измерены | За пределами AW0.8.4; не запускалось |',
        '', 'Словарь полезнее измерять покрытием, чем количеством слов. 94 canonical entries уже дают 127/131 проверенных попаданий до placement, но 131 — это только наш набор occurrences, не все понятия любого технического документа. Массовое добавление неоднозначных слов может навредить. Например, отдельные «отверстие», «петля», «дверь» не задают отношения; проверенная запись «отверстие крепления верхней петли передней двери» задаёт их целиком.',
        '', 'Разумный следующий цикл: список действительно отсутствующих понятий и compound labels → проверенные переводы с предметной областью и вариантами написания → отдельные документы holdout → сравнение terminology coverage, semantic failures, residue и published placement. Сначала нужно видеть, какие ошибки являются терминами, а какие отношениями предложения. Число записей и ожидаемый процент улучшения сейчас не выдумываются.',
        '', 'Если обновлённый словарь устранит большинство оставшихся практических проблем, потребность в тяжёлой модели уменьшится. Если сохранятся неправильные отрицания и условия, большой словарь не будет доказательством, что модель больше не нужна. Проверять это следует раздельно.',
        '', '## 19. Ограничения и остановка',
        '', 'Малый локальный corpus; многие raw labels уже закрываются production Knowledge. Проверка смысла выполнена Codex и доступна для независимой проверки, а не сертифицирована техническим редактором. Нельзя переносить преимущества ZH→RU на RU→ZH и все языки. MADLAD rejected относится к проверенным CT2 вариантам; original HF FP32 в нескольких примерах корректнее. У кандидатов нет E2E/layout acceptance. Installer estimate не является готовым installer.',
        '', 'AW0.8.4 остановлена после отчёта. Словарь не расширялся, fine-tuning/downloader/installer/AW0.8.5 не начинались. Новые компоненты — только изолированные QA инструменты и тесты; production UI/архитектура не перерабатывались. Все промежуточные попытки и окончательные измерения сохранены в qa/aw084; большие dev-ресурсы — build/aw084. Коммит не создан.',
        '', 'Артефакты: candidate_inventory.json, semantic_gold.json/engine_semantic_gold.json, raw_outputs.json, automatic_metrics.json, semantic_review.json, gpu_benchmark.json, cpu_benchmark.json, memory.json, installer_impact.json, license_audit.json, end_to_end.json, decision.json и regression.xml.', '']
    (ROOT/'docs/AW0.8.4_ENGINE_EVALUATION_REPORT.md').write_text('\n'.join(lines),'utf-8')
    print('REPORT COMPLETE',regression,decision['decision'])


if __name__=='__main__':main()
