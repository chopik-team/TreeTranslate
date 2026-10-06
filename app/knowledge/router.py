"""Job-bounded contextual official snapshots over the existing glossary pipeline."""
from app.glossary.models import entry_metadata
from collections import Counter, OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import re
from dataclasses import replace
from time import perf_counter
from functools import lru_cache
from types import MappingProxyType

from app.config.paths import ASSETS_DIR
from app.glossary.models import TermMatch
from app.glossary.normalization import normalize,mapped,boundary
from app.glossary.repository import model
from app.glossary.constraints import validate_result
from app.glossary.errors import ConstraintFailure,GlossaryError
from .profile import DocumentProfiler,ContextProfile
from .segments import SegmentClassifier
from app.documents.run_metrics import measure


@lru_cache(maxsize=1024)
def compiled_template(source):
    parts=re.split(r'(\{[A-Z]\})',source)
    slots=tuple(p[1:-1] for p in parts if re.fullmatch(r'\{[A-Z]\}',p))
    if not 0<=len(slots)<=3 or len(set(slots))!=len(slots):return None
    pattern=''.join('(.{1,128}?)' if re.fullmatch(r'\{[A-Z]\}',p) else r'\s{1,8}' if p.isspace() else
        ''.join(re.escape(c)+r'\s{0,8}' for c in normalize(p) if not c.isspace()) for p in parts)
    return re.compile(pattern),slots


@dataclass(frozen=True)
class KnowledgeSnapshot:
    signature: str
    profile: object
    entries: tuple
    exact: object
    prefixes: object
    concepts: object
    stores: tuple
    packs: tuple
    bytes_estimate: int

    def candidates(self,text,domain,context,suppressed,limit=512):
        folded,positions=mapped(text,fold=True)
        output=[];seen=set()
        exact_key=folded.strip()
        exact_rows=self.exact.get(exact_key,())
        if exact_rows:
            starts=[(len(folded)-len(folded.lstrip()),tuple((exact_key,e,s) for e,s in exact_rows))]
        else:
            starts=((i,self.prefixes.get(char,())) for i,char in enumerate(folded))
        for start,rows in starts:
            for token,entry,store in rows:
                if not folded.startswith(token,start):continue
                end=start+len(token);a,b=positions[start][0],positions[end-1][1]
                if entry.context and entry.context!=context:continue
                if (entry.domain,normalize(entry.source_term,fold=True)) in suppressed:continue
                if text[a:b].endswith('孔') and text[b:b+1] in {'径','距'}:continue
                if entry.case_sensitive and normalize(text[a:b]) not in {normalize(t) for t in (entry.source_term,*entry.variants)}:continue
                if entry.whole_word and not boundary(text,a,b,text[a:b]):continue
                concept=entry_metadata(entry).get('concept_id')
                group=self.concepts.get(concept,())
                identity=(a,b,concept if group else entry.id,entry.target_term,store)
                if identity in seen:continue
                seen.add(identity)
                output.append(TermMatch(a,b,entry,store))
                if len(output)>limit:raise ConstraintFailure('candidate_budget')
        return tuple(output)


