"""Conservative semantic guards above every Chinese-to-Russian route.

These checks reject explicit contradictions, not certify arbitrary prose.
Source action surfaces come from the existing verified action registry.
Russian command variants are independently authored; noun mentions alone do
not establish a contradictory instruction.
"""
import json
import re
from functools import lru_cache
from app.config.paths import ASSETS_DIR

def load_action_safety(path=None):
    data = json.loads((path or ASSETS_DIR / 'config/technical-action-safety.json').read_text('utf8'))
    if data.get('version') != '0.81' or data.get('review_state') != 'VERIFIED':
        raise ValueError('Unreviewed action safety configuration')
    commands, incompatible = data['patterns'], data['incompatible']
    registered = {a['semantic_id'] for a in json.loads(
        (ASSETS_DIR / 'config/technical-actions.json').read_text('utf8'))['actions']
        if a['review_state'] == 'VERIFIED'} | {'CUT'}
    if not isinstance(commands,dict) or not isinstance(incompatible,dict):
        raise ValueError('Invalid action safety matrix')
    for concept, pattern in commands.items():
        if concept not in registered or not isinstance(pattern,str) or not pattern:
            raise ValueError('Unknown action safety pattern')
        re.compile(pattern)
    for concept, opposites in incompatible.items():
        if (concept not in commands or not isinstance(opposites,list)
                or len(opposites)!=len(set(opposites))
                or any(other not in commands or other==concept for other in opposites)):
            raise ValueError('Invalid incompatible action pair')
    return commands, {key:tuple(values) for key,values in incompatible.items()}


COMMANDS, OPPOSITES = load_action_safety()
NEGATIVE_ZH = re.compile(r'不要|不得|禁止|切勿|不能|没有|缺失|缺少|缺乏|未(?!来)|无(?!论|级|刷|线)|不(?!同|足|仅|良|正常)')
NEGATIVE_RU = re.compile(r'\b(?:не|нет|без|никогда|никак\w*|отсутств\w*|запрещ\w*|нельзя)\b', re.I)


@lru_cache(maxsize=1)
def action_records():
    data = json.loads((ASSETS_DIR / 'config/technical-actions.json').read_text('utf8'))
    return tuple(action for action in data['actions'] if action['review_state'] == 'VERIFIED')


@lru_cache(maxsize=1)
def action_surfaces():
    return tuple(sorted(((surface, action['semantic_id']) for action in action_records()
                         if action['review_state'] == 'VERIFIED' and action['semantic_id'] in COMMANDS
                         for surface in action['zh']), key=lambda x: -len(x[0])))


def source_actions(source):
    found, occupied = set(), set()
    for match in re.finditer(r'(?:关闭|切断)[^，。；,;]{1,64}电源',source):
        found.add('REMOVE_POWER')
        occupied.update(range(match.start(),match.end()))
    for surface, concept in action_surfaces():
        for match in re.finditer(re.escape(surface), source):
            positions = set(range(match.start(), match.end()))
            if positions & occupied:
                continue
            occupied |= positions
            # A temporal circumstance is not a second commanded operation.
            # "During installation, remove dirt" must not be rejected as an
            # install/remove contradiction involving the same component.
            if (re.search(r'(?:在|当)[^，。；]{0,80}$', source[:match.start()])
                    and re.match(r'[^，。；]{0,80}时', source[match.end():])):
                continue
            if surface == '安装' and re.match(r'位置|孔|方法|步骤|说明|工具', source[match.end():]):
                continue
            if surface == '连接' and re.match(r'器', source[match.end():]):
                continue
            if surface in ('锁定','锁止') and re.match(r'销|装置|机构|系统', source[match.end():]):
                continue
            # The registry's 关闭 is STOP only for engines, otherwise ambiguous.
            if (surface == '关闭' and not re.match(r'\s*发动机', source[match.end():])
                    and not re.search(r'发动机\s*$', source[:match.start()])):
                continue
            found.add(concept)
    # CUT is used only to avoid rejecting a legitimate cut-and-remove sequence;
    # it is not used to create an output or a new verified concept.
    for match in re.finditer(r'切断(?!电源)|剪断|割断',source):
        if not set(range(match.start(),match.end())) & occupied:
            found.add('CUT')
    return found


def russian_actions(target):
    # A multiword power operation owns its verb; "remove power" must not
    # also count as removing a component or disconnecting a connector.
    spans = [(m.start(), m.end(), concept) for concept, pattern in COMMANDS.items()
             for m in re.finditer(r'\b(?:'+pattern+r')\b', target, re.I)]
    found, occupied, accepted = set(), set(), set()
    for start, end, concept in sorted(spans, key=lambda s: -(s[1]-s[0])):
        positions = set(range(start,end))
        if (start, end) in accepted:
            found.add(concept)
        elif not positions & occupied:
            found.add(concept)
            occupied |= positions
            accepted.add((start, end))
    return found


