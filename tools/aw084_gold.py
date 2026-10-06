"""Freeze QA references before candidate outputs exist. Never imported by app."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'qa/aw084'


def main():
    gold = json.loads((ROOT/'qa/aw083/body_dimensions_gold.json').read_text('utf-8'))
    rows = []
    categories = ['negative', 'instruction', 'negative', 'general prose', 'projection',
                  'condition', 'technical explanation', 'measurement', 'measurement', 'negative']
    for i, case in enumerate(gold['semantic_review_cases']):
        sample = next(x for d in gold['documents'] for x in d['samples'] if x['source'] == case['source'])
        rows.append(dict(id=f'body-{i+1:02}', source_zh=case['source'], reference_ru=case['expected'],
                         category=categories[i], critical_meaning=case['expected'],
                         must_preserve=sample['protected_values'], allowed_variants=[],
                         provenance={'file': case['file'], 'block_id': sample['block_id'], 'kind': 'verbatim'},
                         suite='body'))
    # Literal source segments, not invented prose. Distinct drawings and dimensions
    # remain separate cases; prose/label statistics are reported separately.
    seen = {r['source_zh'] for r in rows}
    canonical = gold['canonical_terms']
    for document in gold['documents']:
        for sample in document['samples']:
            source = sample['source']
            if source in seen or not re.search('[\u4e00-\u9fff]', source):
                continue
            matches = [key for key in canonical if source.startswith(key)]
            if not matches or len(source) < 5:
                continue
            key = max(matches, key=len)
            # A partial head like 前门 is not a gold translation for its compound.
            suffix = source[len(key):]
            if re.search('[\u4e00-\u9fff]', suffix):
                continue
            reference = canonical[key] + suffix
            rows.append(dict(id=f'body-{len(rows)+1:02}', source_zh=source, reference_ru=reference,
                             category='technical explanation' if '。' in source else 'compound label',
                             critical_meaning=canonical[key], must_preserve=sample['protected_values'],
                             allowed_variants=[], provenance={'file': document['file'],
                                 'block_id': sample['block_id'], 'kind': 'verbatim'}, suite='body'))
            seen.add(source)
    # Existing independent authored project fixtures. References written before
    # any engine evaluation; derivatives explicitly separated from verbatim cases.
    refs = [
        'Техник открыл дверь.',
        'Она вчера проверила оба клапана? Не запускайте водяной насос.',
        'Запишите 123, 12.5, 1 250 и 5%. Предельные значения: −20 °C, 220 V и 42 mm. Проверьте 2026-09-28 в 14:30.',
        'Машина непрерывного литья остановилась из-за падения давления охлаждающей воды.',
        'Откройте config.json в C:\\Temp\\plant, затем выполните python main.py --help.',
        'Температура расплавленной стали составляет 1 560 °C, pressure 12 bar.',
        'Перед запуском проверьте CPU, USB и API.',
        'Предупреждение: остановитесь! Клапан открыт? Она ответила: «Нет».',
        'Прежде чем снова запустить остановившуюся ночью машину, техник проверил систему охлаждения, заменил повреждённый разъём и убедился, что аварийный выключатель не был нажат.',
        'Сохраните файл.\n\nПерезапустите приложение.\nПроверьте результат.',
        'Кран поднял стальную балку возле берега реки.',
        'Проверьте давление охлаждающей воды. Запишите давление охлаждающей воды. Не повышайте давление охлаждающей воды.'
    ]
    quality = [r for r in json.loads((ROOT/'docs/qa/aw08/quality-corpus.json').read_text('utf-8'))
               if r['source_language']=='zh' and r['target_language']=='ru']
    for case, reference in zip(quality, refs, strict=True):
        rows.append(dict(id=case['id'], source_zh=case['source'], reference_ru=reference,
                         category='general prose' if case['category']=='simple' else 'instruction',
                         critical_meaning=reference, allowed_variants=[], must_preserve=[], suite='independent',
                         provenance={'file':'docs/qa/aw08/quality-corpus.json','kind':'project-authored QA'}))
    pdf = json.loads((ROOT/'tests/fixtures/pdf/semantic-corpus.json').read_text('utf-8'))
    for case in pdf:
        rows.append(dict(id='coolant-'+case['id'],source_zh=case['source'],reference_ru=case['expected_core_meaning'],
                         category='condition' if case['id'] in {'warmup','connector'} else 'instruction',
                         critical_meaning=case['expected_core_meaning'],allowed_variants=[],must_preserve=[],suite='independent',
                         provenance={'file':'tests/fixtures/pdf/semantic-corpus.json','kind':'user-supplied local QA excerpt; not a redistributable corpus'}))
    for name, source, reference in [
        ('pressure','不要增加冷却水压力。','Не повышайте давление охлаждающей воды.'),
        ('switch','确认紧急开关没有被按下。','Убедитесь, что аварийный выключатель не был нажат.')]:
        rows.append(dict(id='clause-'+name,source_zh=source,reference_ru=reference,category='negative',
                         critical_meaning=reference,allowed_variants=[],must_preserve=[],suite='independent',
                         provenance={'file':'docs/qa/aw08/quality-corpus.json','kind':'explicit clause extraction from authored QA'}))
    document = {'purpose':'QA only; frozen before outputs; exact Knowledge bypass only in raw harness',
                'limitation':'Body corpus has ten instruction/review cases, not 40 unique prose sentences. Remaining verbatim cases are technical labels. No invented sentences represented as source.',
                'entries':rows}
    for filename in ('semantic_gold.json','engine_semantic_gold.json'):
        path=QA/filename
        if path.exists():
            raise RuntimeError('Do not overwrite a frozen gold corpus')
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n','utf-8')
    state=json.loads((QA/'frozen_state.json').read_text('utf-8'))
    for filename in ('semantic_gold.json','engine_semantic_gold.json'):
        state['files']['qa/aw084/'+filename]=hashlib.sha256((QA/filename).read_bytes()).hexdigest()
    (QA/'frozen_state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('FROZEN',len(rows),'body',sum(r['suite']=='body' for r in rows),'independent',sum(r['suite']=='independent' for r in rows))


if __name__ == '__main__':
    main()