class KnowledgeRouter:
    def __init__(self,glossary):
        self.glossary=glossary;self.profiler=DocumentProfiler();self.cache=OrderedDict()
        self.metrics=Counter();self.documents=[];self.snapshots=[];self.decisions=[]
        self.document_metrics={}
        self.templates=json.loads((ASSETS_DIR/'config/knowledge-templates.json').read_text('utf-8'))['templates']
        self.slot_forms={f['source']:f for f in json.loads((ASSETS_DIR/'config/automotive-slot-forms.json').read_text('utf-8'))['forms']}

    def profile(self,source,target,**kwargs):
        started=perf_counter()
        purpose=kwargs.pop('purpose','document')
        try:profile=self.profiler.profile(source,target,**kwargs)
        except Exception:
            self.metrics['profile_failures']+=1
            profile=ContextProfile(source,target,'general',(),(),(),(),(),'fallback')
        self.metrics[purpose+'_profile_time']+=perf_counter()-started
        self.documents.append(dict(profile.summary(),purpose=purpose));return profile

    @measure('knowledge_snapshot')
    def snapshot(self,profile):
        try:return self._snapshot(profile)
        except Exception:
            self.metrics['snapshot_failures']+=1
            return None

    def _snapshot(self,profile):
        if self.glossary is None:return None
        versions=tuple((str(db.path),db.path.stat().st_size,db.path.stat().st_mtime_ns) for db in self.glossary.builtins)
        manifest=json.loads((ASSETS_DIR/'knowledge/manifest.json').read_text('utf-8'))
        checksums=tuple((p['file'],p.get('sha256',p.get('pack_sha256','')),p.get('version','')) for p in manifest['packs'])
        key=(profile.identity,profile.version,profile.source_language,profile.target_language,versions,checksums)
        if key in self.cache:
            self.metrics['snapshot_cache_hits']+=1
            value=self.cache.pop(key);self.cache[key]=value;return value
        started=perf_counter();entries=[];stores=[];prefixes={};exact={};concepts={};packs=set()
        branches={b.split('.',1)[1] for b,s in profile.subdomains if b.startswith(profile.primary_domain+'.')}
        if any(b.startswith('body.') for b in branches):branches.add('body')
        if 'body' in branches:
            # A supported parent family admits its descendants. Sampling is
            # bounded, so an unseen door label must not disappear from a body PDF.
            taxonomy=json.loads((ASSETS_DIR/'config/knowledge-taxonomy.json').read_text('utf-8'))
            branches.update('body.'+name for name in taxonomy['automotive']['body'])
        branches.update({'common','general'})
        # The small curated official index is materialized once. Legacy packs
        # retain their bounded hashed SQL lookup instead of copying huge lexicons.
        for i,db in enumerate(self.glossary.builtins):
            store=f'builtin:{i}'
            try:
                with db.connect() as con:
                    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_context_index'").fetchone():continue
                    marks=','.join('?' for _ in branches)
                    # Split domains so the complete context-selection index is
                    # used instead of scanning every row of a language pair.
                    rows=con.execute(f'''SELECT e.* FROM entries e JOIN (
                        SELECT entry_id FROM knowledge_context_index
                        WHERE source_language=? AND target_language=? AND domain='general'
                        UNION SELECT entry_id FROM knowledge_context_index
                        WHERE source_language=? AND target_language=? AND domain=? AND subdomain IN ({marks})
                        LIMIT 2049) k ON e.id=k.entry_id''',
                        (profile.source_language,profile.target_language,profile.source_language,profile.target_language,profile.primary_domain,*sorted(branches))).fetchall()
                    if len(rows)>2048:
                        self.metrics['snapshot_budget_fallback']+=1;continue
                    stores.append(store)
                    for row in rows:
                        entry=model(row)
                        if entry.status in ('AUTO','REJECTED','DISABLED'):continue
                        entries.append(entry);packs.add(entry.source_pack)
                        meta=entry_metadata(entry);concept=meta.get('concept_id',str(entry.id))
                        concepts.setdefault(concept,[]).append(entry)
                        for surface in (entry.source_term,*entry.variants):
                            token=normalize(surface,fold=True)
                            exact.setdefault(token,[]).append((entry,store))
                            if token:prefixes.setdefault(token[0],[]).append((token,entry,store))
            except (GlossaryError,ValueError):
                self.metrics['snapshot_failures']+=1
        signature=sha256(repr(key).encode()).hexdigest()
        size=sum(len(repr(e).encode('utf-8'))+64 for e in entries)
        value=KnowledgeSnapshot(signature,profile,tuple(entries),MappingProxyType({k:tuple(v) for k,v in exact.items()}),
            MappingProxyType({k:tuple(sorted(v,key=lambda r:-len(r[0]))) for k,v in prefixes.items()}),
            MappingProxyType({k:tuple(v) for k,v in concepts.items()}),tuple(stores),tuple(sorted(packs)),size)
        self.cache[key]=value
        while len(self.cache)>12:self.cache.popitem(last=False)
        self.metrics['snapshot_build_time']+=perf_counter()-started
        self.snapshots.append(dict(signature=signature,profile=profile.identity,entries=len(entries),concepts=len(concepts),
            packs=value.packs,stores=value.stores,bytes_estimate=size,subdomains=sorted(branches)))
        return value

    def ranked(self,matches,request):
        """Public explainable score; explicit user/installable rules stay intact."""
        started=perf_counter();out=[]
        for match in matches:
            if match.store not in request.knowledge_snapshot.stores:
                out.append(match);continue
            entry=match.entry;meta=entry_metadata(entry)
            exact=normalize(request.text)==normalize(request.text[match.start:match.end])
            domain=entry.domain in ('general',request.domain)
            own={b.partition('.')[2] or b for b,_ in request.context_profile.subdomains}
            if any(b.startswith('body.') for b in own):own.add('body')
            scope=set(meta.get('subdomains',['general']))
            direct_scope=bool(scope & (own|{'common','general'}))
            parent_scope=any(branch.startswith(parent+'.') for branch in scope for parent in own)
            subdomain=direct_scope or parent_scope
            typed=self.type_match(request.segment_type,meta.get('segment_types',[]))
            alias=normalize(request.text[match.start:match.end])!=normalize(entry.source_term)
            factors=dict(exactness=.30 if exact else .20,trust=.20*entry.trust,domain=.20*domain,
                         subdomain=.15*subdomain,segment_type=.10*typed,specificity=.05*min(1,len(entry.source_term)/4),
                         priority=.02*min(1,max(0,entry.priority)/100),alias_penalty=-.02*alias,
                         parent_distance=-.02 if parent_scope and not direct_scope else 0.)
            score=round(sum(factors.values()),4)
            if not domain or not subdomain:
                self.metrics['wrong_domain_rejections']+=1;continue
            level='HIGH' if score>=.86 else 'MEDIUM' if score>=.65 else 'LOW'
            if level=='LOW':continue
            out.append(match)
            if len(self.decisions)<4096:self.decisions.append(dict(entry_id=entry.id,concept_id=meta.get('concept_id'),
                segment_type=request.segment_type,score=score,level=level,factors=factors,profile=request.context_profile.identity))
        self.metrics['match_scoring_time']+=perf_counter()-started
        # Competing contextual senses are compared only against the same span;
        # an equal-confidence mixed context remains ambiguous and uses NMT.
        groups={}
        for match in out:
            if match.store not in request.knowledge_snapshot.stores:continue
            groups.setdefault((match.start,match.end),[]).append(match)
        remove=set();scores=dict(request.context_profile.subdomains)
        for span,rows in groups.items():
            if len({m.entry.target_term for m in rows})<2:continue
            weighted=[(max((scores.get(request.domain+'.'+b,0) for b in entry_metadata(m.entry).get('subdomains',[])),default=0),m) for m in rows]
            best=max(s for s,m in weighted)
            winners={m.entry.target_term for s,m in weighted if s==best}
            for score,match in weighted:
                if score<best or len(winners)>1:remove.add(id(match))
            self.metrics['contextual_polysemy_resolutions']+=len(winners)==1
            self.metrics['ambiguous_concepts']+=len(winners)>1
        return tuple(m for m in out if id(m) not in remove)

    def allow_bypass(self,match,request):
        entry=match.entry;meta=entry_metadata(entry)
        own={b.partition('.')[2] or b for b,_ in request.context_profile.subdomains}
        if any(b.startswith('body.') for b in own):own.add('body')
        scope=set(meta.get('subdomains',['general']))
        direct=bool(scope & (own|{'common','general'}))
        inherited=any(b.startswith(p+'.') for b in scope for p in own)
        if entry.domain not in ('general',request.domain) or not (direct or inherited):return False
        typed=self.type_match(request.segment_type,meta.get('segment_types',[]))
        alias=normalize(request.text[match.start:match.end])!=normalize(entry.source_term)
        score=.30+.20*entry.trust+.20+.15+.10*typed+.05*min(1,len(entry.source_term)/4)+.02*min(1,max(0,entry.priority)/100)
        score-=.02*alias+.02*(inherited and not direct)
        return score>=.86

    @staticmethod
    def type_match(kind,types):
        nominal={'TITLE','HEADING','FILENAME','FOLDER_NAME','TABLE_HEADER','TABLE_CELL','DIAGRAM_LABEL','COMPONENT_LABEL'}
        return not types or kind in types or kind in nominal and bool(nominal.intersection(types))

    def template(self,request,matches):
        started=perf_counter()
        try:
            result=self._template_match(request,matches)
            if result:return result
            # One existing block, at most four source sentences. Never fetch
            # a missing continuation from another line or a neighbouring cell.
            if any(m.store=='user' for m in matches):return None
            source=request.text.strip();heading=None;bullet=''
            # A list marker decorates an existing complete source clause; it
            # must survive rendering and cannot supply a missing continuation.
            if source.startswith('• '):
                bullet='• ';source=source[2:].strip()
                item=self._template_match(replace(request,text=source),matches)
                if item:return bullet+item[0],item[1]
            prefix=re.fullmatch(r'([^\s。]{1,24}(?:\s*\([A-Z]{1,8}[\'′″]*\))?)\s+(.+)',source,re.S)
            if prefix:
                label=self.glossary.full_segment(replace(request,text=prefix[1],segment_type='HEADING'))
                label_text=label.translated_text if label else None
                if label_text is None:
                    marked=self._template_match(replace(request,text=prefix[1],segment_type='COMPONENT_LABEL'),matches,context_text=request.text)
                    label_text=marked[0] if marked else None
                if label_text:
                    heading=label_text
                    heading=heading[0].upper()+heading[1:]
                    source=prefix[2].strip()
            clauses=re.findall(r'[^。]+。',source)
            # PDF heading regions may contain a known caption and complete
            # prose sentences. Only a verified caption permits clause routing;
            # unknown or incomplete text still rejects the entire block.
            prose_heading=request.segment_type=='HEADING' and heading is not None
            clause_request=replace(request,segment_type='PROSE') if prose_heading else request
            if (request.segment_type not in {'WARNING','PROSE','PROCEDURE_STEP','CONDITION'} and not prose_heading
                    or not 1<=len(clauses)<=4 or ''.join(clauses)!=source
                    or len(clauses)==1 and heading is None and not re.search(r'[,，]\s*而',source)):
                return None
            accepted_keys=['template_hits','successful_template_translation','model_saved_calls']
            accepted_before={key:self.metrics[key] for key in accepted_keys}
            translated=[];rules=[]
            for clause in clauses:
                item=self._template_match(replace(clause_request,text=clause.strip()),matches,context_text=request.text)
                if item:
                    translated.append(item[0]);rules.append(item[1]);continue
                coordinated=re.split(r'[,，]\s*而',clause)
                items=[]
                if len(coordinated)==2:
                    items=[self._template_match(replace(clause_request,text=part.strip().rstrip('。')+'。'),matches,context_text=request.text)
                           for part in coordinated]
                if not items or any(item is None for item in items):
                    for key,value in accepted_before.items():self.metrics[key]=value
                    return None
                translated.extend([items[0][0],'При этом '+items[1][0][0].lower()+items[1][0][1:]])
                rules.extend(item[1] for item in items)
            target=bullet+(heading+'\n' if heading else '')+' '.join(translated)
            from .relations import negative_relation
            for key,value in accepted_before.items():self.metrics[key]=value
            if not negative_relation(request.text,target):return None
            try:target=validate_result(request.text,target)
            except ConstraintFailure:return None
            self.metrics['composed_templates']+=1
            for key,value in accepted_before.items():self.metrics[key]=value+1
            return target,'compose:'+','.join(rules)
        finally:self.metrics['template_time']+=perf_counter()-started

    def _template_match(self,request,matches,*,context_text=None):
        if request.knowledge_snapshot is None or len(request.text)>512:return None
        if any(m.store=='user' for m in matches):return None
        candidates=[]
        # Scope anchors remain in the same physical source block when its
        # complete clauses are rendered separately. Validation uses each clause.
        scope_request=replace(request,text=context_text) if context_text is not None else request
        normalized,spans=mapped(request.text)
        offset=len(normalized)-len(normalized.lstrip())
        for rule in self.templates:
            if rule['status']!='VERIFIED' or rule['domain'] not in (request.domain,'general.technical.procedure') or request.segment_type not in rule['types']:continue
            own={b.split('.',1)[1] for b,_ in request.context_profile.subdomains}
            if rule['subdomains'] and not own.intersection(rule['subdomains']):
                self.metrics['context_rejection']+=1;continue
            compiled=compiled_template(rule['source'])
            if compiled is None:continue
            pattern,slots=compiled
            match=pattern.fullmatch(normalized.strip())
            if not match:continue
            self.metrics['template_candidates']+=1
            values={};valid=True
            for slot_index,(slot,source) in enumerate(zip(slots,match.groups()),1):
                source=source.strip()
                form=rule['forms'][slot]
                if form in {'coordinated_nouns','condition_list'}:
                    parts=re.split(r'[、,，]|和|或' if form=='condition_list' else r'[、,，]|和',source)
                    values_list=[]
                    if not 2<=len(parts)<=(8 if form=='condition_list' else 6):valid=False;break
                    for part in parts:
                        value=self._noun_slot(part,slot,rule,scope_request,rule['list_cases'][slot])
                        if value is None:valid=False;break
                        values_list.append(value)
                    if not valid:break
                    values[slot]=', '.join(values_list[:-1])+(' или ' if form=='condition_list' else ' и ')+values_list[-1]
                    continue
                if form=='reviewed_condition':
                    value=rule.get('slot_values',{}).get(source)
                    if not value:
                        valid=False;self.metrics['unknown_slot']+=1;break
                    values[slot]=value;continue
                if form=='protected':
                    from app.documents.pdf_ocr_policy import protected_kind
                    number=re.fullmatch(r'\d+(?:[.,]\d+)?(?:[-–]\d+(?:[.,]\d+)?)?\s*(?:%|mm|cm|kPa|MPa|°C|L)',source)
                    if slot=='N' and not number:valid=False;break
                    if not (protected_kind(source) or number):valid=False;break
                    a,b=match.span(slot_index)
                    values[slot]=request.text[spans[a+offset][0]:spans[b+offset-1][1]].strip();continue
                literal=''
                if rule.get('component_marker'):
                    tagged=re.fullmatch(r'(.+?)\s*(\([A-Z]{1,8}[\'′″]*\))',source)
                    if tagged:source,literal=tagged.groups();source=source.strip()
                value=self._noun_slot(source,slot,rule,scope_request,form)
                if value is None:valid=False;break
                values[slot]=value+(' '+literal if literal else '')
            if valid:
                target=rule['target']
                for slot,value in values.items():target=target.replace('{'+slot+'}',value)
                if rule.get('capitalize') and target:target=target[0].upper()+target[1:]
                try:target=validate_result(request.text,target)
                except ConstraintFailure:continue
                if rule.get('negative_relation'):
                    from .relations import negative_relation
                    if not negative_relation(request.text,target):
                        self.metrics['negation_guard_rejection']+=1;continue
                candidates.append((target,rule['id']))
                self.metrics['template_matches']+=1
            else:self.metrics['template_rejections']+=1
        # Identical reviewed renderings are one semantic result; conflicting
        # renderings still fail closed rather than selecting an arbitrary rule.
        candidates=list({target:(target,uid) for target,uid in candidates}.values())
        if len(candidates)!=1:
            if len(candidates)>1:self.metrics['ambiguous_candidates']+=1
            return None
        self.metrics['template_hits']+=1
        self.metrics['successful_template_translation']+=1
        self.metrics['model_saved_calls']+=1
        return candidates[0]

    def _noun_slot(self,source,slot,rule,request,form):
        allowed=rule.get('slot_allowed',{}).get(slot,rule['allowed_slots'])
        # Only a whole declared noun may normalize intra-block spacing. Two
        # competing declared spellings remain ambiguous rather than guessed.
        compact=lambda text: ''.join(normalize(text,fold=True).split())
        nouns=[noun for noun in allowed if compact(noun)==compact(source)]
        if len(nouns)!=1:
            self.metrics['unknown_slot']+=1;return None
        noun=nouns[0]
        entries=request.knowledge_snapshot.exact.get(normalize(noun,fold=True),())
        entries=[(e,s) for e,s in entries if self.glossary.reviewed_context_allowed(e,s,noun,request.text,request)]
        targets={e.target_term.casefold() for e,_ in entries if e.trust>=.8 and e.mode=='PREFERRED'
                 and e.status in ('BUILTIN','REVIEWED','CONFIRMED')}
        if len(targets)!=1:
            self.metrics['ambiguous_candidates']+=1;self.metrics['ambiguous_slot']+=1;return None
        value=next(iter(targets))
        if form!='nominative':
            value=rule.get('slot_forms',{}).get(noun,{}).get(form) or (self.slot_forms.get(noun,{}).get(form) if rule.get('shared_forms') else None)
        # Preserve an OEM acronym at the start of a reviewed noun/form.
        # Lowercasing ECM to eCM invalidates the protected source identifier.
        if value and re.match(r'[A-Z][A-Z0-9]{1,}(?=\W|$)',value):return value
        return value[0].lower()+value[1:] if value else None

    def clear(self):
        self.cache.clear();self.profiler.clear()

    def summary(self):
        return dict(metrics=dict(self.metrics),profiles=self.documents,snapshots=self.snapshots,
                    decisions=self.decisions,document_metrics={k:dict(v) for k,v in self.document_metrics.items()},
                    profile_cache_size=len(self.profiler.cache),snapshot_cache_size=len(self.cache))
