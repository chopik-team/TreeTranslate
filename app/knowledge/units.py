"""Closed unit/number lines; never infer or convert the source values."""
import re
import json
from functools import lru_cache
from app.config.paths import ASSETS_DIR


@lru_cache(maxsize=1)
def semantic_corrections():
    return json.loads((ASSETS_DIR/'config/source-semantic-corrections.json').read_text('utf-8'))


def reviewed_context_measurement(request):
    """Reviewed mistranslated table captions; values stay literal.

    The unit is inherited only from a measured header verified in this document,
    never from the caption's position, numerical value or automotive topic.
    """
    from app.glossary.constraints import validate_result
    from app.glossary.errors import ConstraintFailure
    if request.source_language!='zh' or request.target_language!='ru':
        return None
    facts=set(getattr(request.context_profile,'semantic_facts',()))
    for rule in semantic_corrections()['measurement_labels']:
        if rule['fact'] not in facts:
            continue
        match=re.fullmatch(re.escape(rule['code'])+r'\s*'+re.escape(rule['source_label'])+
                           r'\s*[:：]\s*(\d+(?:[.,]\d+)?)\s*±\s*(\d+(?:[.,]\d+)?)\s*',request.text)
        if not match:
            continue
        target=f"{rule['code']} — {rule['target_label']}: {match[1]} ± {match[2]} {rule['target_unit']}"
        try:
            return validate_result(request.text+' '+rule['source_unit'],target)
        except ConstraintFailure:
            return None
    return None

UNIT_TOKENS=r'(?:kgf[·. ]m|N[·. ]m|lb[-· ]ft|US\s*(?:qt|gal)|(?:mm|cm|mL|kPa|MPa|rpm|inch|psi|gal|qt|kg|lb|L|V|A|m|Ω|Ω|°C))'
NUMBER=r'[+-]?\d+(?:[.,]\d+)?(?:\s*[-–—~～]\s*\d+(?:[.,]\d+)?)?'
TECHNICAL_MEASUREMENT=re.compile(r'\s*'+NUMBER+r'\s*'+UNIT_TOKENS+r'(?:\s*[,，;；/()]\s*'+r'(?:'+NUMBER+r'\s*'+UNIT_TOKENS+r')?)*\s*',re.I)
CAPACITY_UNITS={
 '美国加仑':'US gal','美制加仑':'US gal','美国夸脱':'US qt','美制夸脱':'US qt','英制夸脱':'UK qt',
 '加仑/夸脱':'галлон/кварта [неоднозначно в источнике]',
 '美升':'ед. «мэй-шэн» [неоднозначно в источнике]',
 '公升':'л','毫升':'мл','加仑':'gal','夸脱':'qt','升':'л'}

# Reviewed quantity-caption grammar. Total pressure/temperature have specialized
# meanings, so "total" is admitted only for capacity/volume; never guessed.
CAPTION_ADJECTIVES = {
 '总': {'f':'общая', 'm':'общий'},
 '最大': {'f':'максимальная', 'm':'максимальный', 'n':'максимальное'},
 '最小': {'f':'минимальная', 'm':'минимальный', 'n':'минимальное'},
 '额定': {'f':'номинальная', 'm':'номинальный', 'n':'номинальное'},
}


def reviewed_quantity_label(request):
    """One whole reviewed quantity caption with a literal trailing colon."""
    from dataclasses import replace
    from app.glossary.models import entry_metadata
    from app.glossary.constraints import validate_result
    from app.glossary.errors import ConstraintFailure
    if (request.source_language!='zh' or request.target_language!='ru'
            or request.domain!='automotive' or request.knowledge_snapshot is None
            or request.context_router is None):
        return None
    match = re.fullmatch(r'\s*([^:：\r\n，,。；;?!？!]{1,64}?)\s*([:：])\s*',request.text)
    if match is None:
        return None
    noun = match[1].strip()
    candidates = [m for m in request.knowledge_snapshot.candidates(noun,request.domain,request.context,set())
                  if m.start==0 and m.end==len(noun)]
    if not candidates:
        return None
    noun_request = replace(request,text=noun,segment_type='TABLE_HEADER')
    for candidate in candidates:
        entry, meta = candidate.entry, entry_metadata(candidate.entry)
        if (candidate.store=='user' or entry.trust<.8 or entry.mode!='PREFERRED'
                or entry.status not in ('BUILTIN','REVIEWED','CONFIRMED')
                or meta.get('review_status')!='VERIFIED' or not meta.get('concept_id')
                or str(meta.get('type','')).upper() not in {'TERM','COMPOUND'}
                or meta.get('semantic_role')!='quantity' or meta.get('label_only') is not True
                or not request.context_router.allow_bypass(candidate,noun_request)):
            return None
    concepts = {(entry_metadata(m.entry)['concept_id'],m.entry.target_term) for m in candidates}
    if len(concepts)!=1:
        return None
    try:
        return validate_result(request.text,next(iter(concepts))[1]+match[2])
    except ConstraintFailure:
        return None


def quantity_caption(text,lookup,forms):
    match = re.fullmatch(r'\s*(总|最大|最小|额定)(容量|容积|电压|压力|温度)(\s*[（(](?:cc|mL|L|V|kPa|MPa|°C|Ah)[）)])?\s*',text)
    if match is None or (match[1]=='总' and match[2] not in ('容量','容积')):
        return None
    form, target = forms.get(match[2]), lookup(match[2])
    if not form or not target or form['base'].casefold().replace('ё','е') != target.casefold().replace('ё','е'):
        return None
    adjective = CAPTION_ADJECTIVES[match[1]].get(form.get('gender'))
    if adjective is None:
        return None
    from app.glossary.constraints import validate_result
    from app.glossary.errors import ConstraintFailure
    try:
        return validate_result(text,adjective.capitalize()+' '+form['nominative']+(match[3] or ''))
    except ConstraintFailure:
        return None


def capacity_line(text,source,target):
    if source!='zh' or target!='ru' or len(text)>256:return None
    if not re.search(r'\d\s*(?:公升|升|毫升|加仑|夸脱|美升)',text):return None
    result=text
    for key in sorted(CAPACITY_UNITS,key=len,reverse=True):result=result.replace(key,CAPACITY_UNITS[key])
    # Only closed capacity labels and an optional protected uppercase system ID.
    result=result.replace('总计','Всего').replace('油盘','Масляный поддон').replace('油量','Объём масла').replace('约','около ')
    if re.search(r'[\u4e00-\u9fff]',result):return None
    cleaned=re.sub(r'\[[^\]]+\]|ед\. «мэй-шэн»|галлон/кварта|Всего|Масляный поддон|Объём масла|около', '',result)
    cleaned=re.sub(r'(?<![A-Za-z])[A-Z]{2,8}(?![A-Za-z])|UK qt|US qt|US gal|gal|qt|мл|л','',cleaned)
    if re.search(r'[^\d\s.,:：()（）+\-–—~～/]',cleaned):return None
    return result
