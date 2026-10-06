"""Publication must preserve action argument types, not expand every slot list."""
from tools.aw081_publish_components import reviewed_template_slots


def test_reviewed_component_enables_only_explicitly_reviewed_action_frames():
    row=dict(source='备用连接器',status='VERIFIED',template_rule_ids=['install-reviewed'])
    assert reviewed_template_slots([row],dict(id='install-reviewed',allowed_slots=[]))=={'备用连接器'}
    for rule in ['fill-fluid','drain-fluid','tighten-fastener','unscrew-fastener']:
        assert reviewed_template_slots([row],dict(id=rule,allowed_slots=[]))==set()
    assert reviewed_template_slots([dict(source='备用连接器',status='VERIFIED')],
                                   dict(id='install-reviewed',allowed_slots=[]))==set()


def test_declared_reviewed_alias_inherits_only_its_existing_parent_scope():
    row=dict(source='备用插头',alias_of='备用连接器',status='VERIFIED')
    assert reviewed_template_slots([row],dict(id='disconnect',allowed_slots=['备用连接器']))=={'备用插头'}
    assert reviewed_template_slots([row],dict(id='fill',allowed_slots=['冷却液']))==set()


def test_quantity_relation_and_deferred_nouns_cannot_be_physical_action_slots():
    rule=dict(id='reviewed',allowed_slots=[])
    for extra in [dict(semantic_role='quantity'),dict(semantic_role='diagnostic_relation'),dict(status='DEFERRED')]:
        row=dict(source='备用参数',status='VERIFIED',template_rule_ids=['reviewed'])
        row.update(extra)
        assert reviewed_template_slots([row],rule)==set()
