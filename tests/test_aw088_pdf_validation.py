"""Real native PDF bullet alias must not bypass text completeness checks."""
import pytest
from app.documents.pdf_document import PdfDocument
from app.documents.pdf_types import PdfError
from tools.pdf_fixtures import make_pdf


def test_native_bullet_font_alias_and_wrong_text_still_rejected(tmp_path):
    source=make_pdf(tmp_path/'source.pdf','Inspect the connector and wiring harness.',lines=1)
    document=PdfDocument(source)
    segment=next(s for s in document.segments if 'connector' in s.text)
    for s in document.segments:s.translated=s.text
    segment.translated='• Проверьте разъём и жгут проводов.'
    output=tmp_path/'translated.pdf';document.write(output)
    document.validate(output)
    assert segment.origin=='native' and '•' in segment.visible_text
    segment.visible_text=segment.visible_text.replace('разъём','клапан')
    with pytest.raises(PdfError):document.validate(output)
