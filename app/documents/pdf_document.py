"""One PDFium writer for native text replacement and explicit raster OCR masks."""
import ctypes
from hashlib import sha256
import math
from pathlib import Path
from threading import RLock
import unicodedata

import pypdfium2 as pdfium
import pypdfium2.raw as raw

from app.documents.docx_document import URL
from app.documents.errors import DocumentError, SourceChangedError
from app.documents.pdf_fonts import FontResolver
from app.documents.pdf_layout import group_spans, fit, wrap, FittedText
from app.documents.pdf_diagnostics import diagnostic, context, preserved
from app.documents.pdf_regions import assign_regions, flow_boxes
from app.documents.pdf_types import PdfError, PdfKind, PdfLimits, PdfSegment, PdfPageInfo, ExtractedPage

# PDFium is process-global and not thread-safe, including calls on separate documents.
PDF_LOCK = RLock()


def wide(text):
    return ctypes.cast(ctypes.create_string_buffer(text.encode('utf-16-le') + b'\0\0'), raw.FPDF_WIDESTRING)


def meaningful(text):
    return ''.join(c for c in URL.sub('', text) if c.isalpha() and c != '\ufffd')


def page_info(page, objects):
    preserved = []
    for obj in objects:
        if obj.type != raw.FPDF_PAGEOBJ_TEXT:
            colors = []
            for getter in (raw.FPDFPageObj_GetFillColor, raw.FPDFPageObj_GetStrokeColor):
                values = [ctypes.c_uint() for _ in range(4)]
                colors.append(tuple(v.value for v in values) if getter(obj, *values) else None)
            preserved.append((obj.type, tuple(round(v, 2) for v in obj.get_bounds()), tuple(colors)))
    return PdfPageInfo(page.get_size(), page.get_bbox(), page.get_rotation(),
                       raw.FPDFPage_GetAnnotCount(page), tuple(preserved))


class NativeTextExtractor:
    """Future extractors can return ExtractedPage; writer consumes the same segment contract."""
    def extract(self, page, page_index, objects, limits):
        result = ExtractedPage()
        textpage = page.get_textpage()
        try:
            if textpage.count_chars() > limits.max_text_chars:
                raise PdfError(PdfKind.UNSUPPORTED_PDF)
            spans = []
            empty_objects = []
            for index, obj in enumerate(objects):
                state = dict(page=page_index + 1, object_index=index, object_type=obj.type, policy='SUPPORTED')
                result.object_states.append(state)
                if obj.type == raw.FPDF_PAGEOBJ_FORM:
                    state['policy'] = 'CONSERVATIVE_PRESERVE'
                    preserved('extract', 'nested_form_preserved', page_index + 1, index, obj.type)
                    result.warnings.append(f'Страница {page_index + 1}: содержимое Form XObject сохранено без перевода.')
                if obj.type != raw.FPDF_PAGEOBJ_TEXT:
                    continue
                try:
                    obj.textpage = textpage
                    text = obj.extract().replace('\r', ' ').replace('\n', ' ')
                    if not text.strip():
                        empty_objects.append((index, obj))
                        continue
                    matrix = obj.get_matrix()
                    angle = math.degrees(math.atan2(matrix.b, matrix.a)) % 360
                    rotation = (round(angle / 90) * 90) % 360
                    skew = abs(matrix.a * matrix.c + matrix.b * matrix.d)
                    mode = raw.FPDFTextObj_GetTextRenderMode(obj)
                    bounds = obj.get_bounds()
                    clip = raw.FPDFPageObj_GetClipPath(obj)
                    clipped = bool(clip and raw.FPDFClipPath_CountPaths(clip) > 0)
                    page_bounds = page.get_bbox()
                    outside = bounds[0] < page_bounds[0] - .1 or bounds[1] < page_bounds[1] - .1 or bounds[2] > page_bounds[2] + .1 or bounds[3] > page_bounds[3] + .1
                    if (mode != raw.FPDF_TEXTRENDERMODE_FILL or min(abs(angle - rotation), abs(angle - rotation - 360)) > 1
                            or skew > .01 or clipped or outside or not all(math.isfinite(v) for v in bounds)
                            or any(unicodedata.bidirectional(c) in {'R', 'AL'} for c in text)
                            or '\ufffd' in text):
                        state['policy'] = 'CONSERVATIVE_PRESERVE'
                        preserved('extract', 'unsupported_text_geometry', page_index + 1, index, obj.type)
                        result.warnings.append(f'Страница {page_index + 1}: сложный или невидимый текст сохранён без перевода.')
                        continue
                    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                        continue
                    color = [ctypes.c_uint() for _ in range(4)]
                    raw.FPDFPageObj_GetFillColor(obj, *color)
                    font_size = obj.get_font_size() * math.hypot(matrix.a, matrix.b)
                    state['policy'] = 'TRANSLATABLE'
                    spans.append(PdfSegment(page_index, str(index), text, bounds, index,
                                            (obj.get_font().get_base_name(),), font_size, rotation=rotation,
                                            object_indices=(index,), color=tuple(c.value for c in color), baseline=matrix.f))
                except pdfium.PdfiumError:
                    state['policy'] = 'CONSERVATIVE_PRESERVE'
                    preserved('extract', 'text_object', page_index + 1, index, obj.type)
                    result.warnings.append(f'Неподдерживаемый объект на странице {page_index + 1} сохранён без изменений.')
            # PDFium suppresses duplicate glyph text in faux-bold overprints.
            # Keep both paint objects linked when their font and glyph geometry
            # match (the second copy is offset by a fraction of a point).
            for index, obj in empty_objects:
                b = obj.get_bounds()
                if b[2]-b[0] <= 0 or b[3]-b[1] <= 0:
                    continue
                match = next((span for span in spans
                              if abs(span.bbox[0]-b[0]) <= .5 and abs(span.bbox[1]-b[1]) < .05
                              and abs((span.bbox[2]-span.bbox[0])-(b[2]-b[0])) < .05
                              and abs((span.bbox[3]-span.bbox[1])-(b[3]-b[1])) < .05
                              and span.font_names == (obj.get_font().get_base_name(),)), None)
                if match:
                    match.object_indices += (index,)
            result.segments = group_spans(page_index, spans, limits.max_segment_chars)
            assign_regions(page, objects, result.segments)
            return result
        finally:
            textpage.close()


