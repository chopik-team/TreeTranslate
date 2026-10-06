"""Real bundled data and existing template-component contracts."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest

from app.engine.types import TranslationRequest
from app.glossary.bundled import bundled_paths
from app.glossary.engine import GlossaryEngine


@pytest.fixture
def glossary(tmp_path):
    return GlossaryEngine(tmp_path / 'user.db', builtin_paths=bundled_paths())


@pytest.mark.parametrize('source,target', [
    ('散热器盖', 'Крышка радиатора'),
    ('冷却风扇', 'Вентилятор системы охлаждения'),
    ('机油滤清器', 'Масляный фильтр'),
    ('悬架弹簧', 'Пружина подвески'),
    ('线束连接器', 'Разъём жгута проводов'),
    ('读取故障码', 'Считайте коды неисправностей'),
])
def test_expansion_exact_without_model(glossary, source, target):
    request = TranslationRequest(source, 'zh', 'ru', domain='automotive')
    assert glossary.full_segment(request).translated_text == target
    assert glossary.full_segment(replace(request, domain='software')) is None


@pytest.mark.parametrize('source,malformed,expected', [
    ('蓄电池', 'Проверьте аккумуляторная батарея', 'Проверьте аккумуляторную батарею'),
    ('散热器盖', 'Снимите крышка радиатора', 'Снимите крышку радиатора'),
    ('诊断仪', 'С помощью диагностический прибор', 'С помощью диагностического прибора'),
    ('悬架弹簧', 'Замените пружина подвески', 'Замените пружину подвески'),
])
def test_existing_template_slot_and_user_boundary(glossary, source, malformed, expected):
    matches = glossary.lookup(source, 'zh', 'ru', 'automotive')
    assert GlossaryEngine.grammatical_phrases(malformed, matches) == expected
    assert GlossaryEngine.grammatical_phrases(malformed, ()) == malformed
    glossary.remember_term(source, matches[0].entry.target_term, 'zh', 'ru', 'automotive')
    user = glossary.lookup(source, 'zh', 'ru', 'automotive')
    assert user[0].store == 'user'
    assert GlossaryEngine.grammatical_phrases(malformed, user) == malformed


def test_materialized_scope_keeps_mixed_mounting_holes():
    path = Path('assets/knowledge/aw083-body-repair-zh-ru.db')
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 1
        missing = con.execute('''SELECT count(*) FROM entries e WHERE NOT EXISTS
            (SELECT 1 FROM knowledge_context_index k WHERE k.entry_id=e.id)''').fetchone()[0]
        assert missing == 0
        rows = con.execute('''SELECT k.subdomain FROM knowledge_context_index k
            JOIN entries e ON k.entry_id=e.id WHERE e.source_term=?''', ('前悬架弹簧孔',)).fetchall()
        assert {'suspension', 'body.body_repair'} <= {r[0] for r in rows}


def test_previous_targets_preserved_and_every_assignment_auditable():
    assignments = json.loads(Path('qa/aw086/knowledge_assignments.json').read_text('utf-8'))
    assert len(assignments) >= 296
    assert all(row['concept_id'] and row['subdomains'] and row['segment_types'] for row in assignments)
    assert json.loads(Path('qa/aw086/knowledge_base_after.json').read_text('utf-8'))['previous_translations_unchanged']
