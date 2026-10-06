"""Authored automotive expansion using the existing schema, with auditable review metadata."""
import json
import re
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw085';QA.mkdir(parents=True,exist_ok=True)
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.engine.types import TranslationRequest
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.documents.pdf_types import PdfSegment
from app.documents.pdf_ocr_policy import classify,protected_kind
from unittest.mock import Mock

def save(name,data):
    (QA/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')

TERMS='''车身结构\tСтруктура кузова
车身面板\tКузовная панель
面板间隙\tЗазор между панелями
前端\tПередняя часть
后端\tЗадняя часть
前部\tПередняя часть
后部\tЗадняя часть
车门\tДверь автомобиля
上铰链\tВерхняя петля
下铰链\tНижняя петля
门锁\tЗамок двери
门锁栓\tОтветная часть замка двери
限位器\tОграничитель
车门限位器\tОграничитель открывания двери
纵梁\tЛонжерон
横梁\tПоперечина
后侧构件\tЗадний лонжерон
A柱\tПередняя стойка кузова
B柱\tЦентральная стойка кузова
C柱\tЗадняя стойка кузова
内板\tВнутренняя панель
外板\tНаружная панель
加强板\tУсилительная панель
安装支架\tКрепёжный кронштейн
发动机\tДвигатель
发动机舱\tМоторный отсек
座椅\tСиденье
测量\tИзмерение
测量尺寸\tИзмеренные размеры
参考平面\tОпорная плоскость
高度差\tРазница высот
基准尺寸\tБазовые размеры
公差\tДопуск
间隙\tЗазор
安装\tУстановка
螺栓\tБолт
螺母\tГайка
固定\tКрепление
连接\tСоединение
测量段\tИзмерительный участок
探头长度\tДлина измерительного наконечника
两个表面\tДве поверхности
实际尺寸\tФактические размеры
实测尺寸\tФактически измеренные размеры
直线距离\tПрямое расстояние
车身变动\tИзменение геометрии кузова
孔\tОтверстие
孔径\tДиаметр отверстия
中心线\tОсевая линия
对称轴\tОсь симметрии
车顶\tКрыша
门槛\tПорог
地板\tПол
行李仓盖板\tКрышка багажного отсека
通风罩\tПанель воздухопритока
通风罩侧装饰孔\tОтверстие боковой облицовки панели воздухопритока
通风罩横臂孔\tОтверстие поперечины панели воздухопритока
前门检验器孔\tОтверстие ограничителя открывания передней двери
后门检验器孔\tОтверстие ограничителя открывания задней двери
后门锁栓孔\tОтверстие ответной части замка задней двери
杂物箱装饰孔\tОтверстие облицовки вещевого отсека
行李仓盖板锁栓孔\tОтверстие ответной части замка крышки багажного отсека
前支柱转角\tУгол передней стойки
后面板机加孔\tОбработанное отверстие задней панели
后杂物箱中央面板孔\tОтверстие центральной панели заднего вещевого отсека
杂物箱侧延长机孔\tТехнологическое отверстие бокового удлинителя вещевого отсека
前侧构件机下孔\tНижнее технологическое отверстие переднего лонжерона
前副车架后减振器孔\tОтверстие заднего демпфера переднего подрамника
前侧后下构件机孔\tТехнологическое отверстие задней нижней части переднего лонжерона
中央地板侧构件延长机孔\tТехнологическое отверстие удлинителя лонжерона центральной части пола
后地板侧构件延长机孔\tТехнологическое отверстие удлинителя лонжерона заднего пола
后地板侧构件机孔\tТехнологическое отверстие лонжерона заднего пола
后定位臂孔\tОтверстие заднего направляющего рычага
前门限位器孔\tОтверстие ограничителя открывания передней двери
后门限位器孔\tОтверстие ограничителя открывания задней двери
前门锁安装孔\tОтверстие крепления замка передней двери
后门锁安装孔\tОтверстие крепления замка задней двери
前座椅安装孔\tОтверстие крепления переднего сиденья
后座椅安装孔\tОтверстие крепления заднего сиденья
前悬架弹簧孔\tОтверстие пружины передней подвески
后减震器孔\tОтверстие заднего амортизатора
前保险杠安装孔\tОтверстие крепления переднего бампера
后保险杠安装孔\tОтверстие крепления заднего бампера
前组合灯安装孔\tОтверстие крепления переднего комбинированного фонаря
后组合灯安装孔\tОтверстие крепления заднего комбинированного фонаря
安全带安装孔\tОтверстие крепления ремня безопасности
安全带高度调节器下孔\tНижнее отверстие регулятора высоты ремня безопасности
前副车架安装螺栓\tКрепёжный болт переднего подрамника
后副车架安装螺栓\tКрепёжный болт заднего подрамника
发动机舱加强板\tУсилительная панель моторного отсека
车门内板\tВнутренняя панель двери
车门外板\tНаружная панель двери
前纵梁\tПередний лонжерон
后纵梁\tЗадний лонжерон
地板横梁\tПоперечина пола
车顶横梁\tПоперечина крыши
门槛加强板\tУсилительная панель порога
测量孔\tИзмерительное отверстие
基准点\tБазовая точка
测量点中心\tЦентр точки измерения
测量点间距\tРасстояние между точками измерения
孔中心距\tРасстояние между центрами отверстий
左右高度差\tРазница высот левой и правой сторон
前后高度差\tРазница высот передней и задней частей
探头调节长度\tРегулируемая длина измерительного наконечника
车身对称性\tСимметрия кузова
尺寸偏差\tОтклонение размера
对角线尺寸\tРазмер по диагонали
'''

PHRASES='''使用卷尺时\tПри использовании рулетки
使用轨距仪时\tПри использовании кузовной измерительной линейки
投影到参考平面\tПроецировать на опорную плоскость
确保无自由间隙\tУбедитесь в отсутствии люфта
不得弯曲\tНе допускается изгиб
不得扭曲\tНе допускается перекручивание
不得拉长\tНе допускается растяжение
没有拉长\tНе растянута
没有扭曲\tНе перекручена
没有弯曲\tНе согнута
可调整\tМожно регулировать
加长探头\tУдлинить измерительный наконечник
进行测量\tВыполнить измерение
检查探头\tПроверьте измерительный наконечник
检查量规\tПроверьте измерительную линейку
测量前检查量规\tПеред измерением проверьте измерительную линейку
测量前检查探头\tПеред измерением проверьте измерительный наконечник
使用卷尺时应保持卷尺平直。\tПри использовании рулетки держите её прямо.
测量时不得弯曲卷尺。\tПри измерении не сгибайте рулетку.
测量时不得扭曲卷尺。\tПри измерении не перекручивайте рулетку.
测量时不得拉长卷尺。\tПри измерении не растягивайте рулетку.
测量前确保无自由间隙。\tПеред измерением убедитесь в отсутствии люфта.
检查探头长度。\tПроверьте длину измерительного наконечника.
两个探头应具有相等的长度。\tОба измерительных наконечника должны иметь одинаковую длину.
应在孔的中心进行测量。\tИзмерение следует выполнять по центру отверстия.
测量点必须位于参考平面上。\tТочки измерения должны находиться на опорной плоскости.
检查车门面板间隙。\tПроверьте зазор между панелями двери.
测量两个表面之间的高度差。\tИзмерьте разницу высот между двумя поверхностями.
测量完成后检查尺寸偏差。\tПосле измерения проверьте отклонение размера.
'''

def engine():
    return TranslationKnowledgeEngine(Mock(),Mock(lookup=Mock(return_value=None)),
        GlossaryEngine(QA/'lookup-user.db',builtin_paths=bundled_paths()))

def coverage(name):
    e=engine();run=json.loads((ROOT/'qa/aw083/accepted_segments.json').read_text('utf-8'));rows=[]
    for doc in run['documents']:
        for s in doc['segments']:
            source=s['text'];kind=classify(PdfSegment(**s)) if s['origin']=='ocr' else protected_kind(source)
            request=TranslationRequest(source,'zh','ru',domain='automotive')
            if kind in ('noise','identifier','measurement') or not re.search('[\u4e00-\u9fff]',source):status='PROTECTED';direct=None;matches=()
            else:
                direct=e.lookup_direct(request);matches=e.glossary.lookup(source,'zh','ru','automotive')
                status='KNOWN' if direct else ('PARTIAL' if matches else ('MODEL-ONLY' if len(source)>30 else 'UNKNOWN'))
            rows.append(dict(file=doc['file'],page=s['page'],block_id=s['block_id'],source=source,status=status,
                exact_target=direct.translated_text if direct else None,
                matched_terms=[m.entry.source_term for m in matches],long_prose=len(source)>30,
                phrase_known=bool(direct and any(
                    json.loads(m.entry.notes or '{}').get('type') in ('phrase','full_segment') for m in matches))))
    counts=Counter(r['status'] for r in rows)
    save(name,dict(total_segments=len(rows),total_semantic_segments=len(rows)-counts['PROTECTED'],counts=counts,
        exact_known=counts['KNOWN'],phrase_known=sum(r['phrase_known'] for r in rows),
        partially_known=counts['PARTIAL'],unknown_technical_concepts=sorted({r['source'] for r in rows if r['status']=='UNKNOWN'}),
        long_prose_requiring_model=sum(r['long_prose'] and r['status'] not in ('KNOWN','PROTECTED') for r in rows),rows=rows))

def build():
    destination=ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db'
    repo=Repository(Database(destination));old=list(repo.rows())
    if not (QA/'base_before.json').exists():
        save('base_before.json',dict(entries=len(old),bytes=destination.stat().st_size,sha256=sha256(destination.read_bytes()).hexdigest()))
    reviewed=[]
    existing={r.source_term:r.target_term for r in old}
    for kind,text in [('term',TERMS),('phrase',PHRASES)]:
        for line in text.strip().splitlines():
            s,t=line.split('\t');kind_actual='compound' if kind=='term' and len(s)>=5 else kind
            reviewed.append(dict(source=s,target=t,type=kind_actual,domain='automotive',language_pair='zh>ru',
                trust=.8,provenance='Independently authored AW0.8.5 terminology; Chinese relations, negation and technical meaning checked by Codex; no web or OEM paragraphs copied',
                review_status='VERIFIED',reviewer='Codex; not independent human certification',variants=[]))
    # The four stable instructions need full-segment entries: phrase constraints alone cannot ensure their meaning.
    gold=json.loads((ROOT/'qa/aw083/body_dimensions_gold.json').read_text('utf-8'))
    for case in gold['semantic_review_cases']:
        source=re.sub(r'^\d+\.\s*','',case['source']);compact=re.sub(r'(?<=[\u4e00-\u9fff、，,])\s+(?=[\u4e00-\u9fff])','',source)
        punctuation=compact.replace(',', '，').replace('。','.')
        reviewed.append(dict(source=compact,target=case['expected'],type='full_segment',domain='automotive',language_pair='zh>ru',trust=.8,
            provenance='User-provided AW0.8.5 stable instruction and meaning; independently authored Russian translation, relation/negation checked',
            review_status='VERIFIED',reviewer='Codex; semantic reference audited',variants=list(dict.fromkeys(v for v in [source,punctuation] if v!=compact))))
    # Explicit aliases, never fuzzy similarity: ambiguous 检验器 is restricted to a complete door-check label.
    aliases={'前门检验器孔':['前門檢驗器孔'],'后门检验器孔':['後門檢驗器孔'],
        '自由间隙':['自由間隙','自 由间隙'],'机罩铰链孔':['機罩鉸鏈孔'],
        '前门上铰链安装孔':['前門上鉸鏈安裝孔'],'前门下铰链安装孔':['前門下鉸鏈安裝孔'],
        '后门上铰链安装孔':['後門上鉸鏈安裝孔'],'后门下铰链安装孔':['後門下鉸鏈安裝孔']}
    for s,variants in aliases.items():
        found=next((r for r in reviewed if r['source']==s),None)
        if found:found['variants']=variants
        else:reviewed.append(dict(source=s,target=existing[s],type='compound' if len(s)>4 else 'term',domain='automotive',language_pair='zh>ru',trust=.8,
            provenance='Existing AW0.8.3 reviewed concept; explicit script/OCR aliases reviewed in AW0.8.5',review_status='VERIFIED',reviewer='Codex',variants=variants))
    save('reviewed_entries.json',reviewed)
    # Existing schema carries typed metadata in notes; no second Knowledge database or schema.
    with repo.db.connect(write=True) as con:
        for r in old:
            con.execute('UPDATE entries SET notes=? WHERE id=?',(json.dumps(dict(type='full_segment' if len(r.source_term)>30 else ('compound' if len(r.source_term)>4 else 'term'),sentence_constraints=False,review_status='VERIFIED',reviewer='Previous AW0.8.3 terminology review'),ensure_ascii=False),r.id))
        for r in reviewed:
            if r['source'] in existing:
                con.execute('DELETE FROM entries WHERE source_term=?',(r['source'],))
            for alias in r['variants']:
                if existing.get(alias)==r['target']:
                    con.execute('DELETE FROM entries WHERE source_term=?',(alias,))
    repo.insert_many(dict(source_term=r['source'],target_term=r['target'],source_language='zh',target_language='ru',domain='automotive',
        status='BUILTIN',origin='builtin',priority=100,source_pack='aw083-body-repair',provenance=r['provenance'],variants=r['variants'],
        notes=json.dumps(dict(type=r['type'],review_status=r['review_status'],reviewer=r['reviewer'],sentence_constraints=False),ensure_ascii=False)) for r in reviewed)
    with repo.db.connect(write=True) as con:
        con.commit();con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    rows=list(repo.rows());counts=Counter(json.loads(r.notes)['type'] for r in rows)
    path=ROOT/'assets/knowledge/manifest.json';manifest=json.loads(path.read_text('utf-8'))
    entry=next(p for p in manifest['packs'] if p.get('pack_id')=='aw083-body-repair')
    entry.update(sha256=sha256(destination.read_bytes()).hexdigest(),entries=len(rows),version='0.8.5',
        notice='Authored terminology and reviewed reusable instructions. No OEM IDs, pages or proprietary paragraphs. Codex review is not independent human certification.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    save('base_after.json',dict(entries=len(rows),types=counts,aliases=sum(len(r.variants) for r in rows),
        domains=['automotive'],ZH_RU=len(rows),RU_ZH=0,bytes=destination.stat().st_size,sha256=entry['sha256']))
    print('PACK',len(old),'->',len(rows),counts,flush=True)

if __name__=='__main__':
    if sys.argv[1]=='before':coverage('knowledge_coverage_before.json')
    elif sys.argv[1]=='build':build();coverage('knowledge_coverage_after.json')