def violations(source, target):
    reasons = []
    # Safety relations are checked even when an unseen tail prevents closed
    # composition. Reject a lost support tool/location and inverted pedal
    # commands rather than allowing plausible but dangerous model prose.
    if re.search(r'将千斤顶安装到', source):
        if not re.search(r'\bдомкрат\w*\b', target, re.I):
            reasons.append('object:lifting_device:LOST')
        if '边缘处' in source and not re.search(r'\bкра[йяюем]\w*\b', target, re.I):
            reasons.append('condition:support_edge')
        if re.search(r'安装到[^，,。；;]+下', source) and not re.search(r'\bпод\b', target, re.I):
            reasons.append('condition:support_below')
        if '来支撑' in source and not re.search(r'поддерж\w*|опор\w*|подопр\w*', target, re.I):
            reasons.append('action:SUPPORT:LOST')
    if re.search(r'拧紧放气螺钉', source):
        if 'TIGHTEN' not in russian_actions(target):
            reasons.append('action:TIGHTEN:LOST')
        if not re.search(r'\bвинт\w*\b[^.。]*\b(?:прокачк\w*|выпуск\w*|удалени\w*)', target, re.I):
            reasons.append('object:bleed_screw:LOST')
    if re.search(r'踩(?:动|住)制动踏板', source):
        if re.search(r'подним\w*|подня\w*|отпуст\w*|отпуск\w*|освобод\w*', target, re.I):
            reasons.append('action:PEDAL_PRESS:RELEASE')
        if '踩动' in source and not re.search(r'наж\w*', target, re.I):
            reasons.append('action:PEDAL_PRESS:LOST')
        if '踩住' in source and not (re.search(r'удерж\w*', target, re.I) and re.search(r'нажат\w*', target, re.I)):
            reasons.append('action:PEDAL_HOLD:LOST')
    from .questions import violations as question_violations
    reasons.extend(question_violations(source,target))
    for chinese, russian, name in (
        ('顺时针', r'(?<!против )\bпо часовой стрелке\b', 'clockwise'),
        ('逆时针', r'\bпротив часовой стрелки\b', 'counterclockwise'),
    ):
        if chinese in source and not re.search(russian, target, re.I):
            reasons.append('direction:' + name)
    branch = re.match(r'^\s*(是|否)\s*([▶►→])\s*(.*)$', source, re.S)
    if branch:
        rendered_branch = re.match(r'^\s*(Да|Нет)\s*[▶►→]\s*(.*)$', target, re.I | re.S)
        expected = 'да' if branch[1] == '是' else 'нет'
        if not rendered_branch or rendered_branch[1].casefold() != expected:
            reasons.append('diagnostic:branch')
        source = branch[3]
        if rendered_branch:
            target = rendered_branch[2]
    original = source_actions(source)
    rendered = russian_actions(target)
    for concept in sorted(original):
        for opposite in OPPOSITES.get(concept, ()):
            if opposite in rendered and opposite not in original:
                reasons.append(f'action:{concept}:{opposite}')
    source_negative = len(NEGATIVE_ZH.findall(source))
    target_negative = len(NEGATIVE_RU.findall(target))
    lexical_negative = bool(re.search(r'不良|不正常',source))
    lexical_rendered = bool(re.search(r'\b(?:неправил\w*|неисправ\w*|плох\w*|некачеств\w*|ненормал\w*|некоррект\w*|неудовлетвор\w*)\b',target,re.I))
    if lexical_negative and not (lexical_rendered or target_negative):
        reasons.append('negation:lexical_bad_condition')
    if source_negative and not target_negative:
        reasons.append('negation:lost')
    if (target_negative and not source_negative and not lexical_negative and not re.search(r'避免|防止|免于', source)
            and not ('是否' in source and re.search(r'\bли\b', target, re.I))):
        reasons.append('negation:added')
    conditions = (
        ('if', r'如果|(?:^|[，。；\s])若', r'\bесли\b|\bпри\b|в случае'),
        ('before', r'之前|以前', r'\bперед\b|\bдо\b|прежде'),
        ('after', r'之后|以后', r'\bпосле\b|\bзатем\b|\bпотом\b|\bдалее\b'),
        ('until', r'直到', r'пока|\bдо\b'),
        ('only', r'只有', r'только|лишь'),
        ('unless', r'除非', r'если|за исключением|кроме'),
    )
    for kind, chinese, russian in conditions:
        if re.search(chinese, source) and not re.search(russian, target, re.I):
            reasons.append('condition:' + kind)
    if (re.search(r'当[^。；]{1,80}时|在[^。；]{1,80}时', source)
            and not re.search(r'\bпри\b|\bкогда\b|\bпока\b|\bперед\b|во время|\bесли\b|на (?:горячем|холодном|работающем|остановленном)\b', target, re.I)):
        reasons.append('condition:when')
    return tuple(reasons)
