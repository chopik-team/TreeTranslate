"""Closed clause composition over verified actions and complete object forms.

Every clause must parse. Unknown tails, conditions, numbers and polysemy back
off to the ordinary pipeline. This is not a free Chinese grammar or morphology.
"""
import json
import re
from dataclasses import replace

from app.glossary.models import entry_metadata
from app.glossary.constraints import validate_result
from app.glossary.errors import ConstraintFailure
from .safety import action_records

DIRECTIONS = {'顺时针': 'по часовой стрелке', '逆时针': 'против часовой стрелки'}
# Independently authored infinitives; never inferred from imperative endings.
PURPOSES = {'松开': 'ослабить', '拧松': 'ослабить', '拧紧': 'затянуть'}
SAFE_ACTIONS = {'REMOVE','INSTALL','CHECK','INSPECT','REPLACE','TIGHTEN','LOOSEN',
                'MEASURE','ADJUST','ALIGN','DISCONNECT','CONNECT','UNSCREW',
                'PULL','PRESS','ROTATE','RELEASE','OPEN'}


def action_heading(text):
    unambiguous = {'REMOVE','INSTALL','CHECK','INSPECT','REPLACE','CLEAN','TIGHTEN','LOOSEN','MEASURE','ADJUST','ALIGN','START','WAIT'}
    parts = re.split(r'和|及',text.strip())
    if not 1 <= len(parts) <= 3:
        return None
    labels = []
    for part in parts:
        alternatives = {a['heading'] for a in action_records()
                        if a['semantic_id'] in unambiguous and part.strip() in a['zh']}
        if len(alternatives) != 1:
            return None
        labels.append(next(iter(alternatives)))
    return labels[0] + ''.join(' и '+label.lower() for label in labels[1:])


