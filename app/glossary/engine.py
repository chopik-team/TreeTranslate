from collections import OrderedDict,Counter
from dataclasses import replace
from functools import lru_cache
import json
import logging
import os
import re
from pathlib import Path
from threading import RLock
from time import perf_counter

from app.config.paths import APP_DATA_DIR,ASSETS_DIR
from app.documents.run_metrics import measure
from app.engine.types import TranslationResult
from app.engine.backends.base_backend import check_cancelled
from app.engine.errors import TranslationError,TranslationCancelledError
from .database import Database
from .repository import Repository
from .matcher import candidates
from .ranking import resolve
from .normalization import normalize
from .models import entry_metadata
from .placeholders import PlaceholderCodec
from .constraints import validate_result,forbidden_found
from .errors import GlossaryError,ConstraintFailure
from .hot_cache import ByteLRU,ABSENT
from .cache_plan import GlossaryCachePlan


class GlossaryEngine:
    def __init__(self,path=None,*,builtin_paths=(),config=None,warning=None):
        self.config=json.loads((ASSETS_DIR/'config/glossary.json').read_text('utf-8'));self.config.update(config or {})
        self.db=Database(path or os.environ.get('TREETRANSLATE_GLOSSARY_PATH') or APP_DATA_DIR/'glossary.db',timeout_ms=self.config['busy_timeout_ms'],persistent_reads=True)
        self.repository=Repository(self.db)
        self.builtins=[Database(p,readonly=True,persistent_reads=True) for p in builtin_paths]
        self.cache=OrderedDict();self.indexes=OrderedDict();self.lock=RLock()
        self.warning=warning or (lambda text:None);self.last_warning=None;self.disabled=False
        self.counters=Counter({k:0 for k in ('hits','full_segment_hits','constraint_hits','fallbacks','placeholder_failures')})
        self.codec=PlaceholderCodec(self.config['placeholder_policy'])
        db_bytes=sum(db.path.stat().st_size for db in self.builtins if db.path.is_file())
        self.cache_plan=GlossaryCachePlan.detect(db_bytes or 16*1024**2)
        self.lexical=ByteLRU(self.cache_plan.lexical_bytes)
        self._pack_databases={}
        from .normalization import configure_cache
        configure_cache(self.cache_plan.normalization_bytes)
        self._pressure_checks=0

    def close(self):
        with self.lock:
            for db in [self.db,*self.builtins,*self._pack_databases.values()]:db.close()

    def cache_metrics(self):
        from .normalization import cache_info
        return dict(lexical=self.lexical.summary(),normalization=cache_info(),final_entries=len(self.cache))

    def _memory_pressure(self):
        # No new monitoring thread. Check periodically in existing execution.
        self._pressure_checks+=1
        if self._pressure_checks%128:return
        import psutil
        if psutil.virtual_memory().available<self.cache_plan.reserve_bytes:
            self.lexical.resize(0);self.cache.clear();self.indexes.clear()
            from .normalization import configure_cache
            configure_cache(0)

    def remember_term(self,*args,**kw):return self.repository.remember_term(*args,**kw)

    def notice(self,code):
        self.last_warning='Терминология не применена полностью; проверьте перевод.' if code=='constraint' else 'Глоссарий временно недоступен; перевод без него продолжается.'
        logging.getLogger('treetranslate.glossary').warning('glossary warning code=%s',code)
        self.warning(self.last_warning)

    def retry(self):
        self.close();self.disabled=False;self.db.ready=False;self.cache.clear();self.indexes.clear();self.lexical.clear();self.last_warning=None

    def _stores(self,con):
        stores=[('user',self.db)] if self.config['user_enabled'] else []
        active_paths=set()
        if self.config['builtin_enabled']:
            stores.extend((f'builtin:{i}',db) for i,db in enumerate(self.builtins))
            for row in con.execute('SELECT pack_id,path FROM packs WHERE enabled=1'):
                path=row['path']
                active_paths.add(path)
                if path not in self._pack_databases:
                    self._pack_databases[path]=Database(path,readonly=True,persistent_reads=True)
                stores.append((row['pack_id'],self._pack_databases[path]))
        for path in self._pack_databases.keys()-active_paths:
            self._pack_databases.pop(path).close()
        return stores

    def prefetch(self,texts,source_language,target_language,domain='general',context=''):
        """Warm bounded raw rows only; never preselect, rank, or constrain.

        Keep each original 300-hash query intact: its LIMIT/budget and SQLite
        row order are part of the existing candidate-retrieval contract.
        """
        from .matcher import fragments,records
        if not self.config['enabled'] or self.disabled or not self.cache_plan.prefetch_batch_items:return
        with self.lock:
            self._memory_pressure()
            if not self.lexical.budget:return
            unique=list(dict.fromkeys(texts))[:self.cache_plan.prefetch_batch_items]
            self.lexical.stats['prefetch_calls']+=1
            self.lexical.stats['prefetch_unique_sources']+=len(unique)
            pair=source_language.lower()+'>'+target_language.lower();used=0;seen=set()
            queries_before=self.lexical.stats['sql_queries']
            try:
                with self.db.connect() as con:stores=self._stores(con)
                for name,db in stores:
                    identity,revision=db.revision_state();namespace=name,identity,revision
                    lengthkey=('lengths',namespace,pair,domain,self.config['max_term_length'])
                    lengths=self.lexical.get(lengthkey)
                    if lengths is ABSENT:
                        with db.connect() as con:
                            lengths=tuple(r[0] for r in con.execute('SELECT DISTINCT length FROM lengths WHERE pair=? AND domain IN (?,?)',
                                (pair,domain,'general')) if r[0]<=self.config['max_term_length'])
                        self.lexical.put(lengthkey,lengths,256+len(repr(lengthkey))*2+len(lengths)*32)
                    if not lengths:continue
                    for text in unique:
                        if not text or len(text)>20000:continue
                        try:hashes=list(fragments(text,lengths,self.config['max_lookup_fragments']))
                        except ConstraintFailure:continue
                        for offset in range(0,len(hashes),300):
                            chunk=hashes[offset:offset+300];size=len(chunk)*96+512
                            if used+size>self.cache_plan.document_prefetch_bytes:return
                            used+=size;seen.update(chunk)
                            with db.connect() as con:
                                try:records(con,pair,domain,chunk,self.config['max_candidates'],self.lexical,namespace)
                                except ConstraintFailure:continue
            except GlossaryError:
                pass # Canonical lookup performs the original storage fallback.
            finally:
                self.lexical.stats['prefetch_unique_hashes']+=len(seen)
                self.lexical.stats['prefetch_sql_queries']+=self.lexical.stats['sql_queries']-queries_before

    @staticmethod
    def reviewed_context_allowed(entry, store, surface, text, request):
        if store == 'user':
            return True
        meta = entry_metadata(entry)
        profile = getattr(request, 'context_profile', None)
        branches = {name.partition('.')[2] or name for name, _ in profile.subdomains} if profile else set()
        facts = set(getattr(profile, 'semantic_facts', ()))
        if meta.get('required_subdomains') and not branches.intersection(meta['required_subdomains']):
            return False
        if not set(meta.get('required_semantic_facts', ())).issubset(facts):
            return False
        anchors = meta.get('required_context_terms', ())
        if anchors and not any(anchor in text for anchor in anchors):
            return False
        anchors = meta.get('alias_context_terms', {}).get(surface, ())
        if anchors and not any(anchor in text for anchor in anchors):
            return False
        if surface in meta.get('reference_only_aliases', ()) and getattr(request, 'segment_type', '') != 'CROSS_REFERENCE':
            return False
        return True

    @staticmethod
    def reviewed_context_matches(text, matches, request):
        """Opt-in official senses require evidence in the current context.

        A document topic alone cannot turn an oil leak into a brake-fluid leak.
        User terminology retains its existing priority and scope.
        """
        return [m for m in matches if GlossaryEngine.reviewed_context_allowed(
            m.entry, m.store, text[m.start:m.end], text, request)]

    @measure('glossary_lookup')
    def lookup(self,text,source_language,target_language,domain='general',context='',*,snapshot=None,request=None):
        started=perf_counter()
        source_language=source_language.lower();target_language=target_language.lower()
        if not self.config['enabled'] or self.disabled or not text or len(text)>20000:return ()
        with self.lock:
            try:
                self._memory_pressure()
                with self.db.connect() as con:
                    revision=con.execute('SELECT revision FROM metadata').fetchone()[0]
                    stores=self._stores(con)
                    if snapshot is not None:
                        stores=[(name,db) for name,db in stores if name not in snapshot.stores]
                    suppressed={(r['domain'],r['source']) for r in con.execute('SELECT domain,source FROM suppressions WHERE pair=? AND domain IN (?,?)',(source_language+'>'+target_language,domain,'general'))}
                revisions=[]
                for name,db in stores:
                    identity,store_revision=db.revision_state()
                    revisions.append((name,identity,store_revision))
                pair=source_language+'>'+target_language
                profile = getattr(request, 'context_profile', None)
                forms_key=()
                if source_language=='zh' and target_language=='ru' and request is not None and request.context_router is not None:
                    from app.knowledge.qualifiers import FLUIDS
                    forms_key=tuple((noun,repr(request.context_router.slot_forms.get(noun))) for noun in sorted(FLUIDS))
                cachekey=(text,pair,domain,context,revision,tuple(revisions),tuple(sorted(self.config.items())),
                          snapshot.signature if snapshot else '',request.segment_type if request else '',
                          tuple(profile.subdomains) if profile else (), getattr(profile,'semantic_facts',()),
                          self.db.identity(),request.text if request else '',
                          (profile.identity,profile.version) if profile else (),forms_key)
                if cachekey in self.cache:
                    value=self.cache.pop(cachekey);self.cache[cachekey]=value
                    self.counters['hits']+=len(value)
                    return value
                matches=[]
                if snapshot is not None and self.config['builtin_enabled']:
                    matches.extend(snapshot.candidates(text,domain,context,suppressed,self.config['max_candidates']))
                for name,db in stores:
                    indexkey=(str(db.path),pair,domain,revision,tuple(revisions))
                    namespace=next(r for r in revisions if r[0]==name)
                    lengthskey=('lengths',namespace,pair,domain,self.config['max_term_length'])
                    lengths=self.lexical.get(lengthskey)
                    if lengths is not ABSENT and not lengths:continue
                    with db.connect() as con:
                        if indexkey not in self.indexes:
                            if lengths is ABSENT:
                                lengths=tuple(r[0] for r in con.execute('SELECT DISTINCT length FROM lengths WHERE pair=? AND domain IN (?,?)',(pair,domain,'general')) if r[0]<=self.config['max_term_length'])
                                self.lexical.put(lengthskey,lengths,256+len(repr(lengthskey))*2+len(lengths)*32)
                            self.indexes[indexkey]=lengths
                            while len(self.indexes)>self.config['compiled_index_cache_size']:self.indexes.popitem(last=False)
                        else:lengths=self.indexes[indexkey]
                        matches.extend(candidates(con,text,pair,domain,context,lengths,name,suppressed,self.config['max_candidates'],self.config['max_lookup_fragments'],
                            lexical_cache=self.lexical,namespace=namespace))
                matches = self.reviewed_context_matches(text, matches, request)
                if request is not None and snapshot is not None:
                    matches=request.context_router.ranked(matches,request) if hasattr(request,'context_router') else matches
                if (source_language=='zh' and target_language=='ru' and request is not None
                        and request.context_router is not None):
                    from app.knowledge.qualifiers import derived_constraints
                    derived = derived_constraints(text,matches,request.context_router.slot_forms)
                    matches = list(matches)+derived
                    self.counters['derived_fluid_constraints'] += len(derived)
                value=resolve(matches,domain)
                if len(value)>self.config['max_terms_per_segment']:raise ConstraintFailure('too_many_terms')
                self.counters['hits']+=len(value)
                self.cache[cachekey]=value
                while len(self.cache)>self.config['cache_size']:self.cache.popitem(last=False)
                return value
            except ConstraintFailure:
                self.notice('constraint');return ()
            except GlossaryError:
                self.disabled=True;self.notice('storage');return ()
            finally:
                if request is not None and request.context_router is not None:
                    elapsed=perf_counter()-started
                    request.context_router.metrics['knowledge_lookup_total']+=elapsed
                    if request.context_profile is not None:
                        request.context_router.document_metrics.setdefault(request.context_profile.identity,Counter())['knowledge_lookup_total']+=elapsed

    def constraints(self,source,source_language,target_language,domain='general',context=''):
        return self.codec.encode(source,self.lookup(source,source_language,target_language,domain,context))

    def full_segment(self,request,matches=None):
        matches=self.lookup(request.text,request.source_language,request.target_language,request.domain,request.context,
            snapshot=request.knowledge_snapshot,request=request) if matches is None else matches
        if self.config['full_segment_enabled'] and len(matches)==1:
            match=matches[0]
            if (request.knowledge_snapshot is not None and match.store in request.knowledge_snapshot.stores
                    and not request.context_router.allow_bypass(match,request)):
                return None
            if normalize(request.text)==normalize(request.text[match.start:match.end]) and match.entry.mode!='FORBIDDEN':
                target=request.text if match.entry.mode=='KEEP' else match.entry.target_term
                try:
                    introduced = entry_metadata(match.entry).get('introduced_identifiers', []) if match.store!='user' else []
                    # Only exact, explicitly reviewed labels may spell out an
                    # OEM identifier absent from a localized menu caption.
                    if introduced:
                        meta = entry_metadata(match.entry)
                        if (not meta.get('label_only') or meta.get('review_status')!='VERIFIED'
                                or any(not re.fullmatch('[A-Z]{2,12}',token) for token in introduced)):
                            return None
                    target=validate_result(request.text + ''.join(' '+token for token in introduced),target,
                                           match.entry.forbidden_target_variants)
                except ConstraintFailure:return None
                self.counters['full_segment_hits']+=1
                return TranslationResult(target,request.source_language,request.target_language,'glossary','none',0,
                    'GLOSSARY_FULL_SEGMENT',False,request.request_id,knowledge_source='glossary',glossary_hits_count=1,
                    pack_ids=self.pack_ids(matches),domain=request.domain,constraint_status='full_segment')
        # A list marker is formatting, not part of a reviewed instruction.
        # Match the whole remaining segment; never accept an arbitrary substring.
        numbered=re.fullmatch(r'(\s*\d+[.．、]\s*)(.+)',request.text,re.DOTALL)
        if numbered:
            prefix,body=numbered.groups()
            if re.match(r'\s*\d+[.．、]',body):return None
            result=self.full_segment(replace(request,text=body))
            if result:
                try:target=validate_result(request.text,prefix+result.translated_text)
                except ConstraintFailure:return None
                return replace(result,translated_text=target)
        return None

    @staticmethod
    def sentence_safe_matches(text,matches):
        """Opt-in pack metadata keeps labels usable without capitalized noun slots.

        User terminology and older packs retain their contract. Reviewed complete
        phrases still bypass above; unknown prose is left to the existing model.
        """
        short_label = not re.search(r'[,，。;；]',text) and len(text)<30
        safe=[]
        for match in matches:
            if match.store=='user':safe.append(match);continue
            try:metadata=json.loads(match.entry.notes)
            except (ValueError,TypeError):metadata={}
            if isinstance(metadata,dict) and metadata.get('label_only'):
                continue  # Exact labels bypass earlier; no ambiguous prose fragments.
            if short_label:
                safe.append(match)
                continue
            if isinstance(metadata,dict) and metadata.get('sentence_constraints') is False:
                # These short Chinese verbs/nouns are ambiguous inside compounds;
                # they remain available for exact labels, never fragment prose.
                if match.entry.source_term in {'测量','安装','固定','连接','孔','间隙','实际','高度','前部','后部','前端','后端'}:
                    continue
                target=match.entry.target_term
                if target and 0x410<=ord(target[0])<=0x42f:
                    match=replace(match,entry=replace(match.entry,target_term=target[0].lower()+target[1:]))
            safe.append(match)
        return tuple(safe)

    @staticmethod
    @lru_cache(maxsize=1)
    def grammatical_patterns():
        return json.loads((ASSETS_DIR/'config/automotive-grammar.json').read_text('utf-8'))['patterns']

    @staticmethod
    def grammatical_phrases(text,matches):
        """A bounded reviewed set of Russian service patterns, not morphology.

        Applies only to this pack's enforced noun slots, never user terminology.
        No global replacement of an unconstrained model output.
        """
        allowed={m.entry.target_term.casefold() for m in matches if m.store!='user' and m.entry.source_pack=='aw083-body-repair'}
        patterns=GlossaryEngine.grammatical_patterns()
        for term,rules in patterns.items():
            if term in allowed:
                for pattern,replacement in rules:text=re.sub(pattern,replacement,text,flags=re.I)
        return text

    @staticmethod
    def pack_ids(matches):return tuple(sorted({m.entry.source_pack or m.store for m in matches if m.store!='user'}))

    def translate(self,request,router,cancelled):
        if not self.disabled:self.last_warning=None
        matches=self.lookup(request.text,request.source_language,request.target_language,request.domain,request.context,
            snapshot=request.knowledge_snapshot,request=request)
        check_cancelled(cancelled)
        direct=self.full_segment(request,matches)
        if direct:return direct
        matches=self.sentence_safe_matches(request.text,matches)
        if not matches or not self.config['constraints_enabled']:
            return replace(router.translate(request,cancelled),domain=request.domain)
        plan=self.codec.encode(request.text,matches)
        if plan.mapping:
            try:
                result=router.translate(replace(request,text=plan.text),cancelled)
                check_cancelled(cancelled)
                restored=self.codec.restore(result.translated_text,plan)
                restored=self.grammatical_phrases(restored,matches)
                restored=validate_result(request.text,restored,plan.forbidden)
                self.counters['constraint_hits']+=len(plan.mapping)
                return replace(result,translated_text=restored,knowledge_source='glossary',glossary_hits_count=len(plan.mapping),
                               pack_ids=self.pack_ids(matches),domain=request.domain,constraint_status='enforced')
            except TranslationCancelledError:
                raise
            except ConstraintFailure as error:
                if str(error) in ('placeholder_integrity','unexpected_placeholder'):
                    self.counters['placeholder_failures']+=1
            except TranslationError:
                pass
        # Never guess missing tokens or globally replace translated words.
        if plan.mapping:
            self.counters['fallbacks']+=1;self.notice('constraint')
        result=router.translate(request,cancelled)
        forbidden=forbidden_found(result.translated_text,plan.forbidden)
        if forbidden:self.notice('constraint')
        status='forbidden_detected' if forbidden else ('fallback_unconstrained' if plan.mapping else 'forbidden_checked')
        return replace(result,glossary_hits_count=len(matches),pack_ids=self.pack_ids(matches),domain=request.domain,constraint_status=status)
