"""Bounded diagnostic question features and whole-known-noun rendering."""
from dataclasses import dataclass, replace
import re

from app.glossary.models import entry_metadata
from app.glossary.constraints import validate_result
from app.glossary.errors import ConstraintFailure


@dataclass(frozen=True)
class QuestionFeature:
    kind: str
    predicate: str = ''
    object_source: str = ''
    prefix: str = ''


def features(source):
    text = source.strip()
    prefix = re.match(r'^\d{1,3}[.．、]\s*',text)
    body = text[prefix.end():] if prefix else text
    if not body.endswith(('？','?')) or len(body)>512:
        return None
    displayed=re.fullmatch(r'显示相同的([^\r\n，,。；;？?]{1,80})吗[？?]',body)
    if displayed:
        return QuestionFeature('STATE_CHECK','DISPLAY_SAME',displayed[1].strip(),prefix[0] if prefix else '')
    found = re.fullmatch(r'(?:找到|发现)([^\r\n，,。；;？?]{1,80}?)了吗[？?]',body)
    if found:
        kind = 'FAULT_CHECK' if re.search(r'故障|异常|问题',found[1]) else 'YES_NO'
        return QuestionFeature(kind,'FOUND',found[1].strip(),prefix[0] if prefix else '')
    if re.search(r'[，,。；;]',body):
        return None  # Do not assign a subordinate clause's role to the question.
    quantity = bool(re.search(r'电压|电流|电阻|温度|压力|容量|转速',body))
    normal = re.search(r'(?<!不)正常(?:吗)?[？?]$',body)
    abnormal = bool(re.search(r'不正常(?:吗)?[？?]$',body))
    if not re.search(r'吗|是否|是不是|有没有|多少',body):
        return None  # Question punctuation alone does not prove a question role.
    kind = 'VALUE_CHECK' if quantity else ('STATE_CHECK' if normal or abnormal else 'YES_NO')
    return QuestionFeature(kind,'ABNORMAL' if abnormal else ('NORMAL' if normal else ''))


def violations(source,target):
    feature = features(source)
    if feature is None:
        return ()
    reasons = []
    if not target.rstrip().endswith(('?','？')):
        reasons.append('question:lost')
    if feature.predicate=='FOUND':
        found = re.search(r'\b(?:найден\w*|найти|наш[её]л\w*|нашли|обнаруж\w*)\b',target,re.I)
        if feature.kind=='FAULT_CHECK':
            found = found or re.search(r'\b(?:выявл\w*|определ[её]н\w*|установлен\w*)\b',target,re.I)
            if not re.search(r'\b(?:неисправ\w*|сбо\w*|отказ\w*|ошибк\w*|дефект\w*|аномал\w*|проблем\w*)\b',target,re.I):
                reasons.append('question:fault_meaning')
        if not found:
            reasons.append('question:found_relation')
    if feature.predicate=='NORMAL' and not re.search(r'\bнормаль\w*|\bисправ\w*|в норме',target,re.I):
        reasons.append('question:normal_predicate')
    if feature.predicate=='DISPLAY_SAME':
        if not re.search(r'\b(?:отображается|отображаются|показывается|показываются|выводится|выводятся|появляется|появляются)\s+ли\b',target,re.I):
            reasons.append('question:display_state')
        if not re.search(r'\b(?:тот|та|то|те)\s+же\b',target,re.I):
            reasons.append('question:same_relation')
    return tuple(reasons)


def compose(request,forms):
    feature = features(request.text)
    if (feature is None or feature.predicate not in {'FOUND','DISPLAY_SAME'} or request.domain!='automotive'
            or request.source_language!='zh' or request.target_language!='ru'
            or request.knowledge_snapshot is None or request.context_router is None):
        return None
    noun = feature.object_source
    form = forms.get(noun)
    if not form or not all(form.get(k) for k in ('nominative','genitive','accusative')):
        return None
    noun_request = replace(request,text=noun,segment_type='COMPONENT_LABEL')
    matches = request.knowledge_snapshot.candidates(noun,request.domain,request.context,set())
    whole = [m for m in matches if m.start==0 and m.end==len(noun)]
    if (not whole or any(m.store=='user' or m.entry.mode!='PREFERRED'
            or m.entry.trust<.8 or m.entry.status not in {'BUILTIN','REVIEWED','CONFIRMED'}
            or entry_metadata(m.entry).get('review_status')!='VERIFIED'
            or entry_metadata(m.entry).get('label_only')
            or entry_metadata(m.entry).get('semantic_role')=='quantity'
            or not request.context_router.allow_bypass(m,noun_request) for m in whole)):
        return None
    identities = {(entry_metadata(m.entry).get('concept_id'),m.entry.target_term.casefold()) for m in whole}
    if (len(identities)!=1 or not next(iter(identities))[0]
            or next(iter(identities))[1]!=form['base'].casefold()):
        return None
    if feature.predicate=='DISPLAY_SAME':
        # Agreement is a published whole form, never inferred from endings.
        same=form.get('same_nominative')
        if not same:return None
        target=feature.prefix+'Отображается ли '+same+'?'
    else:target=feature.prefix+'Удалось ли найти '+form['accusative']+'?'
    try:
        target = validate_result(request.text,target)
    except ConstraintFailure:
        return None
    if violations(request.text,target):
        return None
    return target,feature.kind
