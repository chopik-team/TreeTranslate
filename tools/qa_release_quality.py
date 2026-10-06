"""Original small AW0.8 corpus: deterministic invariants, not an academic quality score."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import socket
import sys
from time import perf_counter
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CATEGORIES = ['simple','grammar','numbers','technical','software','mixed','abbreviations',
              'punctuation','long-sentence','paragraphs','ambiguous','repeatability']
TEXTS = {
    'en': ['The technician opened the door.', 'Did she check both valves yesterday? Do not start the pump.',
           'Record 123, 12.5, 1 250 and 5%. The limits are −20 °C, 220 V and 42 mm. Inspect on 2026-09-28 at 14:30.',
           'The continuous casting machine stopped because the cooling water pressure dropped.',
           r'Open config.json in C:\Temp\plant and run python main.py --help.',
           'The steel temperature is 1 560 °C, pressure 12 bar.', 'Check the CPU, USB and API before startup.',
           'Warning: stop! Is the valve open? "No," she replied.',
           'Before restarting the machine that stopped during the night, the technician checked the cooling system, replaced the damaged connector and confirmed that the emergency switch was not pressed.',
           'Save the file.\n\nRestart the application.\nCheck the result.',
           'The crane lifted a steel beam near the river bank.',
           'Check the cooling water pressure. Record the cooling water pressure. Do not increase the cooling water pressure.'],
    'ru': ['Техник открыл дверь.', 'Она проверила оба клапана вчера? Не запускайте насос.',
           'Запишите 123, 12.5, 1 250 и 5%. Пределы: −20 °C, 220 V и 42 mm. Проверка 2026-09-28 в 14:30.',
           'Машина непрерывного литья остановилась из-за падения давления охлаждающей воды.',
           r'Откройте config.json в C:\Temp\plant и выполните python main.py --help.',
           'Температура стали 1 560 °C, pressure 12 bar.', 'Проверьте CPU, USB и API перед запуском.',
           'Внимание: стоп! Клапан открыт? «Нет», — ответила она.',
           'Перед повторным запуском машины, остановившейся ночью, техник проверил систему охлаждения, заменил повреждённый разъём и убедился, что аварийный выключатель не нажат.',
           'Сохраните файл.\n\nПерезапустите приложение.\nПроверьте результат.',
           'Кран поднял стальную балку у берега реки.',
           'Проверьте давление охлаждающей воды. Запишите давление охлаждающей воды. Не повышайте давление охлаждающей воды.'],
    'zh': ['技术员打开了门。', '她昨天检查了两个阀门吗？不要启动水泵。',
           '记录123、12.5、1 250和5%。限值为−20 °C、220 V和42 mm。请于2026-09-28的14:30检查。',
           '连铸机因冷却水压力下降而停止。', r'打开C:\Temp\plant中的config.json，然后运行python main.py --help。',
           '钢水温度为1 560 °C，pressure 12 bar。', '启动前检查CPU、USB和API。',
           '警告：停止！阀门打开了吗？她回答：“没有。”',
           '重新启动夜间停止的机器之前，技术员检查了冷却系统，更换了损坏的连接器，并确认紧急开关没有被按下。',
           '保存文件。\n\n重新启动应用程序。\n检查结果。',
           '起重机在河岸附近吊起一根钢梁。', '检查冷却水压力。记录冷却水压力。不要增加冷却水压力。'],
}
NOTES = {
    'grammar': 'Question refers to yesterday and BOTH valves; pump start is forbidden, not requested.',
    'technical': 'Continuous casting machine stopped; cause is falling COOLING WATER PRESSURE, not temperature.',
    'ambiguous': 'Crane is lifting equipment, not a bird; bank means river bank, not a financial institution.',
    'repeatability': 'Cooling water pressure repeated consistently; final instruction prohibits increasing it.',
    'long-sentence': 'Keep chronology, replacement of damaged connector and NEGATED emergency-switch state.',
}


def corpus():
    cases = []
    for source, target in [('en','ru'),('ru','en'),('zh','ru'),('ru','zh'),('en','zh'),('zh','en')]:
        for category, text in zip(CATEGORIES, TEXTS[source]):
            cases.append({'id': f'{source}-{target}-{category}', 'source_language': source,
                          'target_language': target, 'category': category, 'source': text,
                          'reference_notes': NOTES.get(category, 'Preserve the stated facts, negation and structural content; wording may vary.')})
    samples = {'de': 'Starten Sie die Pumpe nicht, bevor das Ventil geöffnet ist.',
               'es': 'No arranque la bomba antes de abrir la válvula.',
               'fr': 'Ne démarrez pas la pompe avant que la vanne soit ouverte.',
               'ja': 'バルブを開く前にポンプを始動しないでください。'}
    for language, text in samples.items():
        for source, target, value in [('en',language,'Do not start the pump before the valve is open.'), (language,'en',text)]:
            cases.append({'id':f'{source}-{target}-sanity','source_language':source,'target_language':target,
                          'source':value,'category':'release-sanity','reference_notes':'Do NOT start pump until valve is open; preserve negation and temporal condition.'})
    return cases


def numeric_atoms(text):
    text = unicodedata.normalize('NFKC', text).replace('−','-')
    text = re.sub(r'(?<=\d)[ \u00a0\u202f](?=\d{3}(?:\D|$))', '', text)
    text = re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))', '', text)
    return Counter(re.findall(r'(?<!\d)-?\d+(?:[.,]\d+)?', text.replace(',', '.')))


def hard_checks(case, output):
    source = case['source']
    checks = {'nonempty': bool(output.strip()), 'no_model_tokens': not re.search(r'<unk>|</?s>|__[a-z]{2,3}__|\ufffd',output),
              'unicode_valid': not any(0xD800 <= ord(c) <= 0xDFFF for c in output),
              'no_control_chars': not any(ord(c)<32 and c not in '\n\r\t' for c in output),
              'bounded_length': len(output) <= max(100, len(source)*8),
              'no_runaway_repetition': not re.search(r'(.{8,80}?)(?:\s*\1){5,}',output)}
    if case['category'] in ('numbers','mixed'):
        checks['numbers_preserved'] = numeric_atoms(source) == numeric_atoms(output)
        # Language-specific unit spelling is acceptable; each unit is checked independently.
        for unit, pattern in [('temperature',r'°\s*[CcСс]|摄氏|градус'),('voltage',r'\b[VvВв]\b|伏|вольт'),
                              ('length',r'\bmm\b|\bмм\b|毫米|миллиметр'),('percent',r'%|百分|процент'),('pressure',r'bar|бар')]:
            if re.search(pattern, source):
                checks['unit_'+unit] = bool(re.search(pattern, output))
    if case['category']=='software':
        for token in ['config.json',r'C:\Temp\plant','python','main.py','--help']:
            checks['protected_'+token] = token in output
    if case['category']=='abbreviations':
        checks['abbreviations'] = all(x in output for x in ('CPU','USB','API'))
    if case['category']=='paragraphs':
        checks['paragraph_separators'] = re.findall(r'\n+',source) == re.findall(r'\n+',output)
    if case['category']=='grammar':
        negative = {'ru':r'не\s+(?:запуск|включ|начина|старт)', 'en':r"do not|don't|not to",
                    'zh':r'不要|不得|别'}[case['target_language']]
        checks['pump_prohibition_present'] = bool(re.search(negative,output,re.I))
    script = {'ru':r'[А-Яа-я]', 'zh':r'[\u4e00-\u9fff]', 'ja':r'[\u3040-\u30ff\u4e00-\u9fff]'}.get(case['target_language'])
    if script:
        checks['target_script_present'] = bool(re.search(script,output))
    return checks


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['baseline','final'],required=True);args=parser.parse_args()
    qa=ROOT/'docs/qa/aw08';qa.mkdir(parents=True,exist_ok=True)
    os.environ['TREETRANSLATE_TM_PATH']=str(ROOT/'build/aw08/qa-tm.db')
    os.environ['TREETRANSLATE_GLOSSARY_PATH']=str(ROOT/'build/aw08/qa-glossary.db')
    from app.engine.factory import create_translation_engine
    from app.engine.types import TranslationRequest,DevicePreference,PerformanceProfile
    attempts=[]
    def blocked(*a,**k):
        attempts.append(True);raise RuntimeError('QA blocked network')
    socket.getaddrinfo=blocked;socket.create_connection=blocked
    engine=create_translation_engine();results=[]
    cases=corpus()
    (qa/'quality-corpus.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        for case in cases:
            row=dict(case,profile='balanced');start=perf_counter()
            try:
                result=engine.translate(TranslationRequest(case['source'],case['source_language'],case['target_language'],DevicePreference.GPU,PerformanceProfile.BALANCED))
                row.update(output=result.translated_text,backend=result.backend,route=result.route_reason,fallback=result.fallback_used,
                           checks=hard_checks(case,result.translated_text),semantic_review='NEEDS REVIEW')
                row['hard_pass']=all(row['checks'].values())
            except Exception as error:
                row.update(output='',error_type=type(error).__name__,hard_pass=False,checks={'completed':False})
            row['latency_ms']=(perf_counter()-start)*1000
            results.append(row)
            (qa/f'translation-quality-{args.phase}.json').write_text(json.dumps({'phase':args.phase,'network_attempts':len(attempts),'cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
            print(row['id'],row['hard_pass'],flush=True)
    finally:engine.shutdown()


if __name__=='__main__':main()
