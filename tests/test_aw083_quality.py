"""Safety policies and shared trusted-label lookup, without neural inference."""
from dataclasses import replace
from unittest.mock import Mock
import pytest
from app.documents.pdf_types import PdfSegment
from app.documents.pdf_ocr_policy import classify, protected_kind
from app.documents.pdf_fidelity import faithful_result, FidelityMismatch
from app.engine.types import TranslationRequest
from app.glossary.engine import GlossaryEngine
from app.translation_memory.knowledge import TranslationKnowledgeEngine


@pytest.mark.parametrize('text', ["A", "A'", 'A″', "R-R'", 'T-U', 'BIW', 'VIN', 'ITM', 'GDS', 'ECU', 'Ø6.6', 'Ø13', '7x12', '8.5x8.5', '3.5 ± 0.5 mm', '548 (21.59)', 'A-B: 548 (21.59)'])
def test_geometry_never_needs_translation(text):
    assert protected_kind(text) in {'identifier','measurement'}


@pytest.mark.parametrize('text', ['日','之','囍','卫','.', 'C4444:.5)', 'K1.-.:.5)'])
def test_noise_is_preserved(text):
    assert classify(PdfSegment(0,'x',text,(0,0,30,10),0,(),8,origin='ocr',confidence=.99))=='noise'


@pytest.mark.parametrize('source,target', [('孔 Ø6.6','Отверстие 6.6'), ("孔 A'",'Отверстие А'), ('内部A','Внутренний А'), ('孔 7x12','Отверстие 7 на 12'), ('孔','Отверстие 孔'), ('孔','⁇'), ('孔','Передняя передняя передняя передняя')])
def test_failed_invariants_reject_output(source,target):
    with pytest.raises(FidelityMismatch):faithful_result(source,target)


def test_shared_label_lookup_keeps_dimensions_and_user_precedence(tmp_path):
    g=GlossaryEngine(tmp_path/'glossary.db')
    g.remember_term('机罩铰链孔','Отверстие петли капота','zh','ru',domain='automotive')
    memory=Mock();memory.lookup.return_value=None
    engine=TranslationKnowledgeEngine(Mock(),memory,g)
    request=TranslationRequest('机罩铰链孔 （Ø11）','zh','ru',domain='automotive')
    result=engine.lookup_direct(request)
    assert result.translated_text=='Отверстие петли капота （Ø11）'
    engine.router.translate.assert_not_called()
    g.remember_term(request.text,'Пользовательский вариант （Ø11）','zh','ru',domain='automotive')
    assert engine.lookup_direct(request).translated_text=='Пользовательский вариант （Ø11）'


def test_diagram_overflow_preserves_image_before_mask(tmp_path):
    from app.documents.pdf_document import PdfDocument
    from tools.pdf_fixtures import make_pdf
    doc=PdfDocument(make_pdf(tmp_path/'source.pdf',image=True))
    segment=PdfSegment(0,'diagram','接线孔',(450,500,465,510),99,(),10,origin='ocr',
        translated='Отверстие для жгута проводов',ocr_kind='diagram_label')
    doc.segments.append(segment)
    output=tmp_path/'result.pdf';doc.write(output);doc.validate(output)
    assert segment.preserve_reason=='diagram_label_does_not_fit'
    assert not segment.overflow_text and not segment.written_boxes
    assert doc.continuation_count==0 and not doc.added_non_text
