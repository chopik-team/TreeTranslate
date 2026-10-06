from dataclasses import replace
from test_aw081_duty_and_relations import engine,request
from app.knowledge.questions import features,violations

def test_display_same_code_is_state_question_not_command(engine):
 source='3. 显示相同的故障代码吗？'
 result=engine.lookup_direct(request(source,'diagnostics'))
 assert result and result.translated_text=='3. Отображается ли тот же код неисправности?'
 assert features(source).kind=='STATE_CHECK'
 assert 'question:display_state' in violations(source,'3. Показать тот же код неисправности?')
 assert 'question:same_relation' in violations(source,'3. Отображается ли другой код неисправности?')
 for changed in (source.replace('故障代码','未知代码'),source+'然后拆卸。'):
  assert engine.lookup_direct(request(changed,'diagnostics')) is None

def test_seven_inspection_conditions_are_kept_and_not_guessed(engine):
 source='彻底检查连接器的松动、连接不良、弯曲、腐蚀、污染、变质或损坏情况。'
 result=engine.lookup_direct(request(source,'diagnostics',kind='PROCEDURE_STEP'))
 assert result and result.translated_text==('Тщательно проверьте разъём на наличие ослабления, плохого контакта, изгиба, коррозии, загрязнения, ухудшения свойств или повреждения.')
 assert engine.lookup_direct(request(source.replace('变质','未知情况'),'diagnostics')) is None
 assert engine.lookup_direct(request(source,'engine')) is None

def test_clutch_caption_uses_existing_concept_and_preserves_literal_values(engine):
 req=request('离合器位置 F 13 ± 5','brakes',kind='DIAGRAM_LABEL')
 result=engine.lookup_direct(req)
 assert result and result.translated_text=='положение сцепления F 13 ± 5'
 assert 'см' not in result.translated_text
 assert engine.lookup_direct(replace(req,text='如果离合器位置 F 13 ± 5')) is None
