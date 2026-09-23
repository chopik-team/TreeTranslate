"""Actual supplied PDF regressions plus model-independent policy tests."""
from pathlib import Path
from types import SimpleNamespace
from collections import Counter
from hashlib import sha256
import json
import re
import pytest
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from PIL import Image, ImageChops
from app.documents.pdf_document import PdfDocument
from app.documents.pdf_fidelity import preserve_title, faithful_result, FidelityMismatch, segment_source
from app.documents.pdf_diagnostics import diagnostic
from app.documents.pdf_types import PdfError, PdfKind
from tools.pdf_fixtures import render

FIXTURES = Path(__file__).parent / 'fixtures/pdf'

@pytest.mark.parametrize('title', ['iRacing','BeamNG.drive','Wreckfest','Need for Speed Heat','Need for Speed Payback','FORZA HORIZON 5','CarX Drift Racing Online','GDS','ITM','IVT','PC','PS4','Xbox','GT sport'])
def test_general_identifier_title_guard(title):
    assert preserve_title(title)

@pytest.mark.parametrize('text',['Save the configuration file.', 'User guide', 'Restart the application before proceeding.'])
def test_prose_is_not_title(text):
    assert not preserve_title(text)


def test_numeric_and_identifier_invariants():
    assert faithful_result('IVT 6.6 L, 45–60%', 'ИВТ 6,6 л, 45–60%') == 'IVT 6.6 л, 45–60%'
    with pytest.raises(FidelityMismatch):
        faithful_result('ITM 6.6', 'ITM 6.61')
    with pytest.raises(FidelityMismatch):
        faithful_result('ITM', 'Только модуль')
    with pytest.raises(FidelityMismatch):
        faithful_result('ITM', 'ITM 1')


def test_substantial_other_language_uses_detector():
    calls=[]
    def resolve(t,s,d):calls.append(s);return 'en',d
    assert segment_source('Restart the application before proceeding with configuration.', 'zh','ru',resolve)=='en'
    assert calls==['auto']


def test_diagnostics_never_include_user_text(caplog):
    with pytest.raises(PdfError) as caught:
        with diagnostic('validate','visible_text',2,31,raw.FPDF_PAGEOBJ_TEXT):
            raise PdfError(PdfKind.CORRUPTED_PDF)
    assert caught.value.diagnostic['page']==2
    assert caught.value.diagnostic['object_index']==31
    assert 'странице 2' in str(caught.value)
    assert 'visible_text' in caplog.text


def test_automotive_mixed_glyphs_grouped_and_roundtrip(tmp_path):
    path=FIXTURES/'automotive.pdf';before=sha256(path.read_bytes()).hexdigest();doc=PdfDocument(path)
    assert len(doc.pages)==4
    assert not any('Form' in w for w in doc.warnings)
    steps=[s for s in doc.segments if re.match(r'^\d+\.',s.text)]
    assert len(steps)==34
    assert any('GDS' in s.text and len(s.text)>20 for s in doc.segments)
    assert any('6.6' in s.text and 'IVT' in s.text for s in doc.segments)
    for s in doc.segments:
        s.translated='Перевод технического блока. Сохранён порядок процедуры.'
    out=tmp_path/'manual.pdf';doc.write(out);doc.validate(out)
    assert sha256(path.read_bytes()).hexdigest()==before
    with pdfium.PdfDocument(out) as pdf:
        assert len(pdf)>=4
        for i in range(len(pdf)):
            page=pdf[i];assert raw.FPDFPage_GetAnnotCount(page)==0;page.close()


def test_silverstone_grid_and_names_render_unchanged(tmp_path):
    path=FIXTURES/'silverstone.pdf';doc=PdfDocument(path)
    assert sum(s.region_kind=='table_cell' for s in doc.segments)>25
    for s in doc.segments:
        s.translated=s.text if preserve_title(s.text) else 'Перевод'
    out=tmp_path/'table.pdf';doc.write(out);doc.validate(out)
    before=Image.open(render(path,tmp_path/'before')[0])
    after=Image.open(render(out,tmp_path/'after')[0])
    # All game rows: grid, checkmarks, numbers, English names stay visible.
    crop=(50,130,580,806)
    difference=ImageChops.difference(before.crop(crop),after.crop(crop))
    import numpy as np
    # At most 0.05% antialias pixels may differ after explicit CMYK->RGB.
    assert (np.asarray(difference).max(axis=2)>0).mean() < .0005


def test_font_fallback_uses_readable_continuations(tmp_path):
    from tools.pdf_fixtures import make_pdf
    path=make_pdf(tmp_path/'small.pdf',text='Short text.',tiny=True)
    doc=PdfDocument(path)
    for s in doc.segments:s.translated='Полный длинный технический текст. '*300
    out=tmp_path/'continued.pdf';doc.write(out);doc.validate(out)
    assert doc.continuation_count>0
    assert all(s.continuation_lines for s in doc.segments)
