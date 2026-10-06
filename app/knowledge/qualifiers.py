"""Typed pressure/temperature properties of reviewed fluid nouns.

No unqualified 压 is resolved here. A reviewed fluid noun supplies the physical
meaning; unknown roots, competing senses and user overrides back off.
Derived constraints are ephemeral grammar results, never new Knowledge rows.
"""
from app.glossary.models import entry_metadata
from dataclasses import replace
import json
import re
from app.glossary.models import TermMatch
from app.glossary.normalization import normalize

FLUIDS = {'制冷剂气体','制冷剂','冷却液','燃油'}
PROPERTIES = {'高压':'высокого давления','低压':'низкого давления',
              '高温':'высокой температуры','低温':'низкой температуры'}


def derived_constraints(text, matches, forms):
    output, seen = [], set()
    for match in matches:
        entry = match.entry
        if (entry.source_term not in FLUIDS or match.store=='user' or entry.trust < .8
                or entry.status not in ('BUILTIN','REVIEWED','CONFIRMED') or entry.mode!='PREFERRED'):
            continue
        meta = entry_metadata(entry)
        if meta.get('review_status')!='VERIFIED':
            continue
        alternatives = [m for m in matches if m.start==match.start and m.end==match.end]
        if (any(m.store=='user' for m in alternatives)
                or len({m.entry.target_term.casefold() for m in alternatives})!=1):
            continue
        form = forms.get(entry.source_term)
        if not form or form['base'].casefold()!=entry.target_term.casefold():
            continue
        prefix = re.search(r'(?:[高低][压温]){1,2}$',text[max(0,match.start-8):match.start])
        if prefix is None:
            continue
        start = match.start-len(prefix[0])
        if start and text[start-1] in '超较更最过压温':
            continue
        tokens = re.findall(r'[高低][压温]',prefix[0])
        if len({t[1] for t in tokens}) != len(tokens):
            continue
        phrase = form.get('nominative',form['base'])+' '+' и '.join(PROPERTIES[t] for t in tokens)
        key = start, match.end, phrase
        if key in seen:
            continue
        seen.add(key)
        metadata = dict(meta, review_status='VERIFIED_RULE',rule_id='fluid-properties-v1',
                        base_concept_id=meta.get('concept_id'),property_tokens=tokens)
        metadata['concept_id'] = str(meta.get('concept_id'))+':properties:'+prefix[0]
        generated = replace(entry,source_term=text[start:match.end],source_normalized=normalize(text[start:match.end]),
                            target_term=phrase,notes=json.dumps(metadata,ensure_ascii=False),variants=(),
                            origin='authored_rule',provenance='AW0.81 reviewed fluid-property grammar; no document sentence stored.')
        output.append(TermMatch(start,match.end,generated,match.store))
        if len(output)==32:
            break
    return output
