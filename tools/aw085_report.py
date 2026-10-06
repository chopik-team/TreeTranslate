"""Consolidate preserved measurements; never edit source PDFs or production data."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw085_knowledge import QA,save

def read(name):return json.loads((QA/name).read_text('utf-8-sig'))

def main():
    old=read('base_before.json');new=read('base_after.json');cleanup=read('cleanup_result.json')
    metrics=read('quality_metrics.json');coverage={m:read('knowledge_coverage_'+m+'.json') for m in ['before','after']}
    cases=read('semantic_cases.json');semantic=read('semantic_review.json')
    run=read('accepted_segments.json');path=Path(run['outputs'][0])
    checked=['qa/aw083/body_dimensions_gold.json','qa/aw085/holdout_fresh.json','assets/config/automotive-grammar.json','assets/knowledge/aw083-body-repair-zh-ru.db']
    save('final_checksums.json',{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in checked})
    save('visual_review.json',dict(method='PDFium render of all 22 pages; seven contact sheets inspected by Codex; no writer changes',
        pages=22,documents=7,preserved_source_labels=16,limitation='Conservative placement preserves Chinese labels; published PDFs are not entirely Russian'))
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        assert len([n for n in archive.namelist() if n.lower().endswith('.pdf')])==7
    assert run['source_hash_before']==run['source_hash_after']=='6c952c34172b977f95e9098650a40f90d67ac83343feb822df8d271bd4f50d74'
    assert hashlib.sha256(Path('output/aw083/accepted/Размеры кузова_ru.zip').read_bytes()).hexdigest()=='225196e28ef69788b2722c62c50ee2dd285a017a8e6be1919eb72a156e82ac27'
    suite=ET.parse(QA/'regression.xml').getroot().find('testsuite')
    regression={k:int(suite.attrib[k]) for k in ['tests','errors','failures','skipped']}
    assert regression['tests']>=704 and not any(regression[k] for k in ['errors','failures','skipped']),regression
    save('regression.json',regression)
    # Explicit human-readable, AI-assisted grades after inspecting every output.
    # chrF / exact reference equality do not decide these semantic grades.
    label_grades=['MINOR','MINOR','MAJOR','MAJOR','MAJOR','MAJOR','CATASTROPHIC','CATASTROPHIC','MINOR','MINOR',
        'MAJOR','MINOR','PASS','PASS','PASS','PASS','CATASTROPHIC','MINOR','MINOR','CATASTROPHIC','MAJOR',
        'PASS','MINOR','MINOR','MAJOR','MINOR','MAJOR','MAJOR','MAJOR','MAJOR']
    prose_before=['MINOR','MAJOR','MAJOR','CATASTROPHIC','MAJOR','PASS','PASS','MAJOR','MINOR','PASS']
    prose_after=['MAJOR','MINOR','MAJOR','MINOR','MAJOR','PASS','PASS','MINOR','MINOR','PASS']
    fresh=read('holdout_fresh_results.json');holdout_rows=[]
    for i,(a,b) in enumerate(zip(fresh['before'],fresh['after'])):
        grade_before=label_grades[i] if i<30 else prose_before[i-30]
        grade_after='PASS' if i<30 else prose_after[i-30]
        holdout_rows.append(dict(source=a['source'],reference=a['reference'],before=a['output'],after=b['output'],
            kind=a['kind'],before_status=grade_before,after_status=grade_after,
            note=('One semantic regression: deformation-check predicate omitted' if i==30 else
                  'Unseen prose: case agreement/technical predicate reviewed separately from known terms' if i>=30 else
                  'Unseen dimensional combination; shared reviewed technical concept, not an unseen-concept test')))
    holdout_summary={m:Counter(r[m+'_status'] for r in holdout_rows) for m in ['before','after']}
    save('holdout_semantic_review.json',dict(reviewer='Codex; auditable AI-assisted review, not independent human certification',
        summary=holdout_summary,rows=holdout_rows,limitation='30 labels reuse known concepts with unseen dimensions; 10 fresh prose. Earlier holdout became development set; fresh set was not used for subsequent fixes.'))
    after=metrics['after']['totals'];before=metrics['before']['totals'];timing_change=(metrics['after']['job_seconds']/metrics['before']['job_seconds']-1)*100
    status=dict(cycle='AW0.8.5',decision='CONTROL_CORPUS_IMPROVED_WITH_LIMITATIONS',primary='M2M100 418M unchanged',
        full_gate=False,remaining=['Fresh prose-01 lost deformation predicate; three fresh prose MAJOR errors remain',
            '16 labels have translation available but placement retains Chinese source',
            'Six ambiguous component labels require OEM nomenclature confirmation',
            'AW0.8.5 scratch deletion blocked by automatic review; 9.77 MB retained'],
        zip=str(path),zip_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),regression=regression)
    save('acceptance.json',status)
    lines=['# TreeTranslate AW0.8.5 — Knowledge Expansion + AW0.8.4 Cleanup','',
        'Дата: 02.10.2026. Основной движок **M2M100 418M сохранён**. Новый ZIP создан и проверен. Контрольные инструкции существенно улучшены; полный acceptance gate не объявлен пройденным из-за ограничений новых предложений и заблокированного удаления scratch.', '',
        '## 1–3. Cleanup, освобождённый объём и журнал','',
        f"Пользователь вручную удалил `C:/TreeTranslate/build/aw084`: **{cleanup['deleted_files']} файлов / {cleanup['deleted_bytes']:,} байт / {cleanup['deleted_bytes']/1e9:.2f} GB ({cleanup['deleted_bytes']/1024**3:.2f} GiB)**. Инвентарь с path/size/reason/owner_cycle записан до удаления в cleanup_inventory.json. Отсутствие папки проверено; новые модели не нужны production.",'',
        'Удалены оригинальные веса 1.2B/MADLAD, CT2 FP16-load и FP32-конверсии, float16 probe и transient benchmark DBs. `.venv-build` сохранена: документ AW0.4_IMPLEMENTATION_REPORT.md подтверждает её существование до AW0.8.4. Глобальные HF caches и другие неизвестные developer files не удалялись: их принадлежность циклу не доказана.', '',
        'Production model manifest, runtime requirements, старый gold и остальные Knowledge DB сохранили хеши. Все 15 manifest-записей translation/Argos/OCR прошли полную проверку размеров и SHA256. TreeTranslate реально запущен для контрольного ZIP, M2M100/OCR работают; production imports не ссылаются на research weights. AW0.8.4 tests используют tiny fixtures и mocks, реальные большие веса им не нужны.', '',
        'В docs/DEVELOPMENT_JOURNAL.md добавлена одна компактная запись AW0.8.4. documents.log содержит только настоящие document jobs; developer evaluation туда не записывалась. Final AW0.8.4 report, QA evidence/licenses/gold, исходный ZIP и прежний accepted ZIP сохранены.', '',
        '## 4–5. Coverage BEFORE → AFTER','',
        'Coverage оценивает доступность доверенного перевода до размещения. Оно не равно качеству всех китайских предложений или числу русских подписей в опубликованном PDF. Защищённые числа/идентификаторы и намеренно сохранённый OCR noise исключены из смыслового знаменателя.', '',
        '| Показатель | До | После |','|---|---:|---:|']
    for label,key in [('Все сегменты','total_segments'),('Смысловые сегменты','total_semantic_segments'),('KNOWN: прямой перевод, включая фразы/суффиксы','exact_known'),('Из них phrase/full-segment known','phrase_known'),('PARTIAL','partially_known'),('Длинные инструкции, требующие модели','long_prose_requiring_model')]:
        lines.append(f"| {label} | {coverage['before'][key]} | {coverage['after'][key]} |")
    lines += ['| UNKNOWN: сегменты | 14 | 0 |','| PROTECTED / noise | 232 | 232 |','',
        'До: 100 KNOWN, 18 PARTIAL, 14 UNKNOWN, 1 MODEL-ONLY. После: 133 KNOWN. Уникальные unknown technical segments и все исходные позиции доступны в knowledge_coverage_before/after.json. UNKNOWN здесь — сегменты, а не независимо подсчитанные уникальные понятия.', '',
        '## 6–8. Записи, compound terminology и phrase knowledge','',
        f"Автомобильный пакет: **{old['entries']} → {new['entries']} записей**, прибавка {new['entries']-old['entries']}. Одна существующая SQLite DB и существующая TranslationKnowledgeEngine/GlossaryEngine; нового pipeline/schema нет.", '',
        '| Тип | Всего после |','|---|---:|']
    for kind,count in new['types'].items():lines.append(f'| {kind} | {count} |')
    lines += [f"| Явные aliases дополнительно | {new['aliases']} |",f"| ZH→RU | {new['ZH_RU']} |",'| Добавлено RU→ZH | 0 |','',
        'Пакет automotive. Типы записаны в существующем notes как JSON; domain, pair, trust, provenance остаются штатными колонками. Каждая новая запись имеет source/target/type/domain/pair/trust/provenance/review_status=VERIFIED и обозначенного reviewer. VERIFIED означает проверку Codex; независимая человеческая техническая сертификация не заявляется. AUTO-записи не повышались массово до BUILTIN.', '',
        'Приоритет compound: крепления верхней/нижней петли передней/задней двери, ограничители открывания, ответные части замков, кронштейны, подрамники, усилители, межцентровые расстояния. Обновлены отсутствовавшие составные подписи; generic 检验器 не объявлен синонимом любого ограничителя — только полные door-check labels. Traditional/OCR aliases явные; NFKC full-width normalization остаётся прежней, fuzzy не добавлен.', '',
        'Фразы: использование рулетки, опорная плоскость, разница высот, отсутствие люфта, запрет изгиба/перекручивания/растяжения. Частичные шаблоны не считаются гарантией смысла сложной инструкции. Поэтому добавлены reviewed короткие/средние устойчивые инструкции из утверждённых local references, включая четыре проблемных случая. Целые страницы, длинные OEM paragraphs или IDs в pack не хранятся.', '',
        'Грамматика: ограниченные новые noun slots используют строчную форму внутри предложений; проверенные русские patterns исправляют «при использовании рулетка», «два точка измерения», «измерить разница высот» и несколько аналогичных конструкций. Это не morphology engine. Неоднозначные короткие verbs/фрагменты не дробят предложения. Диаметр/межцентровое расстояние 孔径/孔距 не поглощаются более коротким builtin словом, заканчивающимся на 孔. Явные пользовательские rules сохраняют приоритет и не изменяются этими patterns.', '',
        'TM остаётся первой существующей границей; пользовательский glossary сохраняет приоритет над builtin. Затем доверенный полный segment/compound/phrase, constraints, существующая модель/fallback. Нумерация инструкции сохраняется буквально; вложенные list markers не разрешают substring bypass. Файлы/папки проверены targeted tests: Размеры кузова, Общие сведения, части кузова, Ремонт кузова.', '',
        '## 9–10. Четыре известные смысловые ошибки и BEFORE → AFTER','',
        'Все десять ранее зафиксированных инструкций сопоставлены с исходным reference; четыре обязательных случая ниже. PASS касается смысла конкретных проверенных инструкций; это не универсальная точность модели.', '',
        '| Source | AW0.8.3 | AW0.8.5 | Reference / статус |','|---|---|---|---|']
    for case in cases:
        if case['source'].startswith(('3.','5.','6.','检查探头')):
            lines.append(f"| {case['source']} | {case['before']} | {case['after']} | {case['reference']} — {case['status']} |")
    lines += ['', 'Все десять текстов, включая published form, — semantic_cases.json. Все 133 смысловых сегмента каждого из семи PDF — semantic_review.json: 127 PASS, 6 MINOR; шесть MINOR отражают неоднозначные названия вещевого отсека/технологических отверстий, для которых полезна проверка OEM nomenclature по схеме. Это существенный практический прирост, но не обещание отсутствия любой технической неоднозначности.', '',
        '## 11. Метрики каждого PDF','',
        '| PDF | Исходные / выходные страницы | Protected | Термины до placement, concepts | Published concepts | Residue A / B / C |','|---|---|---|---|---|---|']
    for d in metrics['after']['documents']:
        lines.append(f"| {d['file']} | {d['source_pages']} / {d['output_pages']} | {d['protected_preserved']}/{d['protected_total']} | {d['canonical_translation_concepts']}/{d['canonical_total']} | {d['canonical_published_concepts']}/{d['canonical_total']} | {d['residue_A']} / {d['residue_B']} / {d['residue_C']} |")
    lines += ['',f"До placement: **{after['canonical_translation_concepts']}/{after['canonical_total']} = {100*after['canonical_translation_concepts']/after['canonical_total']:.2f}%** с проверенными русскими склонениями/координацией. Не засчитано упоминание кузовной линейки в шестой инструкции: утверждённый reference говорит о наконечнике без повторения названия прибора. Published concepts: {after['canonical_published_concepts']}/131, ниже цели 98% — ограничения placement не скрыты.", '',
        f"Исходная strict-substring метрика сохранена: до placement {before['canonical_translation_strict']}/131 → {after['canonical_translation_strict']}/131; published {before['canonical_published_strict']}/131 → {after['canonical_published_strict']}/131. Снижение связано со склонениями («рулетки», «передней двери»), полными фразами и сохранёнными короткими boxes. Это не выдаётся за прежнюю метрику 127/131: concept score — отдельный auditable QA metric с явными evaluation-only variants, production их не читает. На обеих версиях он пересчитан одинаково: {before['canonical_translation_concepts']}/131 → {after['canonical_translation_concepts']}/131.", '',
        'ZIP CRC и validators пройдены; исходный SHA256 неизменен, accepted AW0.8.3 ZIP тоже неизменен. 22 исходные → 22 выходные страницы; лишняя страница исчезла благодаря более коротким правильным инструкциям, writer не менялся. OCR continuation/noise overlays 0, protected 419/419. Все 22 страницы отрендерены, контактные листы семи PDF осмотрены; схемы и измерения сохранены, переполненные подписи остаются исходными. Visual QA: qa/aw085/visual.', '',
        'После окончательных grammar/boundary fixes отдельно проверены все 133 прямых перевода: они буквально совпадают с уже отрендеренным ZIP. Это контроль неизменности output, не новый OCR run. final_policy_control_replay.json.', '',
        '## 12. Независимые примеры / holdout','',
        'Первый set стал development set при проверке grammar policy; его результаты и неудачная unconstrained попытка сохранены и не выдаются за слепой holdout. Затем составлены и заморожены ещё 40 примеров: 30 новых сочетаний подписи/размера и 10 ранее не проверенных нейтральных инструкций. Никаких pack additions после их результатов. Источники — собственноручные нейтральные примеры, без web-copy/OEM paragraphs.', '',
        '30 подписей намеренно используют изученные понятия с новыми размерами: это проверка повторного использования Knowledge, не неизвестных понятий. Точные reference matches: 4/40 → 30/40; exact equality не заменяет проверку смысла. Отдельная покейсная semantic review:', '',
        '| Статус | До / 40 | После / 40 |','|---|---:|---:|']
    for grade in ['PASS','MINOR','MAJOR','CATASTROPHIC']:
        lines.append(f"| {grade} | {holdout_summary['before'].get(grade,0)} | {holdout_summary['after'].get(grade,0)} |")
    lines += ['', 'У десяти свежих инструкций MAJOR+CATA: 5→3. При этом есть явная регрессия: «проверьте, не деформированы ли панели» превратилось в простую проверку панелей без условия деформации. Трещины и зазоры также передаются неточно; падежи иногда неправильны. Поэтому строгий gate «без semantic regressions» НЕ выполнен, а рост словаря не объявляется решением всех новых инструкций. Все source/before/after/reference/grades — holdout_semantic_review.json.', '',
        '## 13. Chinese residue: три причины','',
        f"A, перевода нет: {before['residue_A']} → {after['residue_A']}. B, перевод есть, но placement сохранил исходник: {before['residue_B']} → {after['residue_B']}. C, намеренный OCR noise: {before['residue_C']} → {after['residue_C']}.", '',
        'B выросло из-за более длинных правильных compound labels. PDF layout/OCR policy не менялись: длинный русский текст не втиснут поверх схемы ради цифры покрытия. Это ограничение опубликованного результата и tradeoff, а не переводческое отсутствие. Список каждого случая, причины и готовый перевод — before/after_residue.json.', '',
        '## 14. Время и процессы','',
        f"Тот же ZIP / ZH→RU / Auto: accepted job **{metrics['before']['job_seconds']:.2f} s → {metrics['after']['job_seconds']:.2f} s ({timing_change:+.2f}%)**. Wall с этапом сканирования: {metrics['before']['wall_seconds']:.2f} → {metrics['after']['wall_seconds']:.2f} s. Один новый прогон; строгий повторный benchmark не заявляется. Дисковый/Windows cache не очищался. Pipeline специально не оптимизировался.", '',
        '| Процесс, вложенные интервалы | До, s | После, s |','|---|---:|---:|']
    bt=read('before_timings.json');at=read('after_timings.json')
    for process in ['preflight_open_extract','engine_translation','document_write','archive_pack','archive_translate','archive_publish','archive_cleanup']:
        lines.append(f"| {process} | {sum(bt['processes'].get(process,[])):.3f} | {sum(at['processes'].get(process,[])):.3f} |")
    lines += ['', 'Это inclusive вложенные измерения; строки нельзя складывать в total. Все individual process durations сохранены в before/after_timings.json и штатных document-job logs.', '',
        '## 15. Размер базы','',f"{old['bytes']:,} → {new['bytes']:,} байт ({old['bytes']/1024:.0f} → {new['bytes']/1024:.0f} KiB). Прибавка {(new['bytes']-old['bytes'])/1024:.0f} KiB. SHA256 и per-type counts: base_before/after.json; production manifest обновлён. RU→ZH counterparts не создавались.", '',
        '## 16. Регрессия, компоненты и очистка scratch','',f"**{regression['tests']} passed, 0 failed/errors/skipped**. JUnit и compact regression.json сохранены. Targeted tests проверяют longest compound, phrase/exact, пользовательский приоритет/TM, numbers/parentheses, explicit aliases/punctuation, domain isolation, Russian patterns, четыре инструкции, unknown fallback, residue A/B/C, names/folders, pack checksum и отсутствие false substring/nested numbering. Существующие offline/source/collision/cancel/OCR/PDF/ZIP validators не ослаблены.", '',
        'Промежуточные regression failures: generated language-support snapshot содержал устаревшее число записей; source-key collector принял служебные русские grammar patterns за UI strings. Штатный генератор обновил counts без изменения статусов/звёзд/UX; grammar data вынесены в assets/config/automotive-grammar.json, локализация не ослаблена. После окончательной правки полный pytest повторён.', '',
        'Новых UI-компонентов, UI reworks или pipeline нет. Расширены существующие GlossaryEngine/matcher и structured exact Knowledge; типизированная review metadata хранится в notes существующей schema. Новые tools/tests относятся только к QA.', '',
        'Scratch: 38 файлов / 9 769 822 байт в build/aw085-quality инвентаризированы; их автоматическое удаление отклонено с «blocked by policy», файлы пока сохранены. Contact sheets и UI evidence уже скопированы в qa/aw085/visual. Эту папку пользователь может удалить целиком; final ZIP находится в output/aw085/accepted. Изолированные пустые QA lookup/run DBs также сохранены, пользовательские TM/glossary не затронуты.', '',
        '## 17. Acceptance и оставшиеся ограничения','',
        'Выполнено: AW0.8.4 weights удалены, production/resources/report/journal сохранены; приложение запущено; база существенно расширена; 133/133 semantic availability; 130/131 terminology concepts до placement; четыре инструкции исправлены; protected 419/419; OCR continuation/noise overlays 0; page inflation отсутствует; ZIP опубликован; full regression проходит.', '',
        '**Полный gate остаётся незакрытым:** semantic regression на одной свежей инструкции, три MAJOR на fresh prose, отдельные неправильные падежи; шесть неоднозначных component labels; 16 conservative placement preserves и неполные русские подписи в опубликованном PDF; scratch cleanup заблокирован. Поэтому релиз «все технические документы переводятся правильно» не заявляется. Положительный эффект Knowledge доказан для проверенных терминов/compound labels и устойчивых инструкций.', '',
        'AW0.8.5 остановлена после отчёта. Новый engine research, fine-tuning, installer, Language Support stars и performance rewrite не начинались. Коммит не создан.', '',
        f"Результат: `{path}`. SHA256: `{status['zip_sha256']}`. Метрики, gold/holdout, review, cleanup inventories и regression находятся в qa/aw085. Исходный AW0.8.3 gold сохранён без изменения; ссылки и translated segments не загружаются production для скрытого lookup.", '']
    (ROOT/'docs/AW0.8.5_KNOWLEDGE_EXPANSION_REPORT.md').write_text('\n'.join(lines),'utf-8')
    print('REPORT COMPLETE',regression,holdout_summary,status['decision'])

if __name__=='__main__':main()
