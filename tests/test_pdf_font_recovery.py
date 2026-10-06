"""Unsupported glyphs must preserve source blocks without aborting PDF output."""
from hashlib import sha256
from pathlib import Path
import pytest

from PIL import Image, ImageChops

from app.documents.errors import DocumentError
from app.documents.pdf_document import PdfDocument
from app.documents.pdf_fonts import FontResolver
from app.documents.pdf_types import PdfSegment
from tools.pdf_fixtures import make_pdf, render


@pytest.mark.parametrize('page,object_index', [(0, None), (1, 71), (1, 188), (2, 46), (3, 166)])
def test_native_unsupported_glyph_preserves_block_and_other_translations(tmp_path, page, object_index):
    source = Path(__file__).parent / 'fixtures/pdf/automotive.pdf'
    before = sha256(source.read_bytes()).hexdigest()
    doc = PdfDocument(source)
    for segment in doc.segments:
        segment.translated = 'Технический перевод.'
    bad = next(s for s in doc.segments if s.page == page and s.available_bbox and not s.rotation
               and (object_index is None or object_index in s.object_indices))
    bad.translated = 'Недоступный символ \U0010ffff'
    output = tmp_path / 'recovered.pdf'
    doc.write(output)
    doc.validate(output)
    assert bad.policy == 'CONSERVATIVE_PRESERVE'
    assert bad.visible_text == bad.text
    assert not bad.written_boxes
    for segment in doc.segments:
        if segment.page == bad.page and segment is not bad:
            for box in segment.written_boxes:
                overlap_width = min(box[2], bad.bbox[2])-max(box[0], bad.bbox[0])
                overlap_height = min(box[3], bad.bbox[3])-max(box[1], bad.bbox[1])
                assert overlap_width <= .1 or overlap_height <= .1
    assert any(s.status == 'written' for s in doc.segments if s is not bad)
    assert any('шрифт' in warning for warning in doc.warnings)
    assert sha256(source.read_bytes()).hexdigest() == before


def test_ocr_unsupported_glyph_keeps_raster_without_mask_or_text_expectation(tmp_path):
    source = make_pdf(tmp_path / 'raster.pdf', image=True)
    doc = PdfDocument(source)
    for segment in doc.segments:
        segment.translated = segment.text
    bad = PdfSegment(0, 'ocr-font-test', 'OCR source', (450, 500, 535, 520),
                     len(doc.segments), (), 10, origin='ocr',
                     available_bbox=(450, 500, 535, 520), translated='\U0010ffff')
    doc.segments.append(bad)
    output = tmp_path / 'kept.pdf'
    doc.write(output)
    doc.validate(output)
    assert bad.policy == 'CONSERVATIVE_PRESERVE'
    assert bad.visible_text is None
    assert not doc.added_non_text
    with Image.open(render(source, tmp_path/'before')[0]) as before:
        with Image.open(render(output, tmp_path/'after')[0]) as after:
            assert ImageChops.difference(before.convert('RGB'), after.convert('RGB')).getbbox() is None


def test_layout_and_continuation_reuse_prepared_face(tmp_path, monkeypatch):
    source = make_pdf(tmp_path / 'small.pdf', 'Short text.', tiny=True, lines=1)
    doc = PdfDocument(source)
    for segment in doc.segments:
        segment.translated = 'Особый длинный технический текст. ' * 200
    resolve = FontResolver.resolve
    def embedded_only(self, text, original=None):
        # Model an embedded face that can cover a translation unavailable in
        # local fallback fonts. Re-resolving without the original must fail.
        if 'Особый' in text and original is None:
            raise DocumentError('test: embedded face required')
        return resolve(self, text, original)
    monkeypatch.setattr(FontResolver, 'resolve', embedded_only)
    output = tmp_path / 'continued.pdf'
    doc.write(output)
    doc.validate(output)
    assert doc.continuation_count > 0
    assert all(s.continuation_lines for s in doc.segments if s.overflow_text)
    assert not any(s.policy == 'CONSERVATIVE_PRESERVE' for s in doc.segments)
