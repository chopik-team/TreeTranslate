"""Assemble measured baseline report and delivery ZIP, without PDF rewriting."""
from collections import Counter
from pathlib import Path
import json
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
from qa_aw083_baseline import ROOT, QA, BUILD, digest, save


def load(name):return json.loads((QA/name).read_text('utf-8'))
def gib(n):return n/1024**3


def main():
    cold=load('cold-run.json');warm=load('warm-run.json');hardware=load('hardware.json')
    inventory=load('corpus-inventory.json');metrics=load('per-file-summary.json');quality=load('quality-structure.json')
    pipelines=load('pipeline-timings.json');reps=load('repetition-analysis.json');memory=load('memory.json')
    validation=load('validation.json');raw=load('raw-instrumentation.json')
    lines=['# TreeTranslate AW0.8.3 — baseline AW0.8.2', '',
        'Baseline измерен 29 сентября 2026 на существующем production AW0.8.2. Версия приложения не повышалась. '
        'Оптимизации, исправления качества, изменения моделей/OCR/PDF/Router/TM/Glossary не выполнялись.', '',
        '## Методика', '',
        'Новый процесс Qt MainWindow + штатный HybridTranslationService. Папка выбрана через существующий '
        'TranslationUiController; обе задачи запущены обычной кнопкой «Начать перевод». Source Auto, target Russian, '
        'device Auto; profile Automatic и domain auto выставлены самим штатным UI. Файлы выполняются последовательно. '
        'Имена файлов/вложенных каталогов не переводятся, структура сохранена. Настройки пользователя скопированы '
        'в отдельный QA INI; изменены только параметры этой задачи и папка результата. TM/glossary используются '
        'из штатных пользовательских путей, не очищались и не заменялись пустыми QA базами.', '',
        'Cold-ish: модели не использовались в новом процессе. Это не холодный дисковый/Windows cache: '
        'inventory и SHA256 были прочитаны заранее. Warm: тот же процесс, сервис и runtime, повтор без выгрузки '
        'моделей со стороны harness. Штатное освобождение translation models перед OCR и shutdown OCR в конце '
        'этапа извлечения не отключались. Поэтому название warm не обещает сохранения всех моделей в памяти.', '',
        'Instrumentation находится только в tools/qa_aw083_*.py: наблюдающие обёртки вызывают исходную функцию '
        'ровно один раз, без изменения возвращаемых объектов и без подмены writer. Время включает небольшие '
        'накладные расходы измерения, сбор RAM/VRAM и обычные UI callbacks. Это наблюдаемый baseline, не строгий microbenchmark.', '',
        '## Corpus и железо', '',
        f"Подтверждено **{inventory['count']} PDF / {inventory['pages']} страницы / {inventory['bytes']:,} bytes**. "
        f"ZIP SHA256: `{inventory['archive_sha256']}`. Native text присутствует; фотографии/схемы не считались чистым scan.", '',
        f"{hardware['cpu']}; {hardware['logical_cores']} logical threads; {hardware['ram_gb']} GB RAM; "
        f"{hardware['gpu']}; {hardware['vram_gb']} GB VRAM; CUDA={hardware['cuda_available']}.", '',
        '| PDF | Страниц | Bytes |', '|---|---:|---:|']
    for row in inventory['files']:lines.append(f"| {row['file']} | {row['pages']} | {row['size']} |")
    difference=cold['wall_seconds']-warm['wall_seconds']
    lines+=['','## Cold / warm','',f"**COLD TOTAL: {cold['wall_seconds']:.3f} s**  ",
        f"**WARM TOTAL: {warm['wall_seconds']:.3f} s**  ",
        f"Difference (cold − warm): **{difference:.3f} s / {difference/cold['wall_seconds']*100:.2f}%**.",'',
        f"Active processing: cold {cold['active_seconds']:.3f} s, warm {warm['active_seconds']:.3f} s. "
        f"Отдельный scan: {cold['scan_seconds']:.3f} / {warm['scan_seconds']:.3f} s. "
        f"Completed files: {len(cold['outputs'])} / {len(warm['outputs'])}; исходных страниц за проход: 22.",'',
        'Total в таблицах — первый open/extraction плюс интервал второго open → publication. '
        'Штатный первый этап обходит все файлы до начала перевода: простой wall-span отдельного файла '
        'включал бы работу над соседними PDF и был бы вводящим в заблуждение. Domain timing вынесен отдельно. '
        'Parse/OCR/Translate/Layout — вложенные inclusive timings, их нельзя складывать с Total. RAM — '
        'наблюдаемый пик main+OCR во время этого файла, а не отдельная память документа.']
    for name in ('cold','warm'):
        lines+=['',f'### {name.upper()}','',
            '| PDF | Pages | Type | OCR | Domain | Total s | Parse s | OCR s | Translate s | Layout/Write s | Peak RAM GiB | Status |',
            '|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|']
        for row in metrics:
            if row['run']!=name:continue
            lines.append(f"| {row['file']} | {row['pages']}→{row['output_pages']} | {row['classification']} | "
                f"{row['ocr_regions']} regions | {row['domain']['domain']} | {row['total_file_attributed_s']:.3f} | "
                f"{row['parse_s']:.3f} | {row['ocr_s']:.3f} | {row['translate_s']:.3f} | {row['layout_write_s']:.3f} | "
                f"{gib(row['peak_combined_rss']):.3f} | {row['status']} |")
    lines+=['','## Pipeline timings','',
        'Inclusive включает дочерние стадии; exclusive вычитает только наблюдаемые обёртки. '
        'Native extraction включает группировку текста; page classification и часть postprocess остаются в '
        'hybrid residual. PDF composition/save остаётся в residual pdf_write после выделенных layout/font calls. '
        'Точного независимого времени всех этих подсистем без более глубоких изменений нет.', '',
        '| Stage | Cold inclusive s | Cold self s | Warm inclusive s | Warm self s |','|---|---:|---:|---:|---:|']
    stages=sorted(set(pipelines['cold']['stages'])|set(pipelines['warm']['stages']))
    for stage in stages:
        a=pipelines['cold']['stages'].get(stage,{});b=pipelines['warm']['stages'].get(stage,{})
        lines.append(f"| {stage} | {a.get('inclusive_s',0):.3f} | {a.get('exclusive_s',0):.3f} | {b.get('inclusive_s',0):.3f} | {b.get('exclusive_s',0):.3f} |")
    lines+=['','## OCR, модели и устройство','',
        'Полное время OCR берётся из router wall time. Возвращаемые load/inference timings относятся только '
        'к выбранному распознавателю: Auto рассматривает больше одного кандидата и может переключить backend. '
        'Суммы ниже частичные; выдавать их за всё время инициализации/inference было бы неверно. '
        'Число всех worker roundtrips отдельно есть в pipeline-timings.json.']
    for name in ('cold','warm'):
        p=pipelines[name];ocr=[o for o in raw['ocr'] if o['run']==name]
        device_counts=Counter((o['backend'],o['device']) for o in ocr)
        paths=Counter((r['result']['backend'],r['result']['device'],r['result']['compute_type'],
                       tuple(r['result']['model_ids']),r['result']['fallback_used']) for r in raw['results'] if r['run']==name)
        lines+=['',f"{name}: OCR regions={len(ocr)}, pages={len({(o['file'],o['page']) for o in ocr})}; "
            f"OCR backend/device={dict(device_counts)}. Selected init={p['ocr_selected_load_s']:.3f} s; "
            f"selected inference={p['ocr_selected_inference_s']:.3f} s.",
            f"Translation result paths (backend/device/compute/model_ids/fallback): `{dict(paths)}`."]
    lines+=['', 'OCR reuse между batch: **нет**, штатный DocumentJob завершает OCR runtime после первого '
        'этапа. Внутри Auto распознавание проверяет основной и кириллический recognizer; worker хранит '
        'только последний ключ (device/backend/recognizer/options), поэтому чередование кандидатов '
        'не означает reuse одних и тех же моделей. Это свойство проверяемой версии, не изменение harness.', '',
        f"Translation runtime перед warm: `{warm['runtime_before']['warm_backend']}`; "
        f"после warm: `{warm['runtime_after']['warm_backend']}`. Перед OCR штатный before_ocr вызывает release_models."]
    lines+=['','## RAM / VRAM','',
        'RAM sampled ~0.2 s; GPU ~1 s. GPU значения device-wide, включают рабочий стол и другие процессы. '
        'Combined RAM — сумма main и наблюдаемых OCR child, sampled peaks не являются hard limits.']
    for name,run in [('cold',cold),('warm',warm)]:
        rows=[s for s in memory['ram'] if s['run']==name]
        gpu=[s['devices'][0][0] for s in memory['gpu'] if s.get('run')==name and s.get('devices')]
        lines+=['',f"{name}: baseline main {gib(run['rss_before']['main_rss']):.3f} GiB; "
            f"peak main {gib(max(s['main_rss'] for s in rows)):.3f}; "
            f"peak OCR children {gib(max(sum(c['rss'] for c in s['ocr_children']) for s in rows)):.3f}; "
            f"combined peak {gib(max(s['combined'] for s in rows)):.3f} GiB. "
            f"GPU before={run['vram_before'].get('devices')}, peak used={max(gpu) if gpu else None} MiB, "
            f"after={run['vram_after'].get('devices')} (used,total,utilization)."]
    lines+=['',f"После обычного shutdown приложения: `{memory['after_shutdown']}`. "
        'Idle timer не ускорялся; after-job и after-shutdown не обозначаются одним состоянием.',
        '', '## Повторения, TM и glossary', '']
    for name in ('cold','warm'):
        r=reps[name]
        lines.append(f"{name}: segments={r['segments']}; unique normalized={r['unique_normalized']}; "
            f"exact duplicates={r['exact_duplicates']}; backend calls={r['backend_calls']}; "
            f"native inference calls={r['native_inference_calls']}; duplicate chunks avoided={r['duplicate_chunks_avoided']}; "
            f"identical OCR region repeats={r['repeated_ocr_region_hashes']}; "
            f"target repeated phrase occurrences={r['repeated_target_phrase_occurrences']}.")
        lines+=['',f"TM deltas: `{r['tm_counter_delta']}`. Glossary deltas: `{r['glossary_counter_delta']}`.",'']
    lines+=['TM hits включают prefetch и повторные lookup; reused показывает реальные применения. '
        'Повторяющиеся строки документа и request-local chunk dedup — разные уровни. '
        'Новая дедупликация не вводилась. Полные повторяющиеся строки сохранены в локальном QA JSON.', '',
        '## Auto-domain', '', '| Run / PDF | Source | Domain | Score | Matches | Margin |','|---|---|---|---:|---:|---:|']
    for name,rows in load('domain-results.json').items():
        for row in rows:
            e=row['evidence'];lines.append(f"| {name} / {row['file']} | {row['source']} | {e['domain']} | {e['score']:.3f} | {e['matches']} | {e['margin']:.3f} |")
    lines+=['','Thresholds не изменялись; general фиксируется как измеренный результат, а не исправляется под ожидаемую тематику.', '',
        '## Structural QA и границы качества', '',
        f"Production validation: {validation['all_production_validation']}; файлы открываются: {validation['all_outputs_open']}; "
        f"image streams сохранены: {validation['image_streams_preserved']}. Source hashes unchanged: {validation['source_files_unchanged']}.", '',
        'Сравнение decoded image resources проверяет сохранность изображений; непрозрачные OCR overlays '
        'могут влиять на видимую схему, поэтому отдельно нужны renders. Числа, диаметры, единицы, dimensions '
        'и labels проверены на уровне native extracted text и segment mapping. Расхождения являются кандидатами '
        'для анализа: текст, оставшийся внутри растра, может отсутствовать в extracted text. '
        'Structural QA не доказывает правильность русского перевода.', '',
        '| Run/PDF | Output pages | Continuations | Preserved segments | Outside-page boxes | Overlap candidates | Token-difference segments | Warnings |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for q in quality:
        lines.append(f"| {q['run']}/{q['file']} | {q['output_pages']} | {q['continuation_pages']} | {q['preserved_segments']} | "
            f"{len(q['written_boxes_outside_page'])} | {len(q['written_box_overlap_candidates'])} | "
            f"{len(q['segment_token_difference_candidates'])} | {len(q['warnings'])} |")
    lines+=['','OCR candidates с исходным распознанным текстом/уверенностью — raw-instrumentation.json; '
        'native extraction — source-text/; точный input→translated→visible mapping с origin — segment-mapping/. '
        'Это позволяет разделять extraction/OCR/model/glossary/layout, не записывая любую плохую строку как ошибку модели.', '',
        '## Safety и regression', '',
        f"Production/config/model SHA256: проверено {validation['production_hashes_checked']}, изменений {len(validation['production_changes'])}. "
        f"ZIP unchanged={validation['source_archive_unchanged']}. Observed main network attempts={validation['main_network_attempts']}; "
        f"OCR attempts={validation['ocr_network_attempts']}. Runtime downloads не выполнялись; штатные offline/telemetry flags активны. "
        'Нативный сетевой трафик не перехватывался на уровне ОС; цифры относятся к audit hooks/worker counters.', '',
        'Исходники не перезаписывались. Cold/warm имеют разные output folders; внутри используется штатная '
        'collision-safe publication. Cancellation/pause architecture не менялась. Git commit/push/reset/revert не выполнялись.', '',
        '## Артефакты', '',
        '[QA directory](qa/aw083-baseline/): inventory, hardware, cold/warm, pipeline timings, memory, repetition, '
        'domains, structural QA, validation, per-file metrics, source/translated text, segment mapping, renders и outputs.', '',
        'Следующий optimization cycle не начат. Независимое сравнение качества пользователем ещё предстоит.']
    dominant=sorted(pipelines['cold']['stages'].items(),key=lambda item:item[1]['exclusive_s'],reverse=True)[:5]
    lines+=['','## Candidate bottlenecks — только наблюдения', '',
        'Наибольшие self-time группы cold: '+', '.join(f"{key} ({value['exclusive_s']:.3f} s)" for key,value in dominant)+'.', '',
        'Для следующего решения о производительности можно исследовать стоимость повторных OCR candidates/model '
        'initialization, одинаковых raster regions и repeated translation requests. Стадии layout/font '
        'сравниваются по измеренным self-times; ничего из перечисленного не оптимизировано в baseline. '
        'Разница cold/warm не является гарантированным ускорением без дополнительных контрольных повторов.']
    # Explicitly record actual checks, not assumed success.
    tests=ET.parse(QA/'targeted-tests.xml').getroot().find('testsuite').attrib
    checks={}
    for label,cmd in [('compileall',[sys.executable,'-m','compileall','-q','app','tools']),('diff_check',['git','diff','--check'])]:
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');checks[label]=p.returncode
    validation['regression']={k:tests[k] for k in ('tests','failures','errors','skipped')};validation['checks']=checks
    save(QA/'validation.json',validation)
    lines+=['',f"Targeted regression: `{validation['regression']}`. Checks: `{checks}`. "
        'Shared production code не изменялся, поэтому новый полный pytest по условиям baseline не требуется.']
    report=ROOT/'docs/AW0.8.3_BASELINE_REPORT.md';report.write_text('\n'.join(lines)+'\n','utf-8')
    (QA/'git-status-after.txt').write_bytes(subprocess.check_output(['git','status','--short'],cwd=ROOT))
    archive=QA/'TreeTranslate_AW0.8.2_车身尺寸_RU.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for path in map(Path,warm['outputs']):z.write(path,path.relative_to(QA/'output/warm').as_posix())
    with ZipFile(archive) as z:
        assert len(z.namelist())==7 and z.testzip() is None
    save(QA/'delivery.json',dict(archive=str(archive),sha256=digest(archive),pdfs=7,run='warm',
                                pdfs_unchanged_in_zip=True))
    print(report);print(archive)


if __name__=='__main__':main()
