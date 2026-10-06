"""Indexed contradictions between explicitly reviewed component concepts.

Unknown Russian wording is not forced into a concept. Missing concepts alone
are not proof of substitution. A rejection requires an additional, unrelated
known object and a missing known source object.
"""
from app.glossary.models import entry_metadata
from collections import OrderedDict
import json
import re


def folded(text):
    return ' '.join(text.casefold().replace('ё','е').split())


class ObjectGuard:
    def __init__(self):
        self.cache = OrderedDict()

    def index(self, snapshot, forms):
        key = snapshot.signature
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        source, single, multiple, complete = {}, {}, {}, {}
        for entry in snapshot.entries:
            meta = entry_metadata(entry)
            concept = meta.get('concept_id')
            form = forms.get(entry.source_term)
            if (not concept or not form or entry.trust < .8
                    or meta.get('semantic_role') in {'quantity','diagnostic_relation'}
                    or meta.get('label_only')
                    or entry.status not in ('BUILTIN','REVIEWED','CONFIRMED')
                    or str(meta.get('type','')).upper() not in ('TERM','COMPOUND')):
                continue
            if entry.source_term in {'部件','组件','零件','元件','系统','部分'}:
                continue  # Generic collectives cannot identify a replaced component.
            source.setdefault(concept,set()).update((entry.source_term,*entry.variants))
            for field in ('nominative','genitive','accusative','instrumental','locative','dative'):
                text = folded(form.get(field,form.get('base','') if field=='nominative' else ''))
                words = text.split()
                if not words:
                    continue
                complete.setdefault(concept,set()).add(text)
                if len(words) == 1:
                    single.setdefault(text,set()).add(concept)
                else:
                    multiple.setdefault(tuple(words[:2]),set()).add((text,concept))
        result = source, single, multiple, complete
        self.cache[key] = result
        while len(self.cache) > 12:
            self.cache.popitem(last=False)
        return result

    def violations(self, request, target, forms):
        snapshot = request.knowledge_snapshot
        if snapshot is None:
            return ()
        sources, single, multiple, complete = self.index(snapshot,forms)
        matches = snapshot.candidates(request.text,request.domain,request.context,set())
        from app.glossary.engine import GlossaryEngine
        matches = GlossaryEngine.reviewed_context_matches(request.text,matches,request)
        if request.context_router is not None:
            matches = request.context_router.ranked(matches,request)
        source_concepts = {entry_metadata(m.entry).get('concept_id') for m in matches
                           if m.entry.trust >= .8 and entry_metadata(m.entry).get('review_status')=='VERIFIED'}
        groups = {}
        for match in matches:
            concept = entry_metadata(match.entry).get('concept_id')
            if concept in sources:
                groups.setdefault((match.start,match.end),[]).append((concept,match))
        expected, occupied, retained_spans = {}, set(), []
        text = folded(target)
        # A retained whole reviewed compound protects its nested source nouns,
        # including old labels with no separate case-form record. Otherwise
        # inserted positional adjectives can look like a missing parent noun.
        for match in sorted(matches,key=lambda m:-(m.end-m.start)):
            meta = entry_metadata(match.entry)
            form=forms.get(match.entry.source_term,{})
            phrases={folded(match.entry.target_term)}
            phrases.update(folded(form[field]) for field in
                ('nominative','genitive','accusative','instrumental','locative','dative') if form.get(field))
            if (match.entry.trust >= .8 and meta.get('review_status')=='VERIFIED'
                    and str(meta.get('type','')).upper() in ('TERM','COMPOUND','PHRASE')
                    and any(re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',text) for phrase in phrases)):
                retained_spans.append((match.start,match.end))
        for (start,end), alternatives in sorted(groups.items(),key=lambda item: -(item[0][1]-item[0][0])):
            if any(a <= start and b >= end for a,b in retained_spans):
                continue
            if len({concept for concept,_ in alternatives}) != 1:
                continue
            concept, match = alternatives[0]
            positions = set(range(start,end))
            if not positions & occupied:
                expected[concept] = request.text[match.start:match.end]
                occupied |= positions
        if not expected:
            return ()
        words = list(re.finditer(r'\w+', text))
        candidates = []
        for i, word in enumerate(words):
            if word.group() in single and len(single[word.group()]) == 1:
                candidates.append((word.start(),word.end(),next(iter(single[word.group()]))))
            if i+1 == len(words):
                continue
            pair = word.group(), words[i+1].group()
            options = multiple.get(pair,())
            by_phrase = {}
            for phrase,concept in options:
                by_phrase.setdefault(phrase,set()).add(concept)
            for phrase,concepts in by_phrase.items():
                end = word.start()+len(phrase)
                if (len(concepts)==1 and text.startswith(phrase,word.start())
                        and (end==len(text) or not text[end].isalnum())):
                    candidates.append((word.start(),end,next(iter(concepts))))
        rendered, occupied = set(), set()
        for start,end,concept in sorted(candidates,key=lambda s: -(s[1]-s[0])):
            positions = set(range(start,end))
            if not positions & occupied:
                rendered.add(concept)
                occupied |= positions
        # A complete reviewed rendering proves retention even if another source
        # concept shares the same Russian phrase. Do not infer a competing sense.
        for concept in expected:
            if any(re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',text)
                   for phrase in complete[concept]):
                rendered.add(concept)
        missing, extra = set(expected)-rendered, rendered-(set(expected)|source_concepts)
        reasons = []
        for concept in sorted(missing):
            # A known parent component within a compound is not a replacement.
            unrelated = {other for other in extra if not any(alias in expected[concept]
                         for alias in sources[other]) and not any(
                         parent in whole for parent in complete[other] for whole in complete[concept])}
            if unrelated:
                reasons.append('object:'+concept+':'+','.join(sorted(unrelated)))
        return tuple(reasons)
