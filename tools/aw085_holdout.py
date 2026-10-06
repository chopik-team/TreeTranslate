"""Freeze independently authored examples, then compare old and new Knowledge."""
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw085_knowledge import QA,save
from tools.qa_aw083_quality import terms
from app.glossary.database import Database
from app.glossary.repository import Repository
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.engine import TranslationMemoryEngine
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest

LABELS='''前门锁安装孔\tОтверстие крепления замка передней двери
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
前门上铰链安装孔\tОтверстие крепления верхней петли передней двери
前门下铰链安装孔\tОтверстие крепления нижней петли передней двери
后门上铰链安装孔\tОтверстие крепления верхней петли задней двери
后门下铰链安装孔\tОтверстие крепления нижней петли задней двери
发动机舱加强板\tУсилительная панель моторного отсека
车门内板\tВнутренняя панель двери
车门外板\tНаружная панель двери
地板横梁\tПоперечина пола
车顶横梁\tПоперечина крыши
门槛加强板\tУсилительная панель порога
测量孔\tИзмерительное отверстие
测量点中心\tЦентр точки измерения
测量点间距\tРасстояние между точками измерения
孔中心距\tРасстояние между центрами отверстий
左右高度差\tРазница высот левой и правой сторон
前后高度差\tРазница высот передней и задней частей
探头调节长度\tРегулируемая длина измерительного наконечника
对角线尺寸\tРазмер по диагонали'''

PROSE='''请在维修前测量车身的对角线尺寸。\tПеред ремонтом измерьте размеры кузова по диагонали.
如果两个测量点不在同一平面上，应测量高度差。\tЕсли две точки измерения находятся в разных плоскостях, следует измерить разницу высот.
测量时必须避免卷尺扭曲。\tПри измерении необходимо избегать перекручивания рулетки.
不要将面板间隙作为孔中心距。\tНе принимайте зазор между панелями за расстояние между центрами отверстий.
更换车门后，检查上铰链和下铰链。\tПосле замены двери проверьте верхнюю и нижнюю петли.
左右测量点之间的距离必须相等。\tРасстояния между точками измерения слева и справа должны быть одинаковыми.
检查后副车架安装螺栓是否松动。\tПроверьте, не ослаблены ли крепёжные болты заднего подрамника.
不要弯曲测量工具的探头。\tНе сгибайте наконечник измерительного инструмента.
维修后应检查车身对称性。\tПосле ремонта следует проверить симметрию кузова.
先测量孔径，再测量孔中心距。\tСначала измерьте диаметр отверстия, затем расстояние между центрами отверстий.'''

FRESH_PROSE='''请检查车门内板和外板是否变形。\tПроверьте, не деформированы ли внутренняя и наружная панели двери.
测量孔中心距时，应保持两个探头的长度一致。\tПри измерении расстояния между центрами отверстий поддерживайте одинаковую длину обоих наконечников.
检查门槛加强板是否有裂纹。\tПроверьте, нет ли трещин в усилительной панели порога.
安装前检查螺栓和螺母。\tПеред установкой проверьте болты и гайки.
前门和后门的间隙应符合公差要求。\tЗазоры передней и задней дверей должны соответствовать требованиям допуска.
不要损坏安全带预紧器。\tНе повредите преднатяжитель ремня безопасности.
维修前应记录实际测量尺寸。\tПеред ремонтом следует записать фактически измеренные размеры.
测量后应比较左右高度差。\tПосле измерения следует сравнить разницу высот левой и правой сторон.
如果车身结构损坏，应停止测量。\tЕсли структура кузова повреждена, измерение следует прекратить.
确保座椅安装孔没有裂纹。\tУбедитесь, что в отверстии крепления сиденья нет трещин.'''

def main():
    fresh='--fresh' in sys.argv
    prefix='holdout_fresh' if fresh else 'holdout'
    cases=[]
    for i,line in enumerate(LABELS.splitlines()):
        s,t=line.split('\t');suffix=f' （Ø{(31 if fresh else 21)+i/10:.1f}）'
        cases.append(dict(id=f'label-{i+1:02}',source=s+suffix,reference=t+suffix,kind='novel_measurement_label',provenance='Authored AW0.8.5 independent case; unseen dimension and segment, shared technical concept'))
    for i,line in enumerate((FRESH_PROSE if fresh else PROSE).splitlines()):
        s,t=line.split('\t');cases.append(dict(id=f'prose-{i+1:02}',source=s,reference=t,kind='unseen_prose',provenance='Authored neutral automotive instruction, not a pack exact entry or source PDF excerpt'))
    save(prefix+'.json',dict(definition='30 unseen label+measurement combinations and 10 unseen prose; concepts overlap intentionally, prose separated; no pack additions after freeze',entries=cases))
    scratch=ROOT/'build/aw085-quality';scratch.mkdir(parents=True,exist_ok=True)
    old=scratch/'old-knowledge.db'
    Repository(Database(old)).insert_many(dict(source_term=s,target_term=t,source_language='zh',target_language='ru',domain='automotive',status='BUILTIN',origin='builtin',priority=100,source_pack='aw083-body-repair') for s,t in terms().items())
    results={}
    for mode in ['before','after']:
        paths=[old if p.name=='aw083-body-repair-zh-ru.db' and mode=='before' else p for p in bundled_paths()]
        e=create_translation_engine(memory=TranslationMemoryEngine(scratch/f'{mode}-tm.db'),glossary=GlossaryEngine(scratch/f'{mode}-glossary.db',builtin_paths=paths))
        rows=[]
        try:
            for c in cases:
                started=time.perf_counter();r=e.translate(TranslationRequest(c['source'],'zh','ru',domain='automotive'))
                rows.append(dict(c,output=r.translated_text,backend=r.backend,route=r.route_reason,duration=time.perf_counter()-started,
                    reference_exact=r.translated_text==c['reference']))
            results[mode]=rows
        finally:e.shutdown()
        save(prefix+'_results.json',results)
        print(mode,sum(r['reference_exact'] for r in rows),'exact /',len(rows),flush=True)

if __name__=='__main__':main()
