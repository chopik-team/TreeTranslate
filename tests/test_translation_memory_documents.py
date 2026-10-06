"""One memory instance through real DOCX, PDF and Paddle OCR document jobs."""
from hashlib import sha256
from unittest.mock import Mock

from docx import Document
import pypdfium2 as pdfium
import pytest

from app.documents.control import JobControl
from app.documents.job import DocumentConfig, DocumentJob
from app.documents.scanner import scan_sources
from app.engine.router.translation_router import TranslationRouter
from app.engine.types import DevicePreference, PerformanceProfile
from app.translation_memory.engine import TranslationMemoryEngine
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from tools.pdf_fixtures import make_pdf
from tools.ocr_fixtures import rasterize


@pytest.mark.integration
def test_one_memory_three_document_types(tmp_path):
    tm = TranslationMemoryEngine(tmp_path/'tm.db')
    source = 'Save the file before restarting.'
    target = 'Сохраните файл перед запуском.'
    for en, ru in [(source,target),('User guide','Руководство'),
                   ('Read the instructions.','Прочитайте инструкции.'),
                   ('Disconnect the connector.','Отсоедините разъём.'),
                   ('Check the engine.','Проверьте двигатель.')]:
        tm.remember_translation(en,ru,'en','ru')
    router = TranslationRouter({})
    router.translate = Mock(side_effect=AssertionError('TM fixture unexpectedly called model router'))
    engine = TranslationKnowledgeEngine(router,tm)
    docx_path = tmp_path/'manual.docx'
    doc = Document();doc.add_paragraph(source);doc.save(docx_path)
    pdf = make_pdf(tmp_path/'native.pdf',source,lines=1,background=False)
    scan = rasterize(pdf,tmp_path/'scan.pdf')
    paths = [docx_path,pdf,scan]
    original = {p:sha256(p.read_bytes()).hexdigest() for p in paths}
    try:
        control = JobControl()
        outputs = DocumentJob(scan_sources(paths,control).files,
            DocumentConfig(source='en',target='ru',device=DevicePreference.CPU,
                           profile=PerformanceProfile.FAST,output=tmp_path/'out'),
            control,engine.translate,engine.languages.resolve).run()
        assert len(outputs) == 3
        for output in outputs:
            if output.suffix == '.docx':
                text = '\n'.join(p.text for p in Document(output).paragraphs)
            else:
                with pdfium.PdfDocument(output) as pdf_doc:
                    page = pdf_doc[0];tp = page.get_textpage()
                    text = tp.get_text_range();tp.close();page.close()
            assert target in text
        assert router.translate.call_count == 0
        assert tm.stats()['total_units'] == 5
        assert tm.stats()['counters']['exact_hits'] >= 3
        assert all(sha256(p.read_bytes()).hexdigest() == original[p] for p in paths)
    finally:
        engine.shutdown()
