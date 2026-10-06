"""Approved OEM senses and conservative command/condition composition."""
from dataclasses import replace
import pytest
from test_aw081_duty_and_relations import engine, request

def test_compare_pedal_travel_is_not_speed_or_piston_stroke(engine):
 source='• 检查快速制动和缓慢制动时,制动行程是否有区别。如果检测到差异,则更换制动总缸。'
 result=engine.lookup_direct(request(source,'brakes'))
 assert result and result.translated_text=='• Сравните ход педали тормоза при быстром нажатии педали тормоза и медленном нажатии педали тормоза. Если обнаружено различие, замените главный тормозной цилиндр.'
 assert engine.lookup_direct(request(source.replace('快速制动','缓慢制动').replace('缓慢制动时','快速制动时'),'brakes'))
 for changed in (source.replace('快速制动','未知操作'),source.replace('检测到差异','没有差异'),source[:-1],source+'执行未知动作。'):
  assert engine.lookup_direct(request(changed,'brakes')) is None
 engine.router.translate.assert_not_called()

def test_test_run_is_scoped_to_brake_booster(engine):
 source='制动助力器 (A) 制动,并检查在试验运转期间的操作情况。如果不能正常工作,请更换制动助力器。'
 result=engine.lookup_direct(request(source,'brakes'))
 assert result and 'Усилитель тормозов (A)\nНажмите педаль тормоза' in result.translated_text
 assert 'во время пробной поездки' in result.translated_text
 assert 'не работает нормально' in result.translated_text
 assert engine.lookup_direct(request(source+'如果在分解','brakes')) is None
 req=engine.contextualize(request('试验运转期间','engine',kind='DIAGRAM_LABEL'))
 assert not engine.glossary.lookup(req.text,'zh','ru','automotive',snapshot=req.knowledge_snapshot,request=req)

def test_hose_label_is_not_the_actor_and_washer_is_plain(engine):
 source='制动软管(C) 检查是否有任何损坏或机油泄漏。如果存在损坏或发现漏油,则更换新的制动软管和垫圈。'
 result=engine.lookup_direct(request(source,'brakes'))
 assert result and result.translated_text=='Тормозной шланг (C)\nПроверьте наличие повреждения или утечки тормозной жидкости. При наличии повреждения или обнаружении утечки тормозной жидкости замените тормозной шланг и шайбу новыми.'
 assert engine.lookup_direct(request(source.replace('垫圈','未知件'),'brakes')) is None
 assert engine.lookup_direct(request(source.replace('(C)','(D)'),'brakes')).translated_text.startswith('Тормозной шланг (D)')

def test_caliper_drag_is_not_slip_and_fault_relation_survives(engine):
 source='• 如果制动踏板工作不正常,则表示存在制动打滑、损坏或漏油。用新的制动钳更换。'
 result=engine.lookup_direct(request(source,'brakes'))
 assert result and 'работает ненормально' in result.translated_text
 assert 'указывает на подтормаживание, повреждение или утечку тормозной жидкости' in result.translated_text
 assert result.translated_text.endswith('Замените тормозной суппорт новым.')
 assert engine.lookup_direct(request(source.replace('工作不正常','工作正常'),'brakes')) is None

def test_swash_plate_rotation_drives_reciprocating_piston(engine):
 source='压缩机配备旋转斜盘,旋转时使得活塞往复运动,以此压缩制冷剂。'
 result=engine.lookup_direct(request(source,'hvac'))
 assert result and 'наклонным диском' in result.translated_text
 assert 'возвратно-поступательное движение поршня' in result.translated_text
 assert 'сжатия хладагента' in result.translated_text
 assert engine.lookup_direct(request(source.replace('活塞往复运动','活塞不运动'),'hvac')) is None

def test_external_compressor_signal_controls_angle_with_ecv(engine):
 source='外部控制的可变旋转斜盘压缩机通过ECV（电动控制阀）,根据加热器与空调控制单元的电信号,改变旋转斜盘的角度。'
 result=engine.lookup_direct(request(source,'hvac'))
 assert result and 'изменяет угол наклонного диска с помощью ECV' in result.translated_text
 assert 'электрическим сигналом блока управления отопителем и кондиционером' in result.translated_text
 assert engine.lookup_direct(request(source.replace('ECV','ABC'),'hvac')) is None
 assert engine.lookup_direct(request(source.replace('加热器与空调控制单元','未知控制单元'),'hvac')) is None
 engine.router.translate.assert_not_called()

def test_master_cylinder_alias_reuses_existing_concept(engine):
 req=engine.contextualize(request('制动总缸','brakes',kind='COMPONENT_LABEL'))
 old=req.knowledge_snapshot.exact['制动主缸'][0][0]
 new=req.knowledge_snapshot.exact['制动总缸'][0][0]
 assert old.id==new.id
 assert engine.lookup_direct(req).translated_text=='главный тормозной цилиндр'
