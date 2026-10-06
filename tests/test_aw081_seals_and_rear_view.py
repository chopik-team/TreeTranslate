"""Separate hydraulic components, scoped visibility and geometry continuations."""
import json
from pathlib import Path
from dataclasses import replace
import pytest
from test_aw081_duty_and_relations import engine,request
from app.documents.pdf_types import PdfSegment
from app.documents.pdf_layout import group_spans
from app.glossary.models import entry_metadata
ROOT=Path(__file__).resolve().parents[1]

def test_seal_and_boot_have_separate_concepts_from_master_cups(engine):
 req=engine.contextualize(request('制动钳活塞密封圈和活塞防尘罩','brakes',kind='TABLE_CELL'))
 result=engine.lookup_direct(req)
 assert result and result.translated_text=='Уплотнительное кольцо и пыльник поршня тормозного суппорта'
 concepts=[entry_metadata(req.knowledge_snapshot.exact[s][0][0])['concept_id'] for s in ('制动钳活塞密封圈','活塞防尘罩','活塞皮碗','润滑脂杯')]
 assert len(set(concepts))==4
 assert engine.lookup_direct(replace(req,text='制动钳活塞密封圈和活塞防尘 罩')).translated_text==result.translated_text
 assert engine.lookup_direct(replace(req,text='制动钳活塞密封圈和活塞防尘')) is None
 engine.router.translate.assert_not_called()

def test_whole_rear_view_block_preserves_two_visual_methods_and_both_times(engine):
 inventory=json.loads((ROOT/'qa/aw081/major_root_causes.json').read_text('utf8'))['rows']
 source=next(r for r in inventory if r['id']=='0:3')['native_layout_matches'][0]['text']
 result=engine.lookup_direct(request(source,'adas',kind='WARNING'))
 assert result and 'только для помощи водителю' in result.translated_text
 assert 'До начала и во время движения задним ходом' in result.translated_text
 assert 'постоянно контролировать пространство позади автомобиля непосредственно визуально и с помощью внутреннего и наружных зеркал' in result.translated_text
 assert 'камера не обнаруживает' in result.translated_text
 for changed in (source.replace('驾驶员','乘客'),source.replace('直观和','直观或'),source.replace('不能通过','可以通过')):
  assert engine.lookup_direct(request(changed,'adas',kind='WARNING')) is None
 engine.router.translate.assert_not_called()

def test_direct_visual_observation_not_a_global_prose_replacement(engine):
 for branch,text in [('engine','直观检查发动机'),('adas','直观检查标志')]:
  req=engine.contextualize(request(text,branch))
  matches=engine.glossary.lookup(text,'zh','ru','automotive',snapshot=req.knowledge_snapshot,request=req)
  safe=engine.glossary.sentence_safe_matches(text,matches)
  assert not any(m.entry.source_term=='直观' for m in safe)

def test_rvm_display_ecm_is_a_functional_mirror_not_engine_control_or_coating(engine):
 source='此系统是辅助系统,倒车时通过音频/视频显示器或ECM(倒车显示室内后视镜)显示车辆后方状况。'
 result=engine.lookup_direct(request(source,'adas'))
 assert result and 'при движении задним ходом' in result.translated_text
 assert 'на аудио-/видеомониторе или на ECM (внутреннем зеркале заднего вида с дисплеем камеры заднего вида)' in result.translated_text
 assert 'электрохром' not in result.translated_text
 assert engine.lookup_direct(request(source,'engine')) is None
 assert engine.lookup_direct(request(source.replace('ECM','PCM'),'adas')) is None
 engine.router.translate.assert_not_called()

def test_actual_rvm_header_activation_and_display_share_one_complete_block(engine):
 from app.documents.pdf_document import PdfDocument
 source=PdfDocument(ROOT/'qa/aw081/diagnostic/originals/0.pdf').segments[0].text
 result=engine.lookup_direct(request(source,'adas',kind='HEADING'))
 # A physical heading region may include two full sentences; the job's
 # heading classification must permit these verified complete clauses.
 assert result and 'ON' in result.translated_text and 'в положении R' in result.translated_text
 assert 'дисплеем камеры заднего вида' in result.translated_text
 for changed in (source+'未知过程。',source[:-1],source.replace('说明','未知标题',1)):
  assert engine.lookup_direct(request(changed,'adas',kind='HEADING')) is None

def test_booster_conditional_replacement_preserves_both_objects(engine):
 source='制动,并检查在试验运转期间的操作情况。如果不能正常工作,请更换制动助力器。如果在分解 助力器时发现内部有制动液,则更换助力器和制动总缸。'
 result=engine.lookup_direct(request(source,'brakes'))
 assert result and 'во время пробной поездки' in result.translated_text
 assert 'при разборке усилителя тормозов' in result.translated_text
 assert result.translated_text.endswith('замените усилитель тормозов и главный тормозной цилиндр.')
 assert engine.lookup_direct(request(source[:-1],'brakes')) is None

def test_four_whole_cup_clauses_keep_conditions_without_neighbour_borrowing(engine):
 source='• 进行制动,检查其工作。检查是否有任何损坏或机油泄漏。如果工作不正常或损坏或发现漏 油,则更换制动总缸。如果在助力器内部发现制动液,则还要更换助力器。'
 result=engine.lookup_direct(request(source,'brakes'))
 assert result and result.translated_text.startswith('• Нажмите педаль тормоза')
 assert 'утечки тормозной жидкости' in result.translated_text
 assert 'ненормальной работе' in result.translated_text
 assert 'также замените усилитель тормозов' in result.translated_text
 for changed in (source+'进行制动,检查其工作。',source+'未知过程。',source[:-1]):
  assert engine.lookup_direct(request(changed,'brakes')) is None

def span(text,x,y,size,region=(100,500,140),kind='warning',order=0):
 return PdfSegment(0,str(order),text,(x,y,x+70,y+8),order,('test',),size,baseline=y+1,
   object_indices=(order,),region_key=region,region_kind=kind)

def test_hanging_cjk_continuation_merges_only_in_same_enclosed_cell():
 first=span('• 检查发现漏',10,120,11.4,order=1)
 second=span('油,则更换制动总缸。',16,108,9.6,order=2)
 next_item=span('• 下一项目。',10,96,11.4,order=3)
 blocks=group_spans(0,[first,second,next_item],4000)
 assert [b.text for b in blocks]==['• 检查发现漏 油,则更换制动总缸。','• 下一项目。']
 assert blocks[0].object_indices==(1,2)

@pytest.mark.parametrize('kind,region,text',[('warning',(88,500,100),'油'),('table_cell',(100,80,140),'油'),('paragraph',(100,500,140),'油')])
def test_continuation_cannot_cross_cell_or_region_kind(kind,region,text):
 blocks=group_spans(0,[span('• 检查发现漏',10,120,11.4,order=1),span(text,16,108,9.6,region,kind,2)],4000)
 assert len(blocks)==2

def test_completed_bullet_and_ordinary_paragraph_keep_font_boundary():
 for text,kind in [('• 完整说明。','warning'),('普通说明','paragraph')]:
  blocks=group_spans(0,[span(text,10,120,11.4,kind=kind,order=1),span('下一行',16,108,9.6,kind=kind,order=2)],4000)
  assert len(blocks)==2
