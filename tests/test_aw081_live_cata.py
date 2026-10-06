"""Known diagnostic failures plus independent relation and rejection boundaries."""
from test_aw081_duty_and_relations import engine, request
from app.knowledge.safety import violations
import pytest

@pytest.mark.parametrize('source,branch,required',[
    ('2. 将千斤顶安装到油盘边缘处','engine',('домкрат','у края масляного поддона')),
    ('7. 将千斤顶安装到变速驱动桥下来支撑。','engine',('домкрат','под коробкой передач с главной передачей','для поддержки')),
    ('5. 重新拧紧放气螺钉,然后确定制动液在储液箱内处于最高 （上） 液位线。','brakes',('затяните винт прокачки','Затем убедитесь','тормозной жидкости','максимальной (верхней)')),
    ('8. 让助手完全踩动制动踏板几次,然后踩住制动踏板。','brakes',('Попросите помощника','полностью нажать педаль тормоза','удерживать педаль тормоза нажатой')),
])
def test_known_cata_closed_actions_and_relations(engine,source,branch,required):
    result=engine.lookup_direct(request(source,branch,kind='PROCEDURE_STEP'))
    assert result is not None
    for text in required:assert text in result.translated_text
    assert not violations(source,result.translated_text)
    engine.router.translate.assert_not_called()

@pytest.mark.parametrize('source,branch,required',[
    ('将千斤顶安装到油底壳下。','engine','под масляным поддоном'),
    ('重新拧紧放气螺钉。','brakes','Снова затяните винт прокачки.'),
    ('让助手踩动制动踏板几次，然后踩住制动踏板。','brakes','несколько раз нажать'),
])
def test_related_independent_variants(engine,source,branch,required):
    result=engine.lookup_direct(request(source,branch,kind='PROCEDURE_STEP'))
    # Missing independently reviewed instrumental must back off, not inflect.
    if '油底壳下' in source:assert result is None
    else:assert result and required in result.translated_text

@pytest.mark.parametrize('source',[
    '将未知工具安装到油盘边缘处。','将千斤顶安装到未知部位下。',
    '将千斤顶安装到变速驱动桥下来支撑，然后执行未知操作。',
    '不要重新拧紧放气螺钉。','重新拧紧放气螺钉至25Nm。',
    '让助手完全踩动制动踏板几次，然后踩住离合器踏板。',
    '让助手完全踩动制动踏板几次，然后踩住制动踏板并启动发动机。',
    '如果有泄漏，重新拧紧放气螺钉。',
])
def test_unknown_tails_conditions_and_changed_actor_cannot_partially_render(engine,source):
    assert engine.lookup_direct(request(source,'brakes',kind='PROCEDURE_STEP')) is None

@pytest.mark.parametrize('source,bad',[
    ('将千斤顶安装到变速驱动桥下来支撑。','Установите килограмм в коробку передач для поддержки.'),
    ('将千斤顶安装到油盘边缘处','Установите домкрат.'),
    ('重新拧紧放气螺钉。','Нажмите винт.'),
    ('让助手完全踩动制动踏板几次，然后踩住制动踏板。','Попросите помощника поднимать педаль тормоза, затем отпустить педаль.'),
    ('踩住制动踏板。','Нажмите педаль тормоза.'),
])
def test_safety_guards_reject_lost_and_inverted_actions(source,bad):
    assert violations(source,bad)