class PdfDocument:
    def __init__(self, path, limits=None, checkpoint=lambda: None, extractor=None):
        self.path = Path(path)
        self.limits = limits or PdfLimits.load()
        self.checkpoint = checkpoint
        self.segments, self.pages, self.warnings = [], [], []
        self.object_states = []
        self.classification = PdfKind.CORRUPTED_PDF
        if self.path.stat().st_size > self.limits.max_file_bytes:
            raise PdfError(PdfKind.UNSUPPORTED_PDF)
        self.source_bytes = self.path.read_bytes()
        self.source_hash = sha256(self.source_bytes).hexdigest()
        if not self.source_bytes[:1024].lstrip().startswith(b'%PDF-'):
            raise PdfError(PdfKind.CORRUPTED_PDF)
        with PDF_LOCK:
            document = self._open(self.source_bytes)
            try:
                if raw.FPDF_GetSecurityHandlerRevision(document) >= 0:
                    raise PdfError(PdfKind.ENCRYPTED_PDF)
                if not 0 < len(document) <= self.limits.max_pages:
                    raise PdfError(PdfKind.UNSUPPORTED_PDF)
                extractor = extractor or NativeTextExtractor()
                images, all_objects, chars, usable = 0, 0, 0, 0
                for index in range(len(document)):
                    checkpoint()
                    page = document[index]
                    try:
                        if raw.FPDFPage_CountObjects(page) > self.limits.max_objects_per_page:
                            raise PdfError(PdfKind.UNSUPPORTED_PDF)
                        objects = list(page.get_objects(max_depth=1))
                        info = page_info(page, objects)
                        if not all(0 < s <= self.limits.max_page_points for s in info.size):
                            raise PdfError(PdfKind.UNSUPPORTED_PDF)
                        self.pages.append(info)
                        with diagnostic('extract', 'extract_page', index + 1):
                            extracted = extractor.extract(page, index, objects, self.limits)
                        self.warnings.extend(extracted.warnings)
                        self.object_states.extend(extracted.object_states)
                        self.segments.extend(extracted.segments)
                        images += sum(o.type == raw.FPDF_PAGEOBJ_IMAGE for o in objects)
                        all_objects += len(objects)
                        for block in extracted.segments:
                            chars += len(block.text)
                            usable += len(meaningful(block.text))
                        if chars > self.limits.max_text_chars:
                            raise PdfError(PdfKind.UNSUPPORTED_PDF)
                    finally:
                        page.close()
                substantial = usable >= (1 if getattr(extractor,'ocr_used',False) else 20 if images else 4)
                if not substantial:
                    if getattr(extractor,'ocr_used',False):
                        from app.ocr.errors import OcrError
                        raise OcrError('confidence')
                    kind = PdfKind.IMAGE_ONLY_PDF if images else PdfKind.UNSUPPORTED_PDF if all_objects else PdfKind.EMPTY_PDF
                    raise PdfError(kind)
                self.classification = PdfKind.MIXED_PDF if images else PdfKind.TEXT_PDF
                if getattr(extractor, 'ocr_used', False) and all(s.origin == 'ocr' for s in self.segments):
                    self.classification = PdfKind.SCANNED_PDF
                if images and not getattr(extractor, 'ocr_used', False):
                    self.warnings.append('Будет переведён текстовый слой. Текст внутри изображений останется без изменений.')
                # Numeric/URL-only blocks are kept as original objects, never sent to the router.
                self.segments = [s for s in self.segments if meaningful(s.text)]
                if not self.segments:
                    raise PdfError(PdfKind.EMPTY_PDF)
                self.structure = tuple(self.pages)
            except pdfium.PdfiumError:
                raise PdfError(PdfKind.CORRUPTED_PDF) from None
            finally:
                document.close()

    @staticmethod
    def _open(data):
        try:
            return pdfium.PdfDocument(data)
        except pdfium.PdfiumError as error:
            kind = PdfKind.ENCRYPTED_PDF if error.err_code == raw.FPDF_ERR_PASSWORD else PdfKind.CORRUPTED_PDF
            raise PdfError(kind, context('classify', 'FPDF_LoadMemDocument', native_code=error.err_code)) from None

    def sample(self):
        count = min(24, len(self.segments))
        indices = sorted({round(i * (len(self.segments) - 1) / max(1, count - 1)) for i in range(count)})
        return '\n'.join(URL.sub('', self.segments[i].text)[:320] for i in indices)

    def assert_source_unchanged(self):
        try:
            if sha256(self.path.read_bytes()).hexdigest() != self.source_hash:
                raise SourceChangedError()
        except OSError:
            raise SourceChangedError() from None

    def write(self, output):
        with PDF_LOCK:
            document = self._open(self.source_bytes)
            fonts = FontResolver()
            self.continuations = []
            self.continuation_count = 0
            self.added_non_text = {}
            try:
                for index in range(len(document)):
                    self.checkpoint()
                    page = document[index]
                    try:
                        objects = list(page.get_objects(max_depth=1))
                        page_segments = [s for s in self.segments if s.page == index]
                        flow_boxes(page_segments, fonts)
                        prepared_faces = {}
                        font_requests = []
                        for segment in page_segments:
                            text = segment.translated if segment.translated is not None else segment.text
                            if text == segment.text:
                                continue
                            original = objects[segment.object_indices[0]] if segment.object_indices else None
                            try:
                                face = fonts.resolve(text + '[...]Продолжение: 0123456789.', original)
                            except DocumentError:
                                segment.policy = 'CONSERVATIVE_PRESERVE'
                                segment.visible_text = segment.text
                                preserved('font', 'local_font_coverage', index + 1, segment.object_indices[0] if segment.object_indices else None, raw.FPDF_PAGEOBJ_TEXT)
                                self.warnings.append(f'Страница {index + 1}: исходный блок сохранён, подходящий локальный шрифт не найден.')
                                continue
                            prepared_faces[segment.block_id] = face
                            font_requests.append((face, text + '[...]Продолжение: 0123456789.'))
                        fonts.prepare(document, font_requests, cache_key=('page', index))
                        # All raster masks precede all replacement text. Reflow
                        # may move a line into another original line's rectangle.
                        for segment in page_segments:
                            if segment.origin != 'ocr' or segment.block_id not in prepared_faces:
                                continue
                            for x,y,r,t in segment.raster_boxes or (segment.bbox,):
                                # Include the anti-aliased fringe around detected glyphs.
                                x,y=max(0,x-.65),max(0,y-.65)
                                r,t=min(self.pages[index].bounds[2],r+.65),min(self.pages[index].bounds[3],t+.65)
                                mask = pdfium.PdfObject(raw.FPDFPageObj_CreateNewRect(x,y,r-x,t-y),pdf=document)
                                raw.FPDFPageObj_SetFillColor(mask,*segment.background_color)
                                raw.FPDFPath_SetDrawMode(mask,raw.FPDF_FILLMODE_WINDING,False)
                                page.insert_obj(mask)
                                self.added_non_text.setdefault(index,[]).extend(page_info(page,[mask]).non_text)
                        changed = False
                        for segment in page_segments:
                            self.checkpoint()
                            text = segment.translated if segment.translated is not None else segment.text
                            if text == segment.text:
                                segment.visible_text = text if segment.origin == 'native' else None
                                continue
                            original = objects[segment.object_indices[0]] if segment.object_indices else None
                            face = prepared_faces.get(segment.block_id)
                            if face is None:
                                continue
                            box = segment.rendered_bbox or segment.available_bbox or segment.bbox
                            fitted = fit(text, face, box, segment.layout_font_size or max(8, segment.font_size), 8, segment.rotation)
                            font = fonts.embed(document, face, text + '[...]Продолжение: 0123456789.', cache_key=('page', index))
                            if fitted.overflow:
                                self.continuations.append((segment, text))
                                # Full content is placed in readable continuation blocks,
                                # with no annotation wall and no silent truncation.
                                marker = fit(f'Продолжение: {segment.page + 1}.{segment.reading_order + 1}', face, box, 8, 8, segment.rotation)
                                if marker.overflow:
                                    marker=fit('[...]',face,box,8,8,segment.rotation)
                                fitted = FittedText(marker.lines if not marker.overflow else [], 8,
                                                    marker.ascent, marker.leading, False)
                                segment.overflow_text = text
                                self.warnings.append(f'Страница {index + 1}, блок {segment.reading_order + 1}: полный перевод в продолжении документа.')
                            # Construct all replacement objects before removing any original.
                            replacements = []
                            try:
                                for line_index, line in enumerate(fitted.lines):
                                    if not line:
                                        continue
                                    obj = pdfium.PdfObject(raw.FPDFPageObj_CreateTextObj(document, font, fitted.size), pdf=document)
                                    replacements.append(obj)
                                    if not raw.FPDFText_SetText(obj, wide(line)):
                                        raise PdfError(PdfKind.UNSUPPORTED_PDF)
                                    raw.FPDFPageObj_SetFillColor(obj, *segment.color)
                                    left, bottom, right, top = box
                                    if segment.alignment == 'center':
                                        left += max(0, (right-left-face.width(line, fitted.size))/2)
                                    offset = fitted.ascent + line_index * fitted.leading
                                    transforms = {0: (1, 0, 0, 1, left, top - offset),
                                                  90: (0, 1, -1, 0, left + offset, bottom),
                                                  180: (-1, 0, 0, -1, right, bottom + offset),
                                                  270: (0, -1, 1, 0, right - offset, top)}
                                    obj.set_matrix(pdfium.PdfMatrix(*transforms[segment.rotation]))
                                # Preserve painting order: insert at the original object's position.
                                if original is None:
                                    position = raw.FPDFPage_CountObjects(page)
                                else:
                                    address = ctypes.cast(original.raw, ctypes.c_void_p).value
                                    position = next(i for i in range(raw.FPDFPage_CountObjects(page))
                                                    if ctypes.cast(raw.FPDFPage_GetObject(page, i), ctypes.c_void_p).value == address)
                                for offset, obj in enumerate(replacements):
                                    if not raw.FPDFPage_InsertObjectAtIndex(page, obj, position + offset):
                                        raise PdfError(PdfKind.UNSUPPORTED_PDF)
                                    # Same ownership handoff as pinned pypdfium2 PdfPage.insert_obj.
                                    obj._detach_finalizer()
                                    obj.page = page
                                    obj.pdf = document
                                    segment.written_boxes += (obj.get_bounds(),)
                                for object_index in segment.object_indices:
                                    old = objects[object_index]
                                    page.remove_obj(old)
                                    old.close()
                            finally:
                                for obj in replacements:
                                    if obj.page is None:
                                        obj.close()
                            segment.visible_text = '\n'.join(fitted.lines)
                            segment.status = 'continuation' if segment.overflow_text else 'written'
                            changed = True
                        if changed:
                            # PDFium content regeneration may lose inherited CMYK/
                            # ICC color spaces. Pin their rendered RGBA explicitly.
                            for obj in page.get_objects(max_depth=1):
                                for getter, setter in ((raw.FPDFPageObj_GetFillColor, raw.FPDFPageObj_SetFillColor),
                                                       (raw.FPDFPageObj_GetStrokeColor, raw.FPDFPageObj_SetStrokeColor)):
                                    color = [ctypes.c_uint() for _ in range(4)]
                                    if getter(obj, *color):
                                        setter(obj, *(c.value for c in color))
                            with diagnostic('write', 'FPDFPage_GenerateContent', index + 1):
                                page.gen_content()
                    finally:
                        page.close()
                self._write_continuations(document, fonts)
                self.checkpoint()
                with diagnostic('write', 'FPDF_SaveAsCopy'):
                    document.save(output, flags=raw.FPDF_NO_INCREMENTAL)
            finally:
                fonts.close()
                document.close()

    def _write_continuations(self, document, fonts):
        page = None
        cursor = 0
        width, height = self.pages[0].size
        try:
            for segment, text in self.continuations:
                self.checkpoint()
                face = fonts.resolve(text)
                lines = wrap(text, face, 11, width - 72)
                segment.continuation_lines = tuple(lines)
                for line_index, line in enumerate(lines):
                    if page is None or cursor < (78 if line_index == 0 else 48):
                        if page is not None:
                            page.gen_content()
                            page.close()
                        if len(document) >= self.limits.max_pages:
                            raise PdfError(PdfKind.UNSUPPORTED_PDF, context('write', 'continuation_page_limit'))
                        page = document.new_page(width, height)
                        self.continuation_count += 1
                        cursor = height - 42
                        heading = 'Продолжение перевода'
                        self._insert_line(document, page, fonts, heading, 10, 36, cursor)
                        cursor -= 24
                    if line_index == 0:
                        segment.continuation_page = len(document)
                        self._insert_line(document, page, fonts, f'Страница {segment.page + 1} · блок {segment.reading_order + 1}', 9, 36, cursor)
                        cursor -= 16
                    self._insert_line(document, page, fonts, line, 11, 36, cursor)
                    cursor -= 14
                cursor -= 10
            if page is not None:
                page.gen_content()
        finally:
            if page is not None:
                page.close()

    @staticmethod
    def _insert_line(document, page, fonts, text, size, x, y):
        face = fonts.resolve(text)
        font = fonts.embed(document, face, text)
        obj = pdfium.PdfObject(raw.FPDFPageObj_CreateTextObj(document, font, size), pdf=document)
        if not raw.FPDFText_SetText(obj, wide(text)):
            obj.close()
            raise PdfError(PdfKind.UNSUPPORTED_PDF, context('replace', 'FPDFText_SetText'))
        obj.set_matrix(pdfium.PdfMatrix(e=x, f=y))
        page.insert_obj(obj)

    @staticmethod
    def _annotation(page, segment, text):
        annotation = raw.FPDFPage_CreateAnnot(page, raw.FPDF_ANNOT_TEXT)
        if not annotation:
            raise PdfError(PdfKind.UNSUPPORTED_PDF)
        try:
            left, bottom, right, top = segment.bbox
            # Keep the viewer's note icon outside text rather than covering the
            # first translated word. Check neighboring text/images and notes.
            bounds = page.get_bbox()
            occupied = [o.get_bounds() for o in page.get_objects(max_depth=1)
                        if o.type in {raw.FPDF_PAGEOBJ_TEXT, raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_FORM}]
            for i in range(raw.FPDFPage_GetAnnotCount(page) - 1):
                other = raw.FPDFPage_GetAnnot(page, i)
                rect = raw.FS_RECTF()
                if raw.FPDFAnnot_GetRect(other, rect):
                    occupied.append((rect.left, rect.bottom, rect.right, rect.top))
                raw.FPDFPage_CloseAnnot(other)
            candidates = [(left - 22, top - 16, left - 6, top),
                          (right + 6, top - 16, right + 22, top)]
            candidates.extend((bounds[0] + 3, y - 16, bounds[0] + 19, y)
                              for y in range(int(bounds[3]) - 3, int(bounds[1]) + 16, -20))
            def free(box):
                return (box[0] >= bounds[0] and box[1] >= bounds[1]
                        and box[2] <= bounds[2] and box[3] <= bounds[3]
                        and not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1]
                                    for b in occupied))
            box = next((b for b in candidates if free(b)), None)
            if box is None:
                # No safe icon position: keep a list-accessible note without
                # obscuring content. The visible [...] and UI warning remain.
                box = (left, top, left, top)
                raw.FPDFAnnot_SetFlags(annotation, raw.FPDF_ANNOT_FLAG_NOVIEW)
            rectangle = raw.FS_RECTF(box[0], box[3], box[2], box[1])
            if not (raw.FPDFAnnot_SetRect(annotation, rectangle)
                    and raw.FPDFAnnot_SetStringValue(annotation, b'Contents', wide(text))
                    and raw.FPDFAnnot_SetStringValue(annotation, b'T', wide('TreeTranslate'))):
                raise PdfError(PdfKind.UNSUPPORTED_PDF)
        finally:
            raw.FPDFPage_CloseAnnot(annotation)

    def validate(self, output):
        if not Path(output).is_file() or not Path(output).stat().st_size:
            raise PdfError(PdfKind.CORRUPTED_PDF)
        with PDF_LOCK:
            document = self._open(Path(output).read_bytes())
            try:
                if len(document) != len(self.pages) + getattr(self, 'continuation_count', 0):
                    raise PdfError(PdfKind.CORRUPTED_PDF)
                for index, before in enumerate(self.pages):
                    self.checkpoint()
                    page = document[index]
                    try:
                        after = page_info(page, list(page.get_objects(max_depth=1)))
                        if (any(abs(a-b) > .1 for a, b in zip(before.size, after.size)) or before.rotation != after.rotation
                                or before.non_text + tuple(getattr(self,'added_non_text',{}).get(index,())) != after.non_text
                                or after.annotations < before.annotations):
                            raise PdfError(PdfKind.CORRUPTED_PDF)
                        textpage = page.get_textpage()
                        extracted = ''.join(textpage.get_text_range().split())
                        textpage.close()
                        annotations = []
                        for i in range(after.annotations):
                            annotation = raw.FPDFPage_GetAnnot(page, i)
                            try:
                                count = raw.FPDFAnnot_GetStringValue(annotation, b'Contents', None, 0)
                                if count:
                                    buffer = (ctypes.c_ushort * ((count + 1) // 2))()
                                    raw.FPDFAnnot_GetStringValue(annotation, b'Contents', buffer, count)
                                    annotations.append(bytes(buffer).decode('utf-16-le').rstrip('\0'))
                            finally:
                                raw.FPDFPage_CloseAnnot(annotation)
                        for segment in (s for s in self.segments if s.page == index):
                            visible = ''.join((segment.visible_text or '').split())
                            # The bundled font shares the bullet/middle-dot glyph;
                            # PDFium's ToUnicode chooses one alias for that glyph.
                            # Compare that one visual equivalence, never drop text,
                            # numbers, identifiers or arbitrary punctuation.
                            actual = extracted
                            if segment.origin == 'ocr':
                                visible,actual=visible.replace('•','·'),actual.replace('•','·')
                            if visible and visible not in actual:
                                raise PdfError(PdfKind.CORRUPTED_PDF, context('validate', 'visible_text_contiguous', index + 1, segment.object_indices[0] if segment.object_indices else None, raw.FPDF_PAGEOBJ_TEXT))
                            if segment.overflow_text and not segment.continuation_lines and segment.overflow_text not in annotations:
                                raise PdfError(PdfKind.CORRUPTED_PDF)
                    finally:
                        page.close()
                if getattr(self, 'continuation_count', 0):
                    from collections import Counter
                    actual = Counter()
                    for i in range(len(self.pages), len(document)):
                        page = document[i]
                        tp = page.get_textpage()
                        for obj in page.get_objects(max_depth=1):
                            if obj.type == raw.FPDF_PAGEOBJ_TEXT:
                                obj.textpage = tp
                                actual[''.join(obj.extract().split())] += 1
                        tp.close()
                        page.close()
                    expected = Counter(''.join(line.split()) for s in self.segments for line in s.continuation_lines if line.strip())
                    if expected - actual:
                        raise PdfError(PdfKind.CORRUPTED_PDF, context('validate', 'continuation_lines'))
            finally:
                document.close()
