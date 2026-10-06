"""Independent adversarial action/condition cases; no held reference sentences."""
import pytest
from app.knowledge.safety import violations


@pytest.mark.parametrize('change', ['unknown_action','self_pair','missing_pattern','unreviewed','bad_regex'])
def test_action_matrix_rejects_invalid_configuration(tmp_path,change):
    import json
    from app.config.paths import ASSETS_DIR
    from app.knowledge.safety import load_action_safety
    data=json.loads((ASSETS_DIR/'config/technical-action-safety.json').read_text('utf8'))
    if change=='unknown_action':data['patterns']['INVENTED']='выдумайте'
    if change=='self_pair':data['incompatible']['REMOVE'].append('REMOVE')
    if change=='missing_pattern':del data['patterns']['CUT']
    if change=='unreviewed':data['review_state']='REVIEW_REQUIRED'
    if change=='bad_regex':data['patterns']['REMOVE']='['
    path=tmp_path/'matrix.json'
    path.write_text(json.dumps(data,ensure_ascii=False),'utf8')
    with pytest.raises((ValueError,__import__('re').error)):
        load_action_safety(path)


def test_combined_action_headings_use_reviewed_registry():
    from unittest.mock import Mock
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    from app.engine.types import TranslationRequest
    engine = TranslationKnowledgeEngine(Mock(), Mock())
    result = engine._structured_exact(TranslationRequest('拆卸和安装','zh','ru'))
    assert result.translated_text == 'Снятие и установка'
    result = engine._structured_exact(TranslationRequest('检查及调整','zh','ru'))
    assert result.translated_text == 'Проверка и регулировка'


def test_lexical_bad_condition_is_separate_from_instruction_negation():
    assert not violations('如果开关工作不正常，更换开关。','Если выключатель работает неправильно, замените выключатель.')
    assert not violations('检查连接不良。','Проверьте плохое соединение.')
    assert 'negation:lexical_bad_condition' in violations('开关工作不正常。','Выключатель работает нормально.')
    assert 'negation:lost' in violations('不要拆下开关。','Снимите неисправный выключатель.')


@pytest.mark.parametrize('source,target,reason', [
    ('拆下检修盖。', 'Разрежьте сервисную крышку.', 'action:REMOVE:CUT'),
    ('安装检修盖。', 'Снимите сервисную крышку.', 'action:INSTALL:REMOVE'),
    ('断开测试连接器。', 'Подсоедините тестовый разъём.', 'action:DISCONNECT:CONNECT'),
    ('连接测试连接器。', 'Отсоедините тестовый разъём.', 'action:CONNECT:DISCONNECT'),
    ('拧紧测试螺栓。', 'Ослабьте тестовый болт.', 'action:TIGHTEN:LOOSEN'),
    ('打开检修盖。', 'Закройте сервисную крышку.', 'action:OPEN:CLOSE'),
    ('按下测试开关。', 'Отпустите тестовый выключатель.', 'action:PRESS:RELEASE'),
    ('不要拆下检修盖。', 'Снимите сервисную крышку.', 'negation:lost'),
    ('检查测试开关。', 'Не проверяйте тестовый выключатель.', 'negation:added'),
    ('如果测试开关失效，更换开关。', 'Замените неисправный тестовый выключатель.', 'condition:if'),
    ('检查之前，拆下检修盖。', 'После проверки снимите сервисную крышку.', 'condition:before'),
    ('提高测试压力。', 'Уменьшите тестовое давление.', 'action:INCREASE:DECREASE'),
    ('减少测试压力。', 'Увеличьте тестовое давление.', 'action:DECREASE:INCREASE'),
    ('锁定测试机构。', 'Разблокируйте тестовый механизм.', 'action:LOCK:UNLOCK'),
    ('解锁测试机构。', 'Заблокируйте тестовый механизм.', 'action:UNLOCK:LOCK'),
    ('释放测试夹子。', 'Зафиксируйте тестовый зажим.', 'action:RELEASE:LOCK'),
    ('启用测试功能。', 'Деактивируйте тестовую функцию.', 'action:ENABLE:DISABLE'),
    ('禁用测试功能。', 'Активируйте тестовую функцию.', 'action:DISABLE:ENABLE'),
    ('通电。', 'Отключите питание.', 'action:APPLY_POWER:REMOVE_POWER'),
    ('切断电源。', 'Подайте питание.', 'action:REMOVE_POWER:APPLY_POWER'),
    ('推入测试夹子。', 'Вытяните тестовый зажим.', 'action:PUSH:PULL'),
    ('闭合测试触点。', 'Откройте тестовые контакты.', 'action:CLOSE:OPEN'),
])
def test_reject_semantic_changes(source, target, reason):
    from app.knowledge.safety import violations
    assert reason in violations(source, target)


