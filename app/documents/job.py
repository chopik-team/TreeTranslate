"""Qt-free document orchestration; translation is supplied by the existing router."""
from dataclasses import dataclass
from pathlib import Path
import os
import re
import tempfile
import logging

from app.documents.docx_document import DocxDocument, validate_docx
from app.documents.errors import DocumentError, SourceChangedError
from app.engine.languages import language_code
from app.engine.types import TranslationRequest, DevicePreference, PerformanceProfile
from app.models.translation_job import TranslationProgress

logger = logging.getLogger(__name__)


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .')[:120]
    if not value or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        value = '_' + value
    return value


def safe_filename_base(value, fallback):
    """Sanitize a translated filename stem, falling back to the original stem."""
    def clean(candidate):
        candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', candidate).rstrip(' .')[:120]
        if not candidate or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', candidate, re.I):
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


class DocumentJob:
    def __init__(self, files, config, control, translate, resolve, progress=lambda p: None, outputs=lambda p: None):
        self.files, self.config, self.control = tuple(files), config, control
        self.translate, self.resolve, self.progress, self.outputs = translate, resolve, progress, outputs
        self.completed = []
        self.directories = {}

    def _translate(self, text, source, target, empty_fallback=None):
        self.control.checkpoint()
        if source == target or not any(c.isalpha() for c in text):
            return text
        c = self.config
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        result = self.translate(TranslationRequest(text.strip(), source, target, c.device, c.profile, cpu_threads=c.threads), self.control.cancelled)
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

    def _destination(self, item, source, target):
        c = self.config
        parent = c.output or item.path.parent
        if item.root:
            name = self._translate(item.root.name, source, target) if c.translate_directories else item.root.name
            name = safe_name(c.template.replace('{name}', name).replace('{lang}', target))
            parent = self._directory(item.root, c.output or item.root.parent, name)
            original = item.root
            for part in item.relative.parts[:-1]:
                original = original / part
                name = self._translate(part, source, target) if c.translate_directories else part
                parent = self._directory(original, parent, safe_name(name))
        parent.mkdir(parents=True, exist_ok=True)
        original_name = item.path.stem
        if c.translate_filenames:
            translated_name = self._translate(original_name, source, target, empty_fallback=original_name)
            base_name = safe_filename_base(translated_name, original_name)
        else:
            base_name = original_name
        name = safe_name(c.template.replace('{name}', base_name).replace('{lang}', target))
        return parent.resolve() / (name + item.path.suffix)

    def run(self):
        if not self.files:
            raise DocumentError('Выберите хотя бы один DOCX. Формат пока не поддерживается для других файлов.')
        target = language_code(self.config.target)
        if target == 'auto':
            raise DocumentError('Выберите язык перевода явно.')
        plans = []
        for index, item in enumerate(self.files, 1):
            self.control.checkpoint()
            self.progress(TranslationProgress(total=0, current_file=item.path.name, file_index=index,
                                               file_total=len(self.files), elapsed_seconds=int(self.control.elapsed)))
            doc = DocxDocument(item.path)
            source, target = self.resolve(doc.sample(), self.config.source, target) if doc.segments else (target, target)
            plans.append((item, doc.source_hash, source, len(doc.segments)))
        total = sum(p[3] for p in plans)
        done = 0
        for index, (item, digest, source, _) in enumerate(plans, 1):
            self.control.checkpoint()
            doc = DocxDocument(item.path)
            if doc.source_hash != digest:
                raise SourceChangedError()
            def update(finished=False):
                percent = 100 if finished else min(99, int(100 * done / total)) if total else 0
                eta = round(self.control.active_seconds * (total - done) / done) if done else None
                self.progress(TranslationProgress(percent, done, total, item.path.name, int(self.control.elapsed), index, len(plans), eta))
            update()
            for segment in doc.segments:
                segment.translated = self._translate(segment.text, source, target)
                done += 1
                update()
            self.control.checkpoint()
            destination = self._destination(item, source, target)
            handle, temporary = tempfile.mkstemp(prefix='.treetranslate-', suffix='.docx', dir=destination.parent)
            os.close(handle)
            temporary = Path(temporary)
            try:
                doc.write(temporary)
                validate_docx(temporary, doc.structure)
                doc.assert_source_unchanged()
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
                        self.control.publish(publish)
                    except FileExistsError:
                        continue
                    self.completed.append(final)
                    logger.info('DOCX completed source=%s bytes=%d segments=%d pair=%s-%s output=%s elapsed=%.2f',
                                item.path, item.size, len(doc.segments), source, target, final, self.control.elapsed)
                    self.outputs(tuple(self.completed))
                    break
                else:
                    raise DocumentError('Не удалось выбрать свободное имя результата.')
            finally:
                temporary.unlink(missing_ok=True)
            update(index == len(plans))
        return tuple(self.completed)
