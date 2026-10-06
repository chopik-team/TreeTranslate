"""Archive adapter for the existing child stages and recovery policy."""
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from time import perf_counter
from zipfile import ZipFile
from collections import Counter
import shutil
import sys

from app.documents.job import DocumentJob
from app.documents.scanner import SourceFile
from app.documents.zip_archive import extract, digest, append_file
from app.documents.errors import SourceChangedError
from app.engine.errors import TranslationCancelledError
from app.documents.run_metrics import observe, document_error_record
from app.documents.pdf_diagnostics import timed_stage
from app.models.translation_job import TranslationProgress
from app.documents.pipeline import StagedPipeline, SchedulePolicy, WorkItem, MIB


def detached_bytes(value, seen=None):
    """Account detached IR once, excluding library/runtime/shared callables."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        return size+sum(detached_bytes(k, seen)+detached_bytes(v, seen) for k,v in value.items())
    if isinstance(value, (list, tuple, set)):
        return size+sum(detached_bytes(v, seen) for v in value)
    if hasattr(value, '__dict__') and value.__class__.__module__.startswith('app.documents'):
        return size+detached_bytes(vars(value), seen)
    return size


@dataclass
class PreparedMember:
    member: object
    source_root: Path
    item: object = None
    child: object = None
    stages: object = None
    source_hash: str = ''
    started: float = 0.


def run_members(archive, members, selected, *, root, output, output_archive,
                expected, directory, unique_name, source_language, target,
                source_hash, archive_profile, preflight_completed, plan, policy):
    pipeline = StagedPipeline(plan, archive.control, policy)
    counts = dict(copied=0, documents=0, segments=0)
    private = root/'results'
    private.mkdir()

    class StageControl:
        def checkpoint(self):
            pipeline.checkpoint()
        def publish(self, action):
            def checked():
                pipeline.checkpoint()
                return action()
            return archive.control.publish(checked)
        def __getattr__(self, name):
            return getattr(archive.control, name)
    control = StageControl()

    def items():
        for seq, member in enumerate(members):
            if member.directory:
                continue
            # Conservative detached IR lease, not an eager extraction or scan.
            estimate = max(32*MIB, member.size*16) if member.name in selected else 0
            value = PreparedMember(member, root/'input'/str(seq))
            yield WorkItem(seq, member, estimate, member.size, value=value)

    def destination(data, item, language, target):
        relative = PurePosixPath(data.member.name)
        parent = directory(relative.parent.as_posix(), source_language)
        return parent/unique_name(parent, data.child._filename(item.path, language, target))

    def prepare(work):
        data = work.value
        member = data.member
        if member.name not in selected:
            return data
        data.started = perf_counter()
        data.source_root.mkdir(parents=True)
        with ZipFile(archive.source) as reader:
            extract(archive.source, data.source_root, (member,), control, archive=reader)
        path = data.source_root.joinpath(*PurePosixPath(member.name).parts)
        data.source_hash = digest(path, control)
        original = selected[member.name]
        data.item = SourceFile(path, None, Path(member.name), original.size, archive.source, source_hash)

        def progress(value):
            archive._last_document_progress = value
            archive.progress(replace(value, percent=min(94, 5+int((counts['documents']+value.percent/100)*89/max(1,len(selected)))),
                file_index=counts['documents']+1, file_total=len(selected),
                processed=counts['segments']+value.processed, total=counts['segments']+value.total,
                source_path=str(original.path), eta_scope='archive', eta_seconds=None,
                file_percent=min(95,value.file_percent),
                stage='TRANSLATING' if value.stage=='COMPLETED' else value.stage))

        child = data.child = DocumentJob((data.item,), replace(archive.owner.config,
            output=output, parent_context=archive_profile), control, archive.owner.translate,
            archive.owner.resolve, progress, lambda paths: None, archive.owner.warning,
            archive.owner.before_ocr, archive.owner.run_id)
        child.path_translation = archive.path_translation
        child._ocr_runtime = archive.owner._ocr_runtime
        child._pipeline_active = True
        child._pipeline_router_factory = pipeline.gpu.router
        if pipeline.policy == SchedulePolicy.ORIGINAL:
            child.destination_override = lambda item, language, target: destination(data,item,language,target)
        else:
            # The writer's private path never participates in final collision
            # allocation. Canonical names are allocated by the commit owner.
            private_doc = private/str(work.sequence_id)
            private_doc.mkdir()
            child.destination_override = lambda item, language, target: private_doc/item.path.name
        observe('archive_event','document_start',source=str(archive.source),member=member.name,
            sequence_id=work.sequence_id,seconds_since_preflight=perf_counter()-preflight_completed)
        data.stages = child._document_stages()
        assert next(data.stages) == 'prepared'
        work.current_bytes = detached_bytes(child._prepared_document)
        # Retained bytes must fit the admission lease. An exceptional source is
        # processed serially instead of retaining an unbounded prepared object.
        if work.current_bytes > work.estimated_bytes:
            data.stages.close()
            data.stages = None
            child._prepared_document = None
            child._pipeline_active = False
            work.current_bytes = 0
            data.serial_fallback = True
            work.requires_serial = True
        return data

    def translate(work):
        data = work.value
        if data.child is not None:
            if getattr(data, 'serial_fallback', False):
                from app.ocr.router.ocr_router import OcrRouter
                data.child._pipeline_router_factory = OcrRouter
                data.child._run_documents()
            else:
                assert next(data.stages) == 'translated'
        return data

    def write(work):
        data = work.value
        if data.stages is not None:
            try:
                next(data.stages)
            except StopIteration:
                pass
            else:
                raise RuntimeError('Unexpected document stage after writer')
        return data

    def commit(work):
        data = work.value
        member = data.member
        if work.error is not None and data.item is None:
            # Extraction/preflight container failures occur before a child
            # exists. Keep the original global exception, never mask it by
            # dereferencing an absent SourceFile or preserve a partial input.
            raise work.error
        if work.error is not None and isinstance(work.error, (SourceChangedError,OSError,TranslationCancelledError,MemoryError)):
            raise work.error
        archive.stage = 'archive_pack_member'
        if member.name not in selected:
            relative = PurePosixPath(member.name)
            parent = directory(relative.parent.as_posix(),source_language)
            entry = (parent/relative.name).relative_to(output).as_posix()
            with ZipFile(archive.source) as reader, reader.open(member.name) as src, output_archive.open(entry,'w',force_zip64=True) as dst:
                while block := src.read(1024*1024):
                    control.checkpoint()
                    dst.write(block)
            counts['copied'] += 1
            expected.append(entry)
            return
        if digest(data.item.path,control) != data.source_hash:
            raise SourceChangedError()
        canonical_destination = None
        if pipeline.policy == SchedulePolicy.EASY_FIRST and hasattr(data.child, '_pipeline_source_target'):
            # Serial naming reserves even a document whose writer later fails.
            # Preserve that collision effect, not merely successful names.
            canonical_destination = destination(data,data.item,*data.child._pipeline_source_target)
        if work.error is not None:
            failure = document_error_record(data.item, work.error,
                getattr(data.child,'_latest_progress',TranslationProgress(stage='EXTRACTING')).stage,
                perf_counter()-data.started, data.source_hash)
            observe('document_error',failure)
            append_file(output_archive,data.item.path,member.name,control)
            expected.append(member.name)
            failure['original_member_preserved'] = True
            observe('fail_document',data.item,failure)
            observe('bind_archive_member',archive.source,member.name,member.name,0.,output_archive.fp.tell()+member.size)
            archive.summary['failed_documents'] += 1
            archive.summary['source_preserved_documents'] += 1
            categories = Counter(archive.summary['document_error_categories'])
            categories[failure['primary_category']] += 1
            archive.summary['document_error_categories'] = dict(categories)
            archive.owner.warning(f'Документ {member.name}: ошибка {failure["exception_type"]}; оригинал сохранён в архиве без перевода.')
        else:
            for path in data.child.completed:
                final = path if pipeline.policy == SchedulePolicy.ORIGINAL else canonical_destination
                entry = final.relative_to(output).as_posix()
                start = perf_counter()
                size = path.stat().st_size
                with timed_stage('archive_pack_member'):
                    append_file(output_archive,path,entry,control)
                observe('bind_archive_member',archive.source,member.name,entry,perf_counter()-start,
                    output_archive.fp.tell()+member.size+size)
                expected.append(entry)
                path.unlink()
            counts['segments'] += getattr(data.child,'_latest_progress',TranslationProgress()).total
            archive.summary['translated_documents'] += 1
            archive.translated_members.add(member.name)
        counts['documents'] += 1
        archive._progress('ARCHIVE_PACKING',min(94,5+int(counts['documents']*89/max(1,len(selected)))))

    def cleanup(work):
        data = work.value
        if data.stages is not None:
            data.stages.close()
        if data.child:
            data.child._prepared_document = None
            for path in data.child.completed:
                path.unlink(missing_ok=True)
        if data.source_root.exists():
            shutil.rmtree(data.source_root)
        private_doc = private/str(work.sequence_id)
        if private_doc.exists():
            shutil.rmtree(private_doc)
        work.value = None
        work.current_bytes = 0

    try:
        pipeline.run(items(),prepare,translate,write,commit,cleanup)
    finally:
        archive.pipeline_metrics = dict(pipeline.metrics)
        observe('archive_event','pipeline',source=str(archive.source),plan=plan.as_dict(),
            policy=pipeline.policy.value,metrics=archive.pipeline_metrics)
        private.rmdir()
    return counts['copied'], counts['documents'], counts['segments']