@pytest.mark.parametrize('source,target', [
    ('拆下检修盖。', 'Демонтируйте сервисную крышку.'),
    ('不要拆下检修盖。', 'Не снимайте сервисную крышку.'),
    ('如果测试开关失效，更换开关。', 'Если тестовый выключатель неисправен, замените его.'),
    ('在检查之前拆下检修盖。', 'Перед проверкой снимите сервисную крышку.'),
    ('检查不同品牌的开关。', 'Проверьте выключатели разных марок.'),
    ('无论温度如何，都检查开关。', 'Проверьте выключатель независимо от температуры.'),
    ('拆下检修盖，然后切断测试导线。', 'Снимите сервисную крышку, затем разрежьте тестовый провод.'),
    ('安装位置。', 'Место установки.'),
    ('该浓度不推荐。', 'Такая концентрация не рекомендуется.'),
    ('检查测试信号缺失记录。', 'Проверьте записи об отсутствии тестового сигнала.'),
    ('发动机关闭之后，起动发动机。', 'Заглушите двигатель, затем запустите двигатель.'),
    ('在安装插头时清除污物。', 'Перед установкой штекера удалите загрязнения.'),
    ('拉出锁定销并推入夹子。', 'Вытяните фиксирующий штифт и вставьте зажим.'),
    ('切断电源并拆下盖。', 'Снимите питание и демонтируйте крышку.'),
])
def test_preserve_legitimate_meaning(source, target):
    from app.knowledge.safety import violations
    assert not violations(source, target)


def test_shared_boundary_blocks_unsafe_tm_and_warns(tmp_path):
    from unittest.mock import Mock
    from types import SimpleNamespace
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    from app.engine.types import TranslationRequest, TranslationResult
    from app.glossary.engine import GlossaryEngine
    router = Mock()
    router.policy.max_text_chars = 20000
    router.languages.resolve.return_value = ('zh', 'ru')
    router.translate.return_value = TranslationResult('Разрежьте тестовый колпачок.', 'zh', 'ru', 'm2m100', 'cpu', 0, '', False, '')
    memory = Mock()
    memory.lookup.return_value = SimpleNamespace(reusable=True, target='Разрежьте тестовый колпачок.', match_type='exact', translation_unit_id=1)
    warnings = []
    engine = TranslationKnowledgeEngine(router, memory, GlossaryEngine(tmp_path/'user.db', warning=warnings.append))
    request = TranslationRequest('拆下测试帽。', 'zh', 'ru')
    for result in [engine.translate(request), engine.lookup_direct(request)]:
        assert result.translated_text == request.text
        assert result.constraint_status.startswith('semantic_source_preserved:')
    assert warnings
    assert not memory.remember.called


@pytest.mark.parametrize('branch,word', [('是','Да'),('否','Нет')])
def test_diagnostic_branch_keeps_its_answer(tmp_path, branch, word):
    from unittest.mock import Mock
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    from app.engine.types import TranslationRequest, TranslationResult
    router = Mock()
    router.policy.max_text_chars = 20000
    router.languages.resolve.return_value = ('zh','ru')
    router.translate.return_value = TranslationResult('Проверьте тестовый разъём.', 'zh','ru','m2m100','cpu',0,'',False,'')
    engine = TranslationKnowledgeEngine(router, Mock(lookup=Mock(return_value=None)))
    result = engine.translate(TranslationRequest(branch+' ▶ 检查测试连接器。','zh','ru'))
    assert result.translated_text == word+' ▶ Проверьте тестовый разъём.'
    assert not violations(branch+' ▶ 检查测试连接器。', result.translated_text)


def test_retry_cannot_drop_an_action_to_escape_the_guard(tmp_path):
    from unittest.mock import Mock
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    from app.engine.types import TranslationRequest, TranslationResult
    router = Mock()
    router.policy.max_text_chars = 20000
    router.languages.resolve.return_value = ('zh','ru')
    router.translate.side_effect = [
        TranslationResult('Разрежьте тестовую крышку.', 'zh','ru','m2m100','cpu',0,'',False,''),
        TranslationResult('Тестовая крышка.', 'zh','ru','m2m100','cpu',0,'',False,'')]
    engine = TranslationKnowledgeEngine(router, Mock(lookup=Mock(return_value=None)))
    request = TranslationRequest('拆下测试盖。','zh','ru')
    result = engine.translate(request)
    assert result.translated_text == request.text
    assert result.constraint_status.startswith('semantic_source_preserved:')


def test_general_profile_scoring_and_bypass_do_not_require_a_subdomain():
    from types import SimpleNamespace
    from app.knowledge.router import KnowledgeRouter
    from app.glossary.models import GlossaryEntry, TermMatch
    from app.engine.types import TranslationRequest
    router = KnowledgeRouter(None)
    profile = SimpleNamespace(subdomains=(('general', 1.),), identity='independent-general')
    snapshot = SimpleNamespace(stores=('builtin',))
    entry = GlossaryEntry('检修', 'обслуживание', 'zh', 'ru', trust=1., status='BUILTIN')
    match = TermMatch(0, 2, entry, 'builtin')
    request = TranslationRequest('检修', 'zh', 'ru', context_profile=profile, knowledge_snapshot=snapshot)
    assert router.ranked((match,), request) == (match,)
    assert router.allow_bypass(match, request)
