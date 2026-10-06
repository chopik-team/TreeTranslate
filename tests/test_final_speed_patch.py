"""Detached OCR lock safety and geometry-first deduplication equivalence."""
from dataclasses import replace
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from app.documents.pdf_document import PDF_LOCK, PdfDocument, detached_pdf_work
from app.documents.job import DocumentConfig
from app.ocr.pdf_extractor import HybridPdfExtractor
from app.ocr.types import OcrPageResult, OcrSegment
from tools.pdf_fixtures import make_pdf
from tools.ocr_fixtures import rasterize


def test_disjoint_geometry_never_runs_text_similarity(monkeypatch):
    import app.ocr.postprocess.deduplication as module
    monkeypatch.setattr(module, 'normalize', lambda text: pytest.fail('Disjoint boxes need no text work'))
    candidate = SimpleNamespace(text='发动机', bbox=(0, 0, 20, 10))
    other = SimpleNamespace(text='发动机', bbox=(100, 0, 120, 10))
    assert module.duplicate(candidate, [other]) is False


@pytest.mark.parametrize('text', ['发动机总成', 'ＥＣＭ １２３', 'Engine guide', 'двигатель', ''])
def test_duplicate_matches_previous_rules_at_geometry_boundaries(text):
    import app.ocr.postprocess.deduplication as module
    thresholds = module.configuration()['dedup']
    candidate = SimpleNamespace(text=text, bbox=(0, 0, 20, 10))
    for shift in (0, 1, 3, 10, 20, 100):
        for other_text in (text, text+' extra', 'completely different'):
            other = SimpleNamespace(text=other_text, bbox=(shift, 0, shift+20, 10))
            coverage = module.intersection(candidate.bbox, other.bbox)/max(1, min(module.area(candidate.bbox), module.area(other.bbox)))
            similarity = module.SequenceMatcher(None, module.normalize(text), module.normalize(other_text)).ratio()
            expected = coverage >= thresholds['overlap'] and similarity >= thresholds['similarity']
            assert module.duplicate(candidate, [other]) is expected


def test_detached_scope_restores_lock_on_exception_and_preserves_recursion():
    with PDF_LOCK:
        with pytest.raises(ValueError):
            with detached_pdf_work():
                assert not PDF_LOCK._is_owned()
                raise ValueError()
        assert PDF_LOCK._is_owned()
        with PDF_LOCK:
            with detached_pdf_work():
                assert PDF_LOCK._is_owned()  # The caller's extra level remains held.
            assert PDF_LOCK._is_owned()
    with detached_pdf_work():
        assert not PDF_LOCK._is_owned()


def test_real_pdf_writer_can_finish_while_ocr_uses_detached_image(tmp_path):
    from tools.aw081_hardware_scaling_20 import fingerprint_pdf
    from tools.aw081_ocr_adaptive import source_contract
    native = make_pdf(tmp_path/'native.pdf')
    scanned = rasterize(native, tmp_path/'scan.pdf')
    entered, release, written = Event(), Event(), Event()
    errors, documents = [], []
    class Router:
        def __init__(self, block=False): self.block = block
        def recognize(self, request):
            assert not PDF_LOCK._is_owned()
            if self.block:
                entered.set()
                assert release.wait(20)
            w, h = request.image.size
            polygon = tuple((x*w/600, y*h/800) for x,y in ((44,62),(250,62),(250,88),(44,88)))
            return OcrPageResult(0, [OcrSegment('title', 'Engine configuration guide', polygon, (0,0,1,1), .99)], 'fake', 'cpu', .01)
    baseline = PdfDocument(scanned, extractor=HybridPdfExtractor(Router(), DocumentConfig(source='en')))
    writer = PdfDocument(native)
    for segment in writer.segments: segment.translated = 'Руководство'
    expected_path = tmp_path/'expected.pdf';writer.write(expected_path)
    writer = PdfDocument(native)
    for segment in writer.segments: segment.translated = 'Руководство'
    def reader():
        try: documents.append(PdfDocument(scanned, extractor=HybridPdfExtractor(Router(True), DocumentConfig(source='en'))))
        except BaseException as error: errors.append(error)
    actual_path = tmp_path/'actual.pdf'
    def write():
        try: writer.write(actual_path);writer.validate(actual_path);written.set()
        except BaseException as error: errors.append(error)
    read_thread = Thread(target=reader);read_thread.start()
    write_thread = None
    try:
        assert entered.wait(10)
        write_thread = Thread(target=write);write_thread.start()
        assert written.wait(10), 'Writer was blocked by OCR on a detached image'
    finally:
        release.set();read_thread.join(20)
        if write_thread: write_thread.join(20)
    assert not read_thread.is_alive() and write_thread and not write_thread.is_alive()
    assert not errors and source_contract(documents[0]) == source_contract(baseline)
    assert fingerprint_pdf(expected_path.read_bytes(), True) == fingerprint_pdf(actual_path.read_bytes(), True)
