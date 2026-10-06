"""ZIP packaging adapter around the existing DocumentJob and naming methods."""
from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory, mkstemp
from zipfile import ZipFile, ZIP_DEFLATED
import shutil
import os
import logging
import unicodedata

from app.documents.errors import DocumentError, SourceChangedError
from app.documents.scanner import SourceFile
from app.documents.job import DocumentJob, safe_name
from app.documents.zip_archive import digest, inventory, extract, append_file, check_disk, validate_output, publish
from app.documents.pdf_diagnostics import timed_stage
from app.engine.languages import language_code
from app.models.translation_job import TranslationProgress
from app.documents.run_metrics import observe
from time import perf_counter
from collections import Counter
from app.engine.errors import TranslationCancelledError
from app.documents.run_metrics import document_error_record, category
from app.documents.path_translation import PathTranslation

logger = logging.getLogger('treetranslate.documents.archive')


class ArchiveJob:
    def __init__(self, owner, files, progress):
        self.owner, self.files, self.progress = owner, files, progress
        self.source = files[0].archive
        self.control = owner.control
        self.folder_names = {}
        self.path_translation = PathTranslation(owner.translate)
        self.translated_members = set()
        self.stage = 'archive_preparing'
        self.summary = dict(total_documents=0,translated_documents=0,failed_documents=0,
            source_preserved_documents=0,skipped_non_documents=0,fatal_errors=0,document_error_categories={})

    def _progress(self, stage, percent):
        previous = getattr(self, '_last_document_progress', TranslationProgress(total=0))
        self.progress(replace(previous, percent=percent, stage=stage, current_file=self.source.name,
            elapsed_seconds=int(self.control.elapsed), file_total=len(self.files), eta_scope='archive',
            eta_seconds=None, page_index=0, page_total=0, source_path=''))

    def run(self):
        prior_path_translation = self.owner.path_translation
        self.owner.path_translation = self.path_translation
        try:
            result = self._run()
            self.summary['status'] = 'COMPLETED_WITH_FAILURES' if self.summary['failed_documents'] else 'COMPLETED'
            return result
        except TranslationCancelledError:
            self.owner.run_status = self.summary['status'] = 'CANCELLED'
            raise
        except BaseException as error:
            self.owner.run_status = self.summary['status'] = 'FATAL_ARCHIVE_FAILURE'
            self.summary['fatal_errors'] += 1
            observe('archive_event','fatal',source=str(self.source),status='FATAL_ARCHIVE_FAILURE',
                stage=self.stage,primary_category='VALIDATION' if isinstance(error,SourceChangedError) else
                'ARCHIVE_SECURITY' if self.stage=='archive_preparing' else 'ARCHIVE_IO',
                secondary_categories=[],exception_type=type(error).__name__)
            raise
        finally:
            self.owner.path_translation = prior_path_translation
            self.owner.archive_summaries.append(dict(self.summary,source=str(self.source)))
            observe('archive_event','summary',source=str(self.source),**self.summary)

    def _run(self):
        source_hash = digest(self.source, self.control)
        if any(f.archive_hash and f.archive_hash != source_hash for f in self.files):
            raise SourceChangedError()
        workspace = TemporaryDirectory(prefix='TreeTranslate-zip-')
        temporary = None
        try:
            self._progress('ARCHIVE_PREPARING', 0)
            members = inventory(self.source, self.control, verify_crc=False)
            observe('archive_event','inventory',source=str(self.source),source_sha256=source_hash,scanned_members=len(members),
                accepted_members=sum(not m.directory and Path(m.name).suffix.lower() in {'.pdf','.docx'} for m in members),
                skipped_asset_members=sum(not m.directory and Path(m.name).suffix.lower() not in {'.pdf','.docx'} for m in members),unsafe_members_rejected=0,crc_status='scanner verifies before job; inventory recheck only')
            logger.info('run=%s archive_inventory source=%s sha256=%s entries=%d supported=%d bytes=%d', self.owner.run_id,
                self.source, source_hash, len(members), sum(not m.directory and Path(m.name).suffix.lower() in {'.pdf', '.docx'} for m in members), sum(m.size for m in members))
            root = Path(workspace.name)
            extracted, output = root / 'input', root / 'output'
            extracted.mkdir(); output.mkdir()
            output_parent = (self.owner.config.output or self.source.parent).resolve()
            output_parent.mkdir(parents=True, exist_ok=True)
            budget=check_disk(members, output_parent, root, self.source.stat().st_size)
            observe('archive_event','disk_preflight',source=str(self.source),budget=budget,passed=True)
            if digest(self.source, self.control) != source_hash:
                raise SourceChangedError()
            preflight_completed = perf_counter()
            observe('archive_event', 'preflight_completed', source=str(self.source))
            selected = {f.relative.as_posix(): f for f in self.files if f.path.suffix.lower() in {'.pdf', '.docx'}}
            self.summary['total_documents'] = len(selected)
            self.summary['skipped_non_documents'] = sum(not m.directory and m.name not in selected for m in members)
            original_files = {unicodedata.normalize('NFC',m.name).casefold() for m in members if not m.directory}
            original_directories = {unicodedata.normalize('NFC',PurePosixPath(*PurePosixPath(m.name).parts[:i]).as_posix()).casefold()
                for m in members for i in range(1,len(PurePosixPath(m.name).parts)+(1 if m.directory else 0))}
            target = language_code(self.owner.config.target)
            source = language_code(self.owner.config.source)
            if any(c.isalpha() for c in self.source.stem):
                source, target = self.owner.resolve(self.source.stem, source, target)
            # Names share domain evidence rather than forcing isolated short
            # labels through a context-free model. Packaging remains unchanged.
            detect = getattr(getattr(self.owner.translate, '__self__', None), 'detect_domain', None)
            engine=getattr(self.owner.translate,'__self__',None)
            profile=getattr(engine,'profile_document',None)
            archive_profile=None
            if self.owner.config.domain=='auto' and profile:
                samples=[]
                # Inspect at most two small native documents, never start OCR
                # here or retain PDF objects. The main preflight remains canonical.
                from app.documents.backends import open_document
                sample_started=perf_counter()
                with timed_stage('archive_sample'):
                    for member in [m for m in members if not m.directory and Path(m.name).suffix.lower() in {'.pdf','.docx'}][:2]:
                        if member.size>2*1024*1024:continue
                        try:
                            extract(self.source, extracted, (member,), self.control)
                            document=open_document(extracted.joinpath(*PurePosixPath(member.name).parts),self.control,self.owner.config.pdf_limits)
                            samples.append(document.sample()[:4000]);del document
                        except (SourceChangedError,OSError,TranslationCancelledError,MemoryError):
                            raise
                        except Exception:
                            continue
                        finally:
                            shutil.rmtree(extracted)
                            extracted.mkdir()
                engine.context_router.metrics['archive_sample_time']+=perf_counter()-sample_started
                with timed_stage('archive_profile'):
                    archive_profile=profile(source,target,identity=source_hash,archive=self.source.name,
                        purpose='archive',
                        folders=tuple(m.name for m in members),segments=tuple(samples))
                self.owner._context_profile=archive_profile;self.owner._snapshot=engine.context_router.snapshot(archive_profile)
                self.owner._domain=archive_profile.primary_domain
            elif self.owner.config.domain == 'auto' and detect:
                evidence = detect('\n'.join([self.source.stem] + [m.name for m in members]), source, target)
                self.owner._domain = evidence.domain
            directory_map = {'': output}
            unchanged_names = {}
            occupied = {}
            for member in members:
                if not member.directory and member.name not in selected:
                    path = PurePosixPath(member.name)
                    parent = '' if str(path.parent) == '.' else str(path.parent)
                    unchanged_names.setdefault(parent, set()).add(unicodedata.normalize('NFC', path.name).casefold())

            def unique_name(parent, name, folder=False, original_entry=None):
                used = occupied.setdefault(parent, set())
                path = Path(name)
                for index in range(10000):
                    candidate = name if not index else f'{name} ({index})' if folder else f'{path.stem} ({index}){path.suffix}'
                    key = unicodedata.normalize('NFC', candidate).casefold()
                    entry_key=unicodedata.normalize('NFC',(parent/candidate).relative_to(output).as_posix()).casefold()
                    reserved = entry_key in original_files or (not folder and entry_key in original_directories)
                    own_entry=unicodedata.normalize('NFC',original_entry or '').casefold()
                    if folder and entry_key!=own_entry and entry_key in original_directories:
                        reserved=True
                    if key not in used and not reserved and not (parent / candidate).exists():
                        used.add(key)
                        return candidate
                raise DocumentError('Не удалось выбрать свободное имя папки.')

            def directory(relative, language):
                parent = output
                key = ''
                for part in PurePosixPath(relative).parts:
                    if part == '.':
                        continue
                    occupied.setdefault(parent, set()).update(unchanged_names.get(key, ()))
                    key = (key + '/' + part).lstrip('/')
                    if key not in directory_map:
                        cache_key = (part, language, target)
                        if cache_key not in self.folder_names:
                            self.folder_names[cache_key] = safe_name(self.owner._translate(part, language, target,segment_type='FOLDER_NAME')
                                if self.owner.config.translate_directories else part)
                        name = unique_name(parent, self.folder_names[cache_key], folder=True,original_entry=key)
                        directory_map[key] = self.owner._directory((self.source, key), parent, name)
                    parent = directory_map[key]
                occupied.setdefault(parent, set()).update(unchanged_names.get(key, ()))
                return parent

            # All ORIGINAL paths above are reserved as strings. Actual output
            # directories and their translated names are created lazily.
            def progress(value):
                self._last_document_progress = value
                self.progress(replace(value, percent=min(94, 5 + int((completed_documents + value.percent / 100) * 89 / max(1, len(selected)))),
                    file_index=completed_documents + 1, file_total=len(selected),
                    processed=completed_segments + value.processed, total=completed_segments + value.total,
                    source_path=str(original.path), eta_scope='archive', eta_seconds=None,
                    file_percent=min(95, value.file_percent),
                    stage='TRANSLATING' if value.stage == 'COMPLETED' else value.stage))
            handle, name = mkstemp(prefix='.treetranslate-', suffix='.zip', dir=output_parent)
            os.close(handle)
            temporary = Path(name)
            expected = []
            copied = completed_documents = completed_segments = 0
            # Only the current input and its validated output exist on disk.
            # Assets are copied directly between streams; no full extraction tree.
            with ZipFile(self.source) as source_archive, ZipFile(temporary, 'w', compression=ZIP_DEFLATED,
                    compresslevel=6, allowZip64=True) as output_archive:
                from app.documents.pipeline import PipelineHardwarePlan, PipelineCapabilities, SchedulePolicy
                plan = getattr(self.owner, '_pipeline_plan', None)
                if plan is None:
                    capabilities = PipelineCapabilities.detect() if getattr(engine, 'runtime', None) and getattr(engine, 'context_router', None) else PipelineCapabilities(1, 1, 0, 0)
                    plan = PipelineHardwarePlan.build(capabilities)
                    self.owner._pipeline_plan = plan
                policy = getattr(self.owner, '_pipeline_policy', SchedulePolicy.ORIGINAL)
                self.pipeline_plan = plan
                if plan.depth > 1 and len(selected) > 1:
                    self.stage = 'archive_document'
                    from app.documents.archive_pipeline import run_members
                    copied, completed_documents, completed_segments = run_members(self, members, selected,
                        root=root, output=output, output_archive=output_archive, expected=expected,
                        directory=directory, unique_name=unique_name, source_language=source, target=target,
                        source_hash=source_hash, archive_profile=archive_profile,
                        preflight_completed=preflight_completed, plan=plan, policy=policy)
                else:
                    for member in members:
                        self.control.checkpoint()
                        if member.directory:
                            continue
                        relative = PurePosixPath(member.name)
                        if member.name not in selected:
                            parent = directory(relative.parent.as_posix(), source)
                            entry = (parent / relative.name).relative_to(output).as_posix()
                            with source_archive.open(member.name) as src, output_archive.open(entry, 'w', force_zip64=True) as dst:
                                while block := src.read(1024 * 1024):
                                    self.control.checkpoint()
                                    dst.write(block)
                            copied += 1
                            expected.append(entry)
                            continue
                        original = selected[member.name]
                        self.stage = 'archive_extract'
                        extract(self.source, extracted, (member,), self.control, archive=source_archive)
                        path = extracted.joinpath(*relative.parts)
                        member_hash = digest(path,self.control)
                        item = SourceFile(path, None, Path(member.name), original.size, self.source, source_hash)
                        child = DocumentJob((item,), replace(self.owner.config, output=output, parent_context=archive_profile),
                            self.control, self.owner.translate, self.owner.resolve, progress, lambda paths: None,
                            self.owner.warning, self.owner.before_ocr, self.owner.run_id)
                        child.path_translation = self.path_translation
                        child._ocr_runtime = self.owner._ocr_runtime
                        # The callback remains shared with the existing name reservation.
                        def child_destination(item, language, target):
                            parent = directory(relative.parent.as_posix(), source)
                            return parent / unique_name(parent, child._filename(item.path, language, target))
                        child.destination_override = child_destination
                        self.stage = 'archive_document'
                        started=perf_counter();failure=None
                        observe('archive_event', 'document_start', source=str(self.source), member=member.name,
                                seconds_since_preflight=started-preflight_completed)
                        try:
                            with timed_stage('archive_translate'):
                                translated = child.run()
                        except (SourceChangedError,OSError,TranslationCancelledError,MemoryError):
                            raise
                        except Exception as error:
                            failure=document_error_record(item,error,getattr(child,'_latest_progress',TranslationProgress(stage='EXTRACTING')).stage,
                                perf_counter()-started,member_hash)
                            observe('document_error',failure)
                            logger.warning('run=%s document_failed member=%s sha256=%s category=%s type=%s stage=%s',
                                self.owner.run_id,member.name,member_hash,failure['primary_category'],failure['exception_type'],failure['stage'])
                        if digest(path,self.control)!=member_hash:
                            raise SourceChangedError()
                        self.stage = 'archive_pack_member'
                        if failure:
                            # Use the exact original member path and bytes; a failed
                            # document is never labelled or counted as translated.
                            append_file(output_archive,path,member.name,self.control)
                            expected.append(member.name)
                            failure['original_member_preserved']=True
                            observe('fail_document',item,failure)
                            observe('bind_archive_member',self.source,member.name,member.name,0.,temporary.stat().st_size+member.size)
                            self.summary['failed_documents']+=1
                            self.summary['source_preserved_documents']+=1
                            categories=Counter(self.summary['document_error_categories']);categories[failure['primary_category']]+=1
                            self.summary['document_error_categories']=dict(categories)
                            self.owner.warning(f'Документ {member.name}: ошибка {failure["exception_type"]}; оригинал сохранён в архиве без перевода.')
                            completed_documents+=1
                            for partial in child.completed:
                                partial.unlink(missing_ok=True)
                            shutil.rmtree(extracted);extracted.mkdir()
                            self._progress('ARCHIVE_PACKING',min(94,5+int(completed_documents*89/max(1,len(selected)))))
                            continue
                        self._progress('ARCHIVE_PACKING', min(94, 5 + int((completed_documents + 1) * 89 / max(1, len(selected)))))
                        for translated_path in translated:
                            entry = translated_path.relative_to(output).as_posix()
                            packing_started=perf_counter();member_output_size=translated_path.stat().st_size
                            with timed_stage('archive_pack_member'):
                                append_file(output_archive, translated_path, entry, self.control)
                            observe('bind_archive_member',self.source,member.name,entry,perf_counter()-packing_started,
                                temporary.stat().st_size+member.size+member_output_size)
                            expected.append(entry)
                            translated_path.unlink()
                        completed_segments += self._last_document_progress.total
                        completed_documents += 1
                        self.summary['translated_documents']+=1
                        self.translated_members.add(member.name)
                        shutil.rmtree(extracted)
                        extracted.mkdir()
                # Preserve explicit empty directories too, after documents have
                # started. Directory records cannot trigger eager path inference.
                for member in members:
                    if member.directory:
                        self.control.checkpoint()
                        directory(member.name, source)
                for directory_path in sorted(p for p in output.rglob('*') if p.is_dir()):
                    entry = directory_path.relative_to(output).as_posix() + '/'
                    self.control.checkpoint()
                    output_archive.writestr(entry, b'')
                    expected.append(entry)
            if not expected:
                raise DocumentError('ZIP не содержит файлов или каталогов для сохранения.')
            if not selected:
                self._progress('ARCHIVE_PACKING', 95)
            self._progress('ARCHIVE_VALIDATING', 97)
            self.stage = 'archive_validate_output'
            if self.summary['translated_documents']+self.summary['source_preserved_documents']!=len(selected):
                raise DocumentError('Проверка ZIP не пройдена: не все документы обработаны.')
            validate_output(temporary, expected, self.control)
            observe('archive_event','validated',source=str(self.source),crc_status='PASS',expected_members=len(expected),temporary_bytes=temporary.stat().st_size)
            if digest(self.source, self.control) != source_hash:
                raise SourceChangedError()
            self._progress('PUBLISHING', 99)
            self.stage = 'archive_publish'
            destination = output_parent / self.owner._filename(self.source, source, target)
            final = publish(temporary, destination, self.source, source_hash, self.control)
            from app.documents.run_metrics import current,file_hash
            if current():observe('archive_event','published',source=str(self.source),source_sha256=source_hash,output=str(final),
                output_sha256=file_hash(final),output_size=final.stat().st_size,source_immutable=True,atomic=True,retries=0)
            logger.info('run=%s archive_published output=%s translated_files=%d copied_unchanged=%d skipped_unsafe=0 entries=%d sha256=%s source_unchanged=true',
                self.owner.run_id, final, completed_documents, copied, len(expected), source_hash)
            return final
        finally:
            with timed_stage('archive_cleanup'):
                if temporary:
                    temporary.unlink(missing_ok=True)
                workspace.cleanup()
            # Check even after cancellation, using a hash operation that cannot be cancelled.
            unchanged = digest(self.source, type('HashControl', (), {'checkpoint': lambda self: None})()) == source_hash
            logger.info('run=%s archive_cleanup workspace_removed=%s source_unchanged=%s', self.owner.run_id,
                not Path(workspace.name).exists(), unchanged)
            observe('archive_event','cleanup',source=str(self.source),workspace_removed=not Path(workspace.name).exists(),source_immutable=unchanged)
            if not unchanged:
                raise SourceChangedError()