def compose(request, forms):
    snapshot = request.knowledge_snapshot
    if snapshot is None or request.domain != 'automotive':
        return None
    text = request.text.strip()
    if len(text) > 768:
        return None
    enumeration = re.match(r'^\d{1,3}[.、]\s*', text)
    prefix = enumeration[0] if enumeration else ''
    if enumeration:
        text = text[enumeration.end():]
    clauses = re.split(r'[，,。；;]', text)
    if not clauses[-1]:
        clauses.pop()
    if not 1 <= len(clauses) <= 6 or any(not c.strip() for c in clauses):
        return None

    def object_form(source, case='accusative'):
        nonlocal used_special
        source = source.strip()
        label = re.search(r'\s*([（(][A-Z][0-9]{0,2}[）)])$', source)
        suffix = label[0] if label else ''
        noun = source[:label.start()].strip() if label else source
        form = forms.get(noun)
        assembly = False
        if not form and noun.endswith('总成'):
            # A known complete assembly always owns its meaning. Derive only
            # an unknown assembly of one complete verified physical base.
            whole = snapshot.candidates(noun,request.domain,request.context,set())
            if any(m.start==0 and m.end==len(noun) for m in whole):
                return None
            noun = noun[:-2].strip()
            if noun.endswith('总成') or noun in {'部件','组件','零件','元件','系统','部分'}:
                return None
            form = forms.get(noun)
            if (not form or form.get('assembly_allowed') is not True
                    or not all(form.get(k) for k in ('nominative','genitive','accusative'))
                    or re.search(r'\bв сборе\b',form['base'],re.I)):
                return None
            assembly = True
        if not form or not form.get(case):
            return None
        matches = [m for m in snapshot.candidates(noun,request.domain,request.context,set())
                   if m.start == 0 and m.end == len(noun) and m.entry.trust >= .8
                   and m.entry.mode=='PREFERRED'
                   and m.entry.status in ('BUILTIN','REVIEWED','CONFIRMED')
                   and entry_metadata(m.entry).get('review_status') == 'VERIFIED']
        if request.context_router is not None:
            from app.glossary.engine import GlossaryEngine
            matches = [m for m in matches if GlossaryEngine.reviewed_context_allowed(
                m.entry,m.store,noun[m.start:m.end],request.text,request)]
            matches = request.context_router.ranked(matches,request)
        if assembly and any(m.store=='user' or not entry_metadata(m.entry).get('concept_id')
                or str(entry_metadata(m.entry).get('type','')).upper() not in {'TERM','COMPOUND'}
                or entry_metadata(m.entry).get('semantic_role') in {'quantity','diagnostic_relation'}
                or entry_metadata(m.entry).get('label_only') for m in matches):
            return None
        if assembly:
            # Confidence belongs to the whole noun slot, not its surrounding
            # imperative. Keep the router's existing HIGH bypass threshold.
            noun_request = replace(request,text=noun,segment_type='COMPONENT_LABEL')
            if (request.context_router is None
                    or not all(request.context_router.allow_bypass(m,noun_request) for m in matches)):
                return None
        concepts = {(entry_metadata(m.entry).get('concept_id'),m.entry.target_term.casefold()) for m in matches}
        if len(concepts) != 1 or next(iter(concepts))[1] != form['base'].casefold():
            return None
        if assembly:
            used_special = True
        return form[case] + (' в сборе' if assembly else '') + (' '+suffix.strip() if suffix else '')

    rendered = []
    used_special = False
    # Closed relations use the same verified whole-noun lookup as ordinary
    # directives. Never infer a case ending, actor, location or omitted tail.
    repeated = re.fullmatch(r'让助手(完全)?踩动([^,，。.；;]{1,64})几次[,，]\s*然后踩住([^,，。.；;]{1,64})[。.]?', text)
    if repeated:
        noun = repeated[2].strip()
        form = forms.get(noun, {})
        obj = object_form(noun)
        if (noun != repeated[3].strip() or not obj
                or form.get('safety_role') != 'pedal'
                or not form.get('held_accusative')):
            return None
        target = (prefix+'Попросите помощника несколько раз '+
                  ('полностью ' if repeated[1] else '')+'нажать '+obj+
                  ', затем удерживать '+obj+' '+form['held_accusative']+'.')
        try:
            return validate_result(request.text, target), 'closed-pedal-press-hold-v1'
        except ConstraintFailure:
            return None
    for clause in clauses:
        clause = clause.strip()
        then = clause.startswith('然后')
        if then:
            clause = clause[2:].strip()
        support = re.fullmatch(r'将(.{1,64})安装到(.{1,64}?)(边缘处|下来支撑|下)', clause)
        level = re.fullmatch(r'确定(.{1,64})在(.{1,64})内处于最高\s*[（(]上[）)]\s*液位线', clause)
        if support:
            tool = object_form(support[1])
            location = object_form(support[2], 'genitive' if support[3] == '边缘处' else 'instrumental')
            if (not tool or not location
                    or forms.get(support[1], {}).get('safety_role') != 'lifting_device'):
                return None
            relation = 'у края ' if support[3] == '边缘处' else 'под '
            target = 'Установите '+tool+' '+relation+location
            if support[3] == '下来支撑':
                target += ' для поддержки'
            rendered.append(('Затем '+target[0].lower()+target[1:] if then else target)+'.')
            used_special = True
            continue
        if level:
            fluid = object_form(level[1], 'genitive')
            container = object_form(level[2], 'locative')
            if (not fluid or not container
                    or forms.get(level[1], {}).get('safety_role') != 'brake_fluid'
                    or forms.get(level[2], {}).get('safety_role') != 'brake_fluid_reservoir'):
                return None
            rendered.append(('Затем убедитесь' if then else 'Убедитесь')+
                            ', что уровень '+fluid+' в '+container+
                            ' находится на максимальной (верхней) отметке.')
            used_special = True
            continue
        repeated_action = clause.startswith('重新')
        if repeated_action:
            clause = clause[2:].strip()
        direction = None
        for source, target in DIRECTIONS.items():
            if clause.startswith(source):
                direction = target
                clause = clause[len(source):]
                if clause.startswith('方向'):
                    clause = clause[2:]
                break
        purpose = None
        purpose_match = re.search(r'(?:来|以)('+'|'.join(PURPOSES)+r')$', clause)
        if purpose_match:
            purpose = PURPOSES[purpose_match[1]]
            clause = clause[:purpose_match.start()]
        power = re.fullmatch(r'(?:关闭|切断)(.{1,64})电源',clause)
        if power:
            if direction or purpose:
                return None
            actions = [a for a in action_records() if a['semantic_id']=='REMOVE_POWER']
            if len(actions)!=1:
                return None
            obj = object_form(power[1],'genitive')
            verb = actions[0]['imperative']
            used_special = True
        elif clause.startswith('使用'):
            noun = clause[2:].strip()
            if direction or purpose or not re.fullmatch(r'.{1,40}扳手(?:\s*[（(][A-Z][0-9]{0,2}[）)])?', noun):
                return None
            obj = object_form(noun)
            verb = 'Используйте'
            used_special = True
        else:
            actions = [(len(surface),action,surface) for action in action_records()
                       if action['semantic_id'] in SAFE_ACTIONS and action.get('review_state') == 'VERIFIED'
                       for surface in action['zh'] if clause.startswith(surface)]
            if not actions:
                return None
            _, action, surface = max(actions, key=lambda a:a[0])
            if direction and action['semantic_id'] != 'ROTATE':
                return None
            if purpose and action['semantic_id'] not in ('ROTATE','PRESS','PULL'):
                return None
            obj = object_form(clause[len(surface):])
            verb = action['imperative']
        if obj is None:
            return None
        target = ('Затем '+verb.lower() if then else verb)+' '+obj
        if repeated_action:
            target = ('Затем снова '+verb.lower() if then else 'Снова '+verb.lower())+' '+obj
            used_special = True
        if direction:
            target += ' '+direction
            used_special = True
        if purpose:
            target += ', чтобы '+purpose
            used_special = True
        rendered.append(target+'.')
    if not used_special and len(rendered) == 1:
        return None  # Existing templates retain ordinary single-action handling.
    target = prefix+' '.join(rendered)
    try:
        target = validate_result(request.text,target)
    except ConstraintFailure:
        return None
    return target, 'closed-directives-v1'
