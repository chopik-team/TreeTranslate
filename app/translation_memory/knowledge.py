"""Shared pre-router knowledge boundary; glossary stays a separate extension point."""
from app.glossary.models import entry_metadata
from app.documents.run_metrics import measure,observe
from dataclasses import replace
from threading import Event
from time import perf_counter
from typing import Protocol
import re

from app.engine.backends.base_backend import check_cancelled
from app.engine.errors import InputTooLongError
from app.engine.types import TranslationResult
from app.engine.runtime.offline import offline_scope


class GlossaryProvider(Protocol):
    def constraints(self, source, source_language, target_language, domain): ...


class TranslationKnowledgeEngine:
    def __init__(self, router, memory, glossary=None):
        self.router, self.memory = router, memory
        self.glossary = glossary
        from app.glossary.domain_detection import DomainDetector
        self.domain_detector = DomainDetector(glossary) if glossary is not None else None
        from app.knowledge.router import KnowledgeRouter
        self.context_router = KnowledgeRouter(glossary)
        from app.knowledge.objects import ObjectGuard
        self.object_guard = ObjectGuard()
        self.last_context_metrics = {}

    def profile_document(self, source, target, **kwargs):
        return self.context_router.profile(source,target,**kwargs)

    def contextualize(self,request):
        if request.context_profile is None:return request
        snapshot=request.knowledge_snapshot or self.context_router.snapshot(request.context_profile)
        from app.knowledge.segments import SegmentClassifier
        return replace(request,domain=request.context_profile.primary_domain,knowledge_snapshot=snapshot,
            segment_type=request.segment_type or SegmentClassifier.classify(request.text).value,context_router=self.context_router)

    @measure('template_routing')
    def _template(self,request):
        if request.knowledge_snapshot is None or self.glossary is None:return None
        from app.knowledge.questions import compose as compose_question
        question = compose_question(request,self.context_router.slot_forms)
        if question is not None:
            self.context_router.metrics['composed_questions'] += 1
            return TranslationResult(question[0],request.source_language,request.target_language,'knowledge_template','none',0,
                'closed-diagnostic-question-v1',False,request.request_id,knowledge_source='template',domain=request.domain,
                pack_ids=request.knowledge_snapshot.packs,constraint_status='verified_closed_question',question_kind=question[1])
        from app.knowledge.directives import compose
        directive = compose(request,self.context_router.slot_forms)
        if directive is not None:
            self.context_router.metrics['composed_directives'] += 1
            return TranslationResult(directive[0],request.source_language,request.target_language,'knowledge_template','none',0,
                directive[1],False,request.request_id,knowledge_source='template',domain=request.domain,
                pack_ids=request.knowledge_snapshot.packs,constraint_status='verified_closed_directives')
        from app.knowledge.units import capacity_line
        capacity=capacity_line(request.text,request.source_language,request.target_language)
        if capacity is not None:
            self.context_router.metrics['unit_lines']+=1
            return TranslationResult(capacity,request.source_language,request.target_language,'knowledge_template','none',0,
                'aw088-capacity-literal',False,request.request_id,knowledge_source='template',domain=request.domain,
                pack_ids=request.knowledge_snapshot.packs,constraint_status='verified_literal_units')
        matches=self.glossary.lookup(request.text,request.source_language,request.target_language,request.domain,request.context,
                                    snapshot=request.knowledge_snapshot,request=request)
        try:result=self.context_router.template(request,matches)
        except (ValueError,TypeError,KeyError,re.error):
            self.context_router.metrics['template_failures']+=1;return None
        if result:
            self.context_router.document_metrics.setdefault(request.context_profile.identity,__import__('collections').Counter())['template_hits']+=1
            return TranslationResult(result[0],request.source_language,request.target_language,'knowledge_template','none',0,
                result[1],False,request.request_id,knowledge_source='template',domain=request.domain,
                pack_ids=request.knowledge_snapshot.packs,constraint_status='verified_template')

    def record_context_result(self,result,request):
        counts=self.context_router.metrics
        if request.context_profile is None:return
        from collections import Counter
        import json
        document=self.context_router.document_metrics.setdefault(request.context_profile.identity,Counter())
        if result.knowledge_source=='template':return
        if result.knowledge_source=='model':counts['model_fallbacks']+=1;document['model_fallbacks']+=1;return
        if result.knowledge_source=='glossary':
            key='exact_hits' if result.constraint_status=='full_segment' else 'constraint_hits'
            counts[key]+=1;document[key]+=1
            if request.knowledge_snapshot:
                matches=request.knowledge_snapshot.candidates(request.text,request.domain,request.context,set())
                used=sorted(matches,key=lambda m:-(m.end-m.start))[:1] if key=='exact_hits' else matches
                for match in used:
                    meta=entry_metadata(match.entry);kind=meta.get('type','term')+'_hits'
                    counts[kind]+=1;document[kind]+=1
                    if meta.get('concept_id'):counts['concept_hits']+=1;document['concept_hits']+=1

    def detect_domain(self, text, source, target):
        from app.glossary.domain_detection import DomainEvidence
        return self.domain_detector.detect(text, source, target) if self.domain_detector else DomainEvidence()

    def __getattr__(self, name):
        # Preserve RuntimeManager, language resolver and diagnostics API.
        return getattr(self.router, name)

    def translate_path(self, request, cancelled=None):
        """Naming only: existing exact/constraint glossary, protected literals,
        and the same model router. No TM, profiler, templates or prose guards.
        The archive supplies one shared context/snapshot and a run-local cache.
        """
        from app.documents.pdf_fidelity import ATOM
        cancelled = cancelled or Event()
        check_cancelled(cancelled)
        if len(request.text) > self.router.policy.max_text_chars:
            raise InputTooLongError()
        source, target = self.languages.resolve(request.text, request.source_language, request.target_language)
        request = replace(request, source_language=source, target_language=target)
        request = self.contextualize(request)
        if source == target:
            return self.router.translate(request, cancelled)
        if self.glossary is not None:
            direct = self.glossary.full_segment(request)
            if direct is not None:
                return direct
        # Keep model/OEM codes and numbers outside inference. Consult whole-name
        # Knowledge first so a known compound retains its reviewed rendering.
        parts = []
        position = 0
        last = None
        def translate_part(text):
            nonlocal last
            if not any(c.isalpha() for c in text):
                return text
            leading = text[:len(text)-len(text.lstrip())]
            trailing = text[len(text.rstrip()):]
            piece = replace(request, text=text.strip())
            last = (self.glossary.translate(piece, self.router, cancelled)
                    if self.glossary is not None else self.router.translate(piece, cancelled))
            return leading + last.translated_text.strip() + trailing
        for match in ATOM.finditer(request.text):
            check_cancelled(cancelled)
            parts.extend((translate_part(request.text[position:match.start()]), match.group()))
            position = match.end()
        parts.append(translate_part(request.text[position:]))
        text = ''.join(parts)
        if last is None:
            return TranslationResult(text, source, target, 'passthrough', 'none', 0,
                                     'protected path tokens', False, request.request_id, domain=request.domain)
        return replace(last, translated_text=text, request_id=request.request_id)

    def translate(self, request, cancelled=None, *, backend_only=None):
        with offline_scope():
            if len(request.text) > self.router.policy.max_text_chars:
                raise InputTooLongError()
            if request.source_language in ('zh', 'auto') and request.target_language == 'ru':
                branch = re.fullmatch(r'\s*(是|否)\s*([▶►→])\s*(.+)', request.text, re.S)
                if branch:
                    result = self.translate(replace(request, text=branch[3]), cancelled, backend_only=backend_only)
                    if result.constraint_status.startswith('semantic_source_preserved:'):
                        return replace(result, translated_text=request.text)
                    result = replace(result, translated_text=('Да' if branch[1]=='是' else 'Нет')+' '+branch[2]+' '+result.translated_text)
                    return self._ensure_safe(request, result, cancelled)
            result = self._translate(request, cancelled, backend_only=backend_only)
            return self._ensure_safe(request, result, cancelled)

    @measure('semantic_guards')
    def _ensure_safe(self, request, result, cancelled=None):
        """TM, glossary and model outputs share the same contradiction guard."""
        if result.source_language != 'zh' or result.target_language != 'ru':
            return result
        from app.knowledge.questions import features as question_features
        question = question_features(request.text)
        if question:
            result = replace(result,question_kind=question.kind)
        if result.translated_text == request.text and result.constraint_status.startswith('semantic_source_preserved:'):
            return result
        if result.constraint_status == 'verified_cross_reference:source_title_preserved':
            from app.knowledge.references import validate_source_title
            return replace(result,translated_text=validate_source_title(request.text,result.translated_text))
        request = self.contextualize(replace(request, source_language='zh', target_language='ru'))
        if request.domain == 'auto':
            request = replace(request, domain=self.detect_domain(request.text, 'zh', 'ru').domain)
        from app.knowledge.safety import violations, russian_actions
        from app.knowledge.units import reviewed_context_measurement
        measured_caption = reviewed_context_measurement(request)
        action_frame = self._safe_action_object(request,with_semantics=True)
        def problems(target):
            issues = list(violations(request.text,target) + self.object_guard.violations(request,target,self.context_router.slot_forms))
            # In the independently reviewed reservoir caption, 之前 is a
            # mistranslation of Pri, not a temporal precondition. Recompute the
            # exact guarded rendering; a status flag or arbitrary model answer
            # cannot grant this exception.
            if measured_caption is not None and target == measured_caption:
                issues = [issue for issue in issues if issue!='condition:before']
            if action_frame and action_frame[1] not in russian_actions(target):
                issues.append('action:'+action_frame[1]+':LOST')
            return issues
        issues = problems(result.translated_text)
        if issues:observe('guards',issues)
        if not issues:
            return result
        started = perf_counter()
        self.context_router.metrics['semantic_guard_rejections'] += 1
        if action_frame and not problems(action_frame[0]):
            self.context_router.metrics['semantic_guard_action_object_repairs'] += 1
            return replace(result,translated_text=action_frame[0],backend='knowledge_template',knowledge_source='template',
                duration_ms=result.duration_ms+(perf_counter()-started)*1000,
                constraint_status='semantic_action_object_repair:'+action_frame[1])
        template = self._template(request)
        if template and not problems(template.translated_text):
            self.context_router.metrics['semantic_guard_template_repairs'] += 1
            return replace(template, duration_ms=result.duration_ms + (perf_counter()-started)*1000,
                           constraint_status='semantic_template_repair',question_kind=result.question_kind)
        # One bounded pass through the existing glossary constraint pipeline.
        # No model output is ever promoted to Knowledge or translation memory.
        from app.engine.errors import TranslationError, TranslationCancelledError
        retry = None
        try:
            check_cancelled(cancelled or Event())
            retry = (self.glossary.translate(request, self.router, cancelled or Event())
                     if self.glossary else self.router.translate(request, cancelled or Event()))
        except TranslationCancelledError:
            raise
        except TranslationError:
            pass
        action_issues = [issue.split(':')[1] for issue in issues if issue.startswith('action:')]
        from app.knowledge.safety import COMMANDS
        actions_retained = (retry is not None and all(re.search(r'\b(?:'+COMMANDS[concept]+r')\b', retry.translated_text, re.I)
                            for concept in action_issues if concept in COMMANDS))
        if (retry and retry.translated_text != request.text and actions_retained
                and not problems(retry.translated_text)):
            self.context_router.metrics['semantic_guard_retry_repairs'] += 1
            return replace(retry, duration_ms=result.duration_ms + (perf_counter()-started)*1000,
                           constraint_status='semantic_retry_repair',question_kind=result.question_kind)
        composed = self._safe_action_object(request)
        if composed and not problems(composed):
            self.context_router.metrics['semantic_guard_action_object_repairs'] += 1
            return replace(result, translated_text=composed, backend='knowledge_template', knowledge_source='template',
                           duration_ms=result.duration_ms + (perf_counter()-started)*1000,
                           constraint_status='semantic_action_object_repair')
        self.context_router.metrics['semantic_guard_source_preserved'] += 1
        import logging
        logging.getLogger('treetranslate.knowledge').warning('semantic_source_preserved reasons=%s', ','.join(issues))
        if self.glossary:
            self.glossary.last_warning = 'Небезопасное изменение смысла перевода: исходный фрагмент сохранён. Проверьте его вручную.'
            self.glossary.warning(self.glossary.last_warning)
        return replace(result, translated_text=request.text, fallback_used=True,
                       duration_ms=result.duration_ms + (perf_counter()-started)*1000,
                       constraint_status='semantic_source_preserved:' + ','.join(issues))

    def _safe_action_object(self, request, *, with_semantics=False):
        """One reviewed command frame, one whole HIGH noun, complete case forms."""
        if (request.knowledge_snapshot is None or request.domain != 'automotive'
                or request.source_language!='zh' or request.target_language!='ru'
                or request.context_router is None or request.context_profile is None or len(request.text)>256):
            return None
        from app.knowledge.safety import action_records
        from app.glossary.constraints import validate_result
        from app.glossary.errors import ConstraintFailure
        text = request.text.strip()
        if (request.segment_type!='PROCEDURE_STEP'
                and not (request.segment_type=='PROSE' and text.endswith('。'))):
            return None  # A component or procedure heading is not a command.
        prefix = re.match(r'^(?:\d{1,3}[.．、]\s*|[•●▪]\s*)',text)
        enumeration = prefix[0] if prefix else ''
        if prefix:
            text = text[prefix.end():]
        semantic_text = text.rstrip('。.').strip()
        semantic_marker = re.search(r'\s*[（(][A-Z][0-9]{0,2}[）)]$',semantic_text)
        if semantic_marker:
            semantic_text = semantic_text[:semantic_marker.start()].strip()
        whole = request.knowledge_snapshot.candidates(semantic_text,request.domain,request.context,set())
        if any(m.start==0 and m.end==len(semantic_text) and str(entry_metadata(m.entry).get('type','')).upper()
               in {'TERM','COMPOUND'} for m in whole):
            return None  # A longer known component owns its meaning.
        surfaces = sorted(((surface,action) for action in action_records() for surface in action['zh']),
                          key=lambda item:-len(item[0]))
        rules = self.context_router.templates
        own = {branch.partition('.')[2] or branch for branch,_ in request.context_profile.subdomains}
        for surface, action in surfaces:
            match = re.fullmatch(re.escape(surface) + r'\s*(.+?)[。.]?', text)
            if not match:
                continue
            component = match.group(1).strip()
            marker = re.search(r'\s*([（(][A-Z][0-9]{0,2}[）)])$',component)
            literal = marker[1] if marker else ''
            if marker:
                component = component[:marker.start()].strip()
            form = self.context_router.slot_forms.get(component)
            if not form or not all(form.get(case) for case in ('nominative','genitive','accusative')):
                continue
            # Reuse the existing reviewed action/slot contracts rather than
            # granting every operation to every known technical noun.
            frames = [rule for rule in rules if rule['status']=='VERIFIED' and rule.get('shared_forms')
                      and len(rule['forms'])==1 and next(iter(rule['forms'].values()))=='accusative'
                      and rule['source'] in (surface+'{'+next(iter(rule['forms']))+'}',
                                             surface+'{'+next(iter(rule['forms']))+'}。')
                      and rule['domain'] in (request.domain,'general.technical.procedure')
                      and (not rule['subdomains'] or own.intersection(rule['subdomains']))
                      and 'PROCEDURE_STEP' in rule['types']
                      and component in rule.get('slot_allowed',{}).get(next(iter(rule['forms'])),rule.get('allowed_slots',[]))
                      and (not literal or rule.get('component_marker'))]
            if not frames:
                continue
            matches = [m for m in request.knowledge_snapshot.candidates(component,request.domain,request.context,set())
                       if m.start==0 and m.end==len(component)]
            noun_request = replace(request,text=component,segment_type='COMPONENT_LABEL')
            if not matches or any(m.store=='user' or m.entry.trust<.8 or m.entry.mode!='PREFERRED'
                    or m.entry.status not in ('BUILTIN','REVIEWED','CONFIRMED')
                    or entry_metadata(m.entry).get('review_status')!='VERIFIED'
                    or not entry_metadata(m.entry).get('concept_id')
                    or str(entry_metadata(m.entry).get('type','')).upper() not in {'TERM','COMPOUND'}
                    or entry_metadata(m.entry).get('semantic_role') in {'quantity','diagnostic_relation'}
                    or entry_metadata(m.entry).get('label_only')
                    or not request.context_router.allow_bypass(m,noun_request) for m in matches):
                continue
            concepts = {(entry_metadata(m.entry)['concept_id'],m.entry.target_term.casefold()) for m in matches}
            if len(concepts)!=1 or next(iter(concepts))[1]!=form['base'].casefold():
                continue
            target = enumeration+action['imperative']+' '+form['accusative']+(' '+literal if literal else '')+'.'
            try:
                target = validate_result(request.text,target)
            except ConstraintFailure:
                continue
            return (target,action['semantic_id']) if with_semantics else target
        return None

    def _translate(self, request, cancelled=None, *, backend_only=None):
        cancelled = cancelled or Event()
        check_cancelled(cancelled)
        started = perf_counter()
        if len(request.text) > self.router.policy.max_text_chars:
            raise InputTooLongError()
        if backend_only or not request.text.strip():
            return self.router.translate(request, cancelled, backend_only=backend_only)
        source, target = self.languages.resolve(request.text, request.source_language, request.target_language)
        request = replace(request, source_language=source, target_language=target)
        request = self.contextualize(request)
        if request.domain == 'auto':
            request = replace(request, domain=self.detect_domain(request.text, source, target).domain)
        if source != target:
            match = self.memory.lookup(request.text, source, target, request.domain, request.context)
            check_cancelled(cancelled)
            if match and match.reusable:
                self.memory.record_use(match)
                return TranslationResult(match.target, source, target, 'translation_memory', 'none',
                    (perf_counter()-started)*1000, f'TM {match.match_type}; unit={match.translation_unit_id}',
                    False, request.request_id,knowledge_source='tm',domain=request.domain)
        if source != target and self.glossary is not None:
            structured = self.glossary.full_segment(request) or self._structured_exact(request)
            if structured is not None:
                self.record_context_result(structured,request)
                return replace(structured, duration_ms=(perf_counter()-started)*1000)
            template=self._template(request)
            if template is not None:return replace(template,duration_ms=(perf_counter()-started)*1000)
            result=self.glossary.translate(request,self.router,cancelled)
            self.record_context_result(result,request)
            return replace(result,duration_ms=(perf_counter()-started)*1000)
        # No automatic write-back, even when a model succeeds.
        return self.router.translate(request, cancelled)

    def lookup_direct(self, request, cancelled=None):
        """Allow protected PDF labels to consult knowledge without model inference."""
        check_cancelled(cancelled or Event())
        request=self.contextualize(request)
        if request.source_language==request.target_language:return None
        match=self.memory.lookup(request.text,request.source_language,request.target_language,request.domain,request.context)
        if match and match.reusable:
            self.memory.record_use(match)
            result = TranslationResult(match.target,request.source_language,request.target_language,'translation_memory','none',0,
                                       f'TM {match.match_type}',False,request.request_id,knowledge_source='tm',domain=request.domain)
            return self._ensure_safe(request, result, cancelled)
        if request.domain == 'auto':
            request = replace(request, domain=self.detect_domain(request.text, request.source_language, request.target_language).domain)
        if self.glossary is not None:
            result=self.glossary.full_segment(request) or self._structured_exact(request) or self._template(request)
            if result:self.record_context_result(result,request)
            return self._ensure_safe(request, result, cancelled) if result else None
        return None

    def _structured_exact(self, request):
        """Reuse trusted label knowledge with literal diagram suffixes.

        Only an entire known semantic prefix plus a numeric/identifier suffix
        qualifies. Sentences and arbitrary partial matches still use constraints.
        """
        from app.documents.pdf_ocr_policy import protected_kind
        if request.source_language == 'zh' and request.target_language == 'ru':
            from app.knowledge.directives import action_heading
            heading = action_heading(request.text)
            if heading is not None:
                return TranslationResult(heading, 'zh', 'ru', 'knowledge_template', 'none', 0,
                    'verified_action_heading', False, request.request_id, knowledge_source='template',
                    domain=request.domain, constraint_status='verified_action_heading')
            from app.knowledge.units import quantity_caption, reviewed_quantity_label, reviewed_context_measurement
            caption = reviewed_context_measurement(request)
            if caption is not None:
                return TranslationResult(caption,'zh','ru','knowledge_template','none',0,'verified_context_measurement',False,
                    request.request_id,knowledge_source='template',domain=request.domain,constraint_status='verified_context_measurement')
            caption = reviewed_quantity_label(request)
            if caption is not None:
                return TranslationResult(caption,'zh','ru','knowledge_template','none',0,'verified_quantity_label',False,
                    request.request_id,knowledge_source='template',domain=request.domain,constraint_status='verified_quantity_label')
            import json
            matches = self.glossary.lookup(request.text,'zh','ru',request.domain,request.context,
                snapshot=request.knowledge_snapshot,request=request)
            qualified = [m for m in matches if m.start==0 and m.end==len(request.text)
                         and m.entry.origin=='authored_rule' and m.store!='user'
                         and entry_metadata(m.entry).get('rule_id')=='fluid-properties-v1']
            if len(qualified)==1:
                from app.glossary.constraints import validate_result
                caption = validate_result(request.text,qualified[0].entry.target_term)
                return TranslationResult(caption,'zh','ru','knowledge_template','none',0,'verified_fluid_property_caption',False,
                    request.request_id,knowledge_source='template',domain=request.domain,constraint_status='verified_fluid_property_caption')
            def quantity(text):
                matches = self.glossary.lookup(text,'zh','ru','automotive',request.context)
                targets = {m.entry.target_term for m in matches if m.start==0 and m.end==len(text)
                           and m.store!='user' and m.entry.trust >= .8 and m.entry.mode!='FORBIDDEN'
                           and m.entry.status in ('BUILTIN','REVIEWED','CONFIRMED')
                           and entry_metadata(m.entry).get('review_status')=='VERIFIED'}
                return next(iter(targets)) if len(targets)==1 else None
            caption = quantity_caption(request.text,quantity,self.context_router.slot_forms)
            if caption is not None:
                return TranslationResult(caption,'zh','ru','knowledge_template','none',0,'verified_quantity_caption',False,
                    request.request_id,knowledge_source='template',domain=request.domain,constraint_status='verified_quantity_caption')
            from app.knowledge.references import is_reference, render, annotated, validate_source_title, tagged_label, breadcrumb
            if '>' in request.text:
                def node_label(text):
                    result=self.glossary.full_segment(replace(request,text=text,segment_type='DIAGRAM_LABEL'))
                    return result.translated_text if result else None
                trail=breadcrumb(request.text,node_label)
                if trail is not None:
                    return TranslationResult(trail,'zh','ru','knowledge_template','none',0,'verified_breadcrumb',False,
                        request.request_id,knowledge_source='template',domain=request.domain,constraint_status='verified_breadcrumb')
            if is_reference(request.text):
                import json
                from app.glossary.constraints import validate_result
                from app.glossary.errors import ConstraintFailure
                def label(text):
                    # References explicitly name another section. Query exact
                    # reviewed labels through the existing index across official
                    # automotive branches, never through an unrestricted model.
                    matches = self.glossary.lookup(text,'zh','ru','automotive',request.context,
                        request=replace(request,text=text,segment_type='CROSS_REFERENCE'))
                    targets = {m.entry.target_term for m in matches if m.start==0 and m.end==len(text)
                               and m.store!='user' and m.entry.trust >= .8
                               and m.entry.mode!='FORBIDDEN'
                               and m.entry.status in ('BUILTIN','REVIEWED','CONFIRMED')
                               and entry_metadata(m.entry).get('review_status')=='VERIFIED'}
                    if len(targets)==1:
                        return next(iter(targets))
                    if len(targets)>1:
                        return None
                    return tagged_label(text,label,self.context_router.slot_forms)
                def recover_title(text):
                    matches = self.glossary.lookup(text,'zh','ru','automotive',request.context,
                        request=replace(request,text=text,segment_type='CROSS_REFERENCE'))
                    return any(m.start==0 and m.end==len(text) and m.store!='user'
                        and entry_metadata(m.entry).get('review_status')=='VERIFIED'
                        and text in entry_metadata(m.entry).get('open_reference_aliases',()) for m in matches)
                target = render(request.text,label,preserve_unknown_title=True,recover_title=recover_title)
                source_title_preserved = annotated(target)
                try:
                    if target is not None:
                        target = validate_source_title(request.text,target) if source_title_preserved else validate_result(request.text,target)
                except ConstraintFailure:
                    target = None
                status = 'verified_cross_reference' if target else 'semantic_source_preserved:cross_reference:unknown_label'
                if source_title_preserved and target is not None:
                    status = 'verified_cross_reference:source_title_preserved'
                if target is None or source_title_preserved:
                    self.context_router.metrics['cross_reference_source_preserved'] += 1
                    self.glossary.last_warning = 'Небезопасное изменение смысла перевода: исходный фрагмент сохранён. Проверьте его вручную.'
                    self.glossary.warning(self.glossary.last_warning)
                return TranslationResult(target if target is not None else request.text,'zh','ru','knowledge_template','none',0,
                    status,target is None,request.request_id,knowledge_source='template',domain=request.domain,constraint_status=status)
        tagged = re.fullmatch(r"([A-Z](?:[&/\-][A-Z])*)\s*([\[［])([^\[\]［］]+)([\]］])", request.text)
        if tagged:
            marker, opening, qualifier, closing = tagged.groups()
            detail = self.glossary.full_segment(replace(request, text=qualifier.strip()))
            if detail:
                return replace(detail, translated_text=f'{marker} {opening}{detail.translated_text}{closing}')
        variant = re.fullmatch(r'(.+?)\s*([（(])([^（）()]+?)([A-Z][\'′″"]*)([）)])', request.text)
        if variant:
            label, opening, qualifier, marker, closing = variant.groups()
            main = self.glossary.full_segment(replace(request, text=label.strip()))
            detail = self.glossary.full_segment(replace(request, text=qualifier.strip()))
            if main and detail:
                return replace(main, translated_text=f'{main.translated_text} {opening}{detail.translated_text} {marker}{closing}')
        match = re.fullmatch(r'(.*?[\u4e00-\u9fff])([\s（(]*[^\u4e00-\u9fff]+)', request.text)
        if not match:
            return None
        prefix, suffix = match.groups()
        core = suffix.strip().strip('()（）').strip()
        marked_quantity=re.fullmatch(r'[A-Z]\s+\d+(?:[.,]\d+)?\s*±\s*\d+(?:[.,]\d+)?',core)
        if not (protected_kind(core) or marked_quantity or re.fullmatch(r"(?:[A-Z]['′″\"]*[:：][Øø]?\d+(?:\.\d+)?\s*)+", core)):
            return None
        result = self.glossary.full_segment(replace(request, text=prefix))
        separator = ' ' if suffix and suffix[0].isalnum() else ''
        return replace(result, translated_text=result.translated_text + separator + suffix) if result else None

    def prefetch(self, sources, source, target, domain='general', context=''):
        result=self.memory.lookup_many(sources, source, target, domain, context)
        if self.glossary is not None and hasattr(self.glossary,'prefetch'):
            self.glossary.prefetch(sources,source,target,domain,context)
        return result

    def shutdown(self):
        try:self.router.shutdown()
        finally:
            if self.glossary is not None and hasattr(self.glossary,'close'):self.glossary.close()
