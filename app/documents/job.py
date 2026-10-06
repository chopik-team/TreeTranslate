"""Qt-free document orchestration; translation is supplied by the existing router."""
from dataclasses import dataclass
from pathlib import Path
import os
import re
import tempfile
import logging
import json
from collections import deque
from statistics import median
from uuid import uuid4

from app.documents.docx_document import validate_docx, URL
from app.documents.backends import open_document
from app.documents.pdf_fidelity import ATOM, preserve_title, segment_source, faithful_result, FidelityMismatch
from app.documents.errors import DocumentError, SourceChangedError
from app.documents.pdf_diagnostics import timed_process, timed_stage
from app.engine.languages import language_code
from app.engine.types import TranslationRequest, DevicePreference, PerformanceProfile
from app.models.translation_job import TranslationProgress
from app.documents.run_metrics import logged_run,observe,semantic_segment,current

logger = logging.getLogger('treetranslate.documents.job')


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:120]
    if not value or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        value = '_' + value
    return value


def filename_stem(value, suffix):
    """Remove repeated extension/download suffixes, preserving meaningful dots."""
    if not suffix:
        return value
    previous = None
    while value != previous:
        previous = value
        value = re.sub(re.escape(suffix) + r'\s*(?:\(\d+\))?$', '', value.rstrip(), flags=re.I)
    return value


def safe_filename_base(value, fallback, suffix=''):
    """Sanitize a translated filename stem, falling back to the original stem."""
    def clean(candidate):
        candidate = filename_stem(candidate.strip().rstrip(' .'), suffix)
        candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', candidate).rstrip(' .')[:120]
        if (not candidate or (suffix and candidate.casefold() == suffix[1:].casefold())
                or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', candidate, re.I)):
            return None
        return candidate
    return clean(value.strip()) or clean(fallback.strip()) or '_document'


@dataclass(frozen=True)
class DocumentConfig:
    source: str = 'auto'
    target: str = 'ru'
    device: DevicePreference = DevicePreference.AUTO
    profile: PerformanceProfile = PerformanceProfile.AUTOMATIC
    threads: int | None = None
    output: Path | None = None
    template: str = '{name}_{lang}'
    translate_directories: bool = False
    translate_filenames: bool = False
    pdf_limits: object = None
    ocr_enabled: bool = True
    domain: str = 'general'
    context: str = ''
    parent_context: object = None
    metrics_directory: Path | None = None


class DocumentJob:
    def __init__(self, files, config, control, translate, resolve, progress=lambda p: None, outputs=lambda p: None,
                 warning=lambda message: None, before_ocr=lambda: None, run_id=None,
                 file_completed=lambda source, output: None, eta_estimator=None):
        self.files, self.config, self.control = tuple(files), config, control
        self.translate, self.resolve, self.progress, self.outputs = translate, resolve, progress, outputs
        self.completed = []
        self.directories = {}
        if (config.metrics_directory or current()) and not getattr(warning,'_local_metrics_warning',False):
            def observed_warning(message):
                observe('warning',message);warning(message)
            observed_warning._local_metrics_warning=True
            self.warning=observed_warning
        else:self.warning=warning
        self.before_ocr = before_ocr
        self.detected_domains = []  # Content-free, per-document runtime metadata.
        self._domain = config.domain
        self._context_profile = config.parent_context
        self._snapshot = None
        self._segment_type = ''
        self.run_id = run_id or uuid4().hex[:12]
        self.file_completed = file_completed
        self._routes = set()
        self._logged_progress = None
        self.eta_estimator = eta_estimator
        self._durations = ()
        self.destination_override = None
        self.path_translation = None  # Archive-scoped lightweight naming/cache.
        self.archive_summaries = []
        self._ocr_runtime = None

    def _report_progress(self, progress):
        self._latest_progress = progress
        if self.eta_estimator:
            self.eta_estimator.update(progress, self._durations)
        key = (progress.stage, progress.file_index, progress.page_index, progress.processed // 10)
        if key != self._logged_progress:
            logger.info('run=%s stage=%s percent=%d segments=%d/%d file=%d/%d page=%d/%d elapsed=%d eta=%s',
                        self.run_id, progress.stage, progress.percent, progress.processed, progress.total,
                        progress.file_index, progress.file_total, progress.page_index, progress.page_total,
                        progress.elapsed_seconds, progress.eta_seconds)
            self._logged_progress = key
        self.progress(progress)

    def _record_route(self, result):
        observe('see_result',result)
        if (getattr(result, 'constraint_status', '').startswith('semantic_source_preserved:')
                or getattr(result,'constraint_status','')=='verified_cross_reference:source_title_preserved'):
            self.warning('Небезопасное изменение смысла перевода: исходный фрагмент сохранён. Проверьте его вручную.')
        route = tuple(getattr(result, key, None) for key in
                      ('source_language', 'target_language', 'domain', 'backend', 'device', 'compute_type'))
        if route not in self._routes:
            self._routes.add(route)
            logger.info('run=%s route source=%s target=%s domain=%s backend=%s device=%s compute_type=%s',
                        self.run_id, *route)

    @timed_process('pdf_segment_translation')
    def _pdf_translation(self, text, source, target):
        from app.documents.pdf_ocr_policy import protected_kind
        if protected_kind(text):
            return text
        direct = getattr(getattr(self.translate, '__self__', None), 'lookup_direct', None)
        if direct:
            self.control.checkpoint()
            result = direct(TranslationRequest(text, source, target, self.config.device, self.config.profile,
                            domain=self._domain, context=self.config.context,context_profile=self._context_profile,
                            knowledge_snapshot=self._snapshot,segment_type=self._segment_type), self.control.cancelled)
            if result is not None:
                self._record_route(result)
                if result.constraint_status=='verified_cross_reference:source_title_preserved':
                    from app.knowledge.references import validate_source_title
                    return validate_source_title(text,result.translated_text)
                return faithful_result(text, result.translated_text)
        # Protect visible URLs, emails and recognizable internal identifiers.
        if preserve_title(text):
            return text
        if not URL.search(text) and not re.search(r'\b[A-Za-z][A-Za-z0-9]*[_-][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b', text):
            # Keep sentence context. Protect enumeration outside inference and
            # validate numbers/IDs rather than translating tiny broken clauses.
            prefix = re.match(r'^\s*(?:\d+[.)、]\s*|[•●▪]\s*)', text)
            start = prefix.end() if prefix else 0
            return text[:start] + faithful_result(text[start:], self._translate(text[start:], source, target))
        protected = ATOM
        result, position = [], 0
        def translate_part(part):
            translated = []
            while part:
                length = min(4000, len(part))
                if length < len(part):
                    split = part.rfind(' ', 2000, length)
                    length = split + 1 if split >= 0 else length
                translated.append(self._translate(part[:length], source, target))
                part = part[length:]
            return ''.join(translated)
        for match in protected.finditer(text):
            part = translate_part(text[position:match.start()])
            atom = match.group()
            if part and part[-1].isalpha() and atom[0].isalnum():
                part += ' '
            result.extend((part, atom))
            position = match.end()
        result.append(translate_part(text[position:]))
        return ''.join(result)

    @timed_process('engine_translation')
    def _translate(self, text, source, target, empty_fallback=None, segment_type=''):
        self.control.checkpoint()
        if source == target or not any(c.isalpha() for c in text):
            return text
        c = self.config
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        request=TranslationRequest(text.strip(), source, target, c.device, c.profile,
                                cpu_threads=c.threads, domain=self._domain, context=c.context,context_profile=self._context_profile,
                                knowledge_snapshot=self._snapshot,segment_type=segment_type or self._segment_type)
        translate = self.path_translation if self.path_translation and request.segment_type in {'FILENAME', 'FOLDER_NAME'} else self.translate
        result=translate(request,self.control.cancelled)
        self._record_route(result)
        observe('frontier_candidate',text.strip(),request,result)
        if not result.translated_text.strip():
            if empty_fallback is not None:
                return empty_fallback
            raise DocumentError('Движок вернул пустой перевод. Исходный файл сохранён без изменений.')
        return leading + result.translated_text.strip() + trailing

    def _directory(self, key, parent, name):
        if key not in self.directories:
            parent.mkdir(parents=True, exist_ok=True)
            for index in range(10000):
                candidate = parent / (name if not index else f'{name} ({index})')
                try:
                    candidate.mkdir()
                except FileExistsError:
                    continue
                self.directories[key] = candidate.resolve()
                break
            else:
                raise DocumentError('Не удалось выбрать свободное имя папки.')
        return self.directories[key]

    @timed_process('destination_filename')
    def _destination(self, item, source, target):
        if self.destination_override:
            return self.destination_override(item, source, target)
        c = self.config
        parent = c.output or item.path.parent
        if item.root:
            name = self._translate(item.root.name, source, target,segment_type='FOLDER_NAME') if c.translate_directories else item.root.name
            name = safe_name(c.template.replace('{name}', name).replace('{lang}', target))
            parent = self._directory(item.root, c.output or item.root.parent, name)
            original = item.root
            for part in item.relative.parts[:-1]:
                original = original / part
                name = self._translate(part, source, target,segment_type='FOLDER_NAME') if c.translate_directories else part
                parent = self._directory(original, parent, safe_name(name))
        parent.mkdir(parents=True, exist_ok=True)
        return parent.resolve() / self._filename(item.path, source, target)

    def _filename(self, path, source, target):
        c = self.config
        suffix = path.suffix
        original_name = filename_stem(path.stem, suffix)
        if c.translate_filenames:
            translated_name = self._translate(original_name, source, target, empty_fallback=original_name,segment_type='FILENAME')
            base_name = safe_filename_base(translated_name, original_name, suffix)
        else:
            base_name = original_name
        name = safe_name(filename_stem(c.template.replace('{name}', base_name).replace('{lang}', target), suffix))
        return name + suffix

    @logged_run
    @timed_process('document_job')
    def run(self):
        from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager
        owns_ocr_runtime = self._ocr_runtime is None
        if owns_ocr_runtime:
            self._ocr_runtime = OcrRuntimeManager(checkpoint=self.control.checkpoint, run_scoped=True)
        engine=getattr(self.translate,'__self__',None)
        contextual=getattr(engine,'context_router',None)
        if contextual is not None:
            depth=getattr(contextual,'job_depth',0)
            if not depth:
                contextual.clear();contextual.metrics.clear();contextual.documents.clear();contextual.snapshots.clear();contextual.decisions.clear();contextual.document_metrics.clear()
            contextual.job_depth=depth+1
        try:return self._run()
        finally:
            if owns_ocr_runtime:
                self._ocr_runtime.shutdown()
                self._ocr_runtime = None
            if contextual is not None:
                contextual.job_depth-=1
                if not contextual.job_depth:
                    contextual.clear();engine.last_context_metrics=contextual.summary()
                    summary=engine.last_context_metrics
                    logger.info('run=%s contextual_knowledge=%s',self.run_id,json.dumps(dict(metrics=summary.get('metrics',{}),
                        profiles=len(summary.get('profiles',())),snapshots=len(summary.get('snapshots',())),decisions=len(summary.get('decisions',()))),ensure_ascii=False))
                    from app.knowledge.segments import SegmentClassifier
                    SegmentClassifier.clear()
            self._snapshot=None;self._context_profile=None

    def _run(self):
        if any(item.archive for item in self.files) and not self.destination_override:
            if language_code(self.config.target) == 'auto':
                raise DocumentError('Выберите язык перевода явно.')
            return self._run_inputs()
        return self._run_documents()

    def _run_inputs(self):
        from dataclasses import replace
        from app.documents.archive_job import ArchiveJob
        groups = []
        archives = {}
        for item in self.files:
            if item.archive:
                if item.archive not in archives:
                    archives[item.archive] = []
                    groups.append(archives[item.archive])
                archives[item.archive].append(item)
            else:
                groups.append([item])
        offset = 0
        for group in groups:
            self.control.checkpoint()
            def progress(value):
                self._report_progress(replace(value, percent=min(99, int((offset + len(group)*value.percent/100)*100/len(self.files))),
                    file_index=offset+value.file_index if value.file_index else offset+1, file_total=len(self.files),
                    stage='PUBLISHING' if value.stage == 'COMPLETED' else value.stage))
            if group[0].archive:
                archive_job = ArchiveJob(self, group, progress)
                output = archive_job.run()
                self.completed.append(output)
                self.outputs(tuple(self.completed))
                for item in group:
                    if item.relative.as_posix() in archive_job.translated_members:
                        self.file_completed(item.path, output)
            else:
                child = DocumentJob(group, self.config, self.control, self.translate, self.resolve, progress,
                    lambda paths: None, self.warning, self.before_ocr, self.run_id, self.file_completed)
                child.directories = self.directories
                child._ocr_runtime = self._ocr_runtime
                self.completed.extend(child.run())
                self.outputs(tuple(self.completed))
            offset += len(group)
        self.run_status = 'COMPLETED_WITH_FAILURES' if any(s['failed_documents'] for s in self.archive_summaries) else 'COMPLETED'
        final = replace(self._latest_progress, percent=100, stage=self.run_status, elapsed_seconds=int(self.control.elapsed),
            file_index=len(self.files), file_total=len(self.files), source_path='', file_percent=100,
            current_file=self.files[-1].archive.name if self.files[-1].archive else self.files[-1].path.name)
        self._report_progress(final)
        return tuple(self.completed)

    def _run_documents(self):
        # The serial path consumes the same stage implementation as the
        # archive pipeline. Translation, guards and writer remain unchanged.
        for _ in self._document_stages():
            pass
        return tuple(self.completed)

    def _document_stages(self):
        if not self.files:
            raise DocumentError('Выберите хотя бы один DOCX или PDF. Формат пока не поддерживается для других файлов.')
        target = language_code(self.config.target)
        if target == 'auto':
            raise DocumentError('Выберите язык перевода явно.')
        plans = []
        if self.eta_estimator:
            with timed_stage('workload_inventory'):
                self.eta_estimator.prepare(self.files, self.config, self.run_id)
        from app.ocr.router.ocr_router import OcrRouter
        from app.ocr.pdf_extractor import HybridPdfExtractor
        router_factory = getattr(self, "_pipeline_router_factory", OcrRouter)
        router = router_factory(checkpoint=self.control.checkpoint, before_ocr=self.before_ocr,
                           runtime=self._ocr_runtime)
        class CachedExtraction:
            def __init__(self, delegate):
                self.delegate, self.pages = delegate, {}
            @property
            def ocr_used(self):
                return self.delegate.ocr_used
            def set_source_identity(self, identity):
                self.delegate.source_identity = identity
            def extract(self, page, index, objects, limits):
                if index not in self.pages:
                    self.pages[index] = self.delegate.extract(page,index,objects,limits)
                return self.pages[index]
        try:
            for index, item in enumerate(self.files, 1):
                self.control.checkpoint()
                observe('start_document',item,self.config,getattr(self.translate,'__self__',None))
                def extraction_progress(stage, page=None, page_total=0, eta=None):
                    current = item.path.name + (f' · страница {page+1}' if page is not None else '')
                    self._report_progress(TranslationProgress(total=0, current_file=current, file_index=index,
                        file_total=len(self.files), elapsed_seconds=int(self.control.elapsed), stage=stage,
                        page_index=(page+1) if page is not None else 0,page_total=page_total,eta_seconds=eta,
                        eta_scope='stage', source_path=str(item.path),
                        file_percent=int(15 * (page or 0) / max(1, page_total))))
                extraction_progress('EXTRACTING')
                extractor = CachedExtraction(HybridPdfExtractor(router,self.config,self.control.checkpoint,extraction_progress)) if self.config.ocr_enabled and item.path.suffix.lower() == '.pdf' else None
                with timed_stage('preflight_open_extract'):
                    doc = open_document(item.path, self.control, self.config.pdf_limits, extractor)
                if getattr(self, '_pipeline_active', False):
                    self._prepared_document = doc
                    yield 'prepared'
                logger.info('run=%s source=%s bytes=%d sha256=%s pages=%d segments=%d chars=%d native_segments=%d ocr_segments=%d', self.run_id,
                            item.path, item.size, doc.source_hash, len(getattr(doc, 'pages', ())), len(doc.segments),
                            sum(len(s.text) for s in doc.segments),
                            sum(getattr(s, 'origin', 'native') != 'ocr' for s in doc.segments),
                            sum(getattr(s, 'origin', 'native') == 'ocr' for s in doc.segments))
                with timed_stage('resolve_language'):
                    origins = {getattr(s, 'origin', 'native') for s in doc.segments}
                    ocr_used = bool(extractor and extractor.ocr_used)
                    kind = 'docx' if item.path.suffix.lower() == '.docx' else 'pdf_mixed' if ocr_used and 'native' in origins else 'pdf_ocr' if ocr_used else 'pdf_native' if doc.segments else 'pdf_no_text'
                    logger.info('run=%s document_metadata=%s', self.run_id, json.dumps(dict(file_index=index,
                        path=str(item.path), format=item.path.suffix.lower().lstrip('.'), kind=kind,
                        input_kind='zip' if item.archive else 'folder' if item.root else 'file', container=str(item.archive or item.root) if item.archive or item.root else None,
                        relative_path=str(item.relative), archive_origin=str(item.archive) if item.archive else 'unconfirmed', bytes=item.size,
                        pages=len(getattr(doc, 'pages', ())), segments=len(doc.segments), chars=sum(len(s.text) for s in doc.segments),
                        ocr_used=ocr_used), ensure_ascii=False))
                    source, target = self.resolve(doc.sample(), self.config.source, target) if doc.segments else (target, target)
                domain = self.config.domain
                context_profile=None;snapshot=None
                if domain == 'auto':
                    engine=getattr(self.translate,'__self__',None)
                    profile=getattr(engine,'profile_document',None)
                    if profile:
                        with timed_stage('document_profile'):
                            context_profile=profile(source,target,identity=doc.source_hash,segments=doc.segments,
                                filename=item.path.name,folders=tuple(item.relative.parts[:-1]),
                                archive=item.archive.name if item.archive else '',parent=self.config.parent_context)
                        domain=context_profile.primary_domain
                        with timed_stage('snapshot_build'):
                            snapshot=engine.context_router.snapshot(context_profile)
                if domain == 'auto':
                    detect = getattr(getattr(self.translate, '__self__', None), 'detect_domain', None)
                    # Extraction (including OCR) is already complete. Use spread
                    # segments without retaining another full document copy.
                    from app.glossary.domain_detection import document_sample
                    sample = document_sample(doc.segments)
                    with timed_stage('detect_domain'):
                        evidence = detect(sample, source, target) if detect else None
                    domain = evidence.domain if evidence else 'general'
                    self.detected_domains.append(evidence)
                plans.append((item, doc.source_hash, source, len(doc.segments), extractor, domain,context_profile,snapshot))
                observe('extracted',doc,source,target,context_profile,extractor)
                observe('pause_document')
                if self.eta_estimator:
                    self.eta_estimator.extracted(index, len(doc.segments))
                logger.info('run=%s resolved source=%s target=%s domain=%s requested_device=%s',
                            self.run_id, source, target, domain, self.config.device.value)
                # Cache only small extracted contracts, never all source PDFs or images.
                if not getattr(self, '_pipeline_active', False):
                    del doc
        finally:
            with timed_stage('ocr_shutdown'):
                router.shutdown()
        total = sum(p[3] for p in plans)
        done = 0
        durations = deque(maxlen=8)
        self._durations = durations
        for index, (item, digest, source, _, extractor, domain,context_profile,snapshot) in enumerate(plans, 1):
            observe('resume_document',item)
            self._domain = domain
            self._context_profile=context_profile;self._snapshot=snapshot
            self.control.checkpoint()
            if getattr(self, '_pipeline_active', False):
                doc = self._prepared_document
            else:
                with timed_stage('reopen_cached_extraction'):
                    doc = open_document(item.path, self.control, self.config.pdf_limits, extractor)
            if doc.source_hash != digest:
                raise SourceChangedError()
            file_done = 0
            published = False
            def update(finished=False, stage='TRANSLATING'):
                fraction = {'WRITING': .97, 'VALIDATING': .98, 'PUBLISHING': .99}.get(
                    stage, .95 * file_done / max(1, len(doc.segments)))
                percent = 100 if finished else min(99, int(100 * (index - 1 + fraction) / len(plans)))
                # Skip the first segment of each document (cold model setup).
                # Preparation and publication have no measured remaining work.
                eta = (max(1, round(median(durations) * (total - done)))
                       if stage == 'TRANSLATING' and len(durations) >= 3 and done < total else None)
                self._report_progress(TranslationProgress(percent, done, total, item.path.name, int(self.control.elapsed), index, len(plans), eta,
                                                   'COMPLETED' if finished else stage,
                                                   source_path=str(item.path),
                                                   file_percent=100 if published else int(15 + 85 * fraction)))
            update()
            from app.documents.pdf_diagnostics import known_layout_findings
            findings=known_layout_findings(doc.source_hash) if item.path.suffix.lower()=='.pdf' else []
            if findings:
                observe('layout_warning',findings)
                self.warning('Известное наложение текста в таблице PDF: результат требует визуальной проверки.')
            for message in getattr(doc, 'warnings', ()):
                self.warning(message)
            # Warm exact/normalized lookups in bounded batches before segment inference.
            # The callback remains compatible with injected translators and tests.
            prefetch = getattr(getattr(self.translate, '__self__', None), 'prefetch', None)
            if prefetch:
                for offset in range(0, len(doc.segments), 256):
                    self.control.checkpoint()
                    with timed_stage('knowledge_prefetch'):
                        prefetch([s.text.strip() for s in doc.segments[offset:offset+256]], source, target,
                                 self._domain, self.config.context)
            for segment in doc.segments:
                from app.knowledge.segments import SegmentClassifier
                from time import perf_counter
                classification_started=perf_counter()
                with timed_stage('segment_classification'):
                    self._segment_type=SegmentClassifier.classify(segment.text,segment=segment).value
                if context_profile is not None:
                    engine.context_router.metrics['segment_'+self._segment_type]+=1
                    engine.context_router.metrics['segment_classification_time']+=perf_counter()-classification_started
                    engine.context_router.document_metrics.setdefault(context_profile.identity,__import__('collections').Counter())['segment_'+self._segment_type]+=1
                started = self.control.active_seconds
                with semantic_segment(segment,self._segment_type):
                    if item.path.suffix.lower() == '.pdf':
                        logger.info('run=%s segment=%d page=%d block=%s origin=%s', self.run_id,
                                    done + 1, segment.page + 1, segment.block_id, segment.origin)
                        segment.source_language = segment_source(segment.text, source, target, self.resolve) if not preserve_title(segment.text) else source
                        try:
                            if segment.origin == 'ocr' and segment.ocr_kind in {'noise', 'identifier', 'measurement'}:
                                segment.translated = segment.text
                                segment.policy = 'CONSERVATIVE_PRESERVE'
                                segment.preserve_reason = segment.ocr_kind
                            else:
                                segment.translated = self._pdf_translation(segment.text, segment.source_language, target)
                        except FidelityMismatch:
                            segment.translated = segment.text
                            segment.policy = 'CONSERVATIVE_PRESERVE'
                            observe('guards',['unit:fidelity'])
                            self.warning(f'Страница {segment.page + 1}, блок {segment.reading_order + 1}: числовые данные или обозначения не прошли проверку; исходный текст сохранён.')
                        segment.status = 'translated'
                    else:
                        segment.translated = self._translate(segment.text, source, target)
                if file_done:
                    durations.append(max(0, self.control.active_seconds - started))
                file_done += 1
                done += 1
                update()
            self.control.checkpoint()
            update(stage='WRITING')
            destination = self._destination(item, source, target)
            self._pipeline_source_target = (source, target)
            if getattr(self, '_pipeline_active', False):
                observe('semantic_complete', getattr(self.translate, '__self__', None))
                yield 'translated'
            handle, temporary = tempfile.mkstemp(prefix='.treetranslate-', suffix=item.path.suffix.lower(), dir=destination.parent)
            os.close(handle)
            temporary = Path(temporary)
            try:
                update(stage='WRITING')
                with timed_stage('document_write'):
                    doc.write(temporary)
                for entry in getattr(doc, 'continuations', ()):
                    segment = entry[0]
                    logger.info('run=%s continuation source_page=%d block=%s order=%d origin=%s reason=fit_overflow box=%s destination_page=%s',
                                self.run_id, segment.page + 1, segment.block_id, segment.reading_order + 1,
                                segment.origin, segment.rendered_bbox or segment.available_bbox or segment.bbox,
                                segment.continuation_page)
                logger.info('run=%s written source_pages=%d continuation_pages=%d continuation_blocks=%d',
                            self.run_id, len(getattr(doc, 'pages', ())), getattr(doc, 'continuation_count', 0),
                            len(getattr(doc, 'continuations', ())))
                update(stage='VALIDATING')
                if item.path.suffix.lower() == '.docx':
                    with timed_stage('docx_validation'):
                        validate_docx(temporary, doc.structure)
                else:
                    doc.validate(temporary)
                    for message in doc.warnings:
                        self.warning(message)
                with timed_stage('source_hash_verification'):
                    doc.assert_source_unchanged()
                logger.info('run=%s validation=passed source_sha256=%s source_unchanged=true', self.run_id, digest)
                update(stage='PUBLISHING')
                for collision in range(10000):
                    final = destination if not collision else destination.with_name(
                        f'{destination.stem} ({collision}){destination.suffix}'
                    )
                    if final.exists() or final in {f.path for f in self.files}:
                        continue
                    def publish():
                        doc.assert_source_unchanged()
                        if os.name == 'nt':
                            os.rename(temporary, final)
                        else:
                            os.link(temporary, final)
                            temporary.unlink()
                    try:
                        with timed_stage('publication'):
                            self.control.publish(publish)
                    except FileExistsError:
                        continue
                    self.completed.append(final)
                    published = True
                    observe('complete_document',item,doc,final,getattr(self.translate,'__self__',None))
                    if self.eta_estimator:
                        self.eta_estimator.published(index)
                    logger.info('run=%s published output=%s bytes=%d segments=%d pair=%s-%s elapsed=%.2f',
                                self.run_id, final, final.stat().st_size, len(doc.segments), source, target, self.control.elapsed)
                    self.outputs(tuple(self.completed))
                    self.file_completed(item.path, final)
                    break
                else:
                    raise DocumentError('Не удалось выбрать свободное имя результата.')
            finally:
                temporary.unlink(missing_ok=True)
            update(index == len(plans), stage='PUBLISHING')
        return tuple(self.completed)
