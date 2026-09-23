"""Synthetic fixtures and renderer for developer QA only; never imported by runtime."""
from pathlib import Path
from io import BytesIO
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from PIL import Image

from app.documents.pdf_document import PDF_LOCK, wide
from app.documents.pdf_fonts import FontResolver


def make_pdf(path, text='Save the configuration file before restarting the application.', *,
             pages=1, image=False, empty=False, columns=False, rotation=0, rotated_text=False,
             link=False, fragments=False, lines=2, tiny=False, background=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with PDF_LOCK:
        document = pdfium.PdfDocument.new()
        fonts = FontResolver()
        face = fonts.resolve(text + 'User guideLeft columnRight column')
        font = fonts.embed(document, face, text + 'User guideLeft columnRight column')
        try:
            for index in range(pages):
                page = document.new_page(600, 800)
                if background and not empty:
                    rect = pdfium.PdfObject(raw.FPDFPageObj_CreateNewRect(25, 430, 550, 325), pdf=document)
                    raw.FPDFPageObj_SetFillColor(rect, 232, 242, 250, 255)
                    raw.FPDFPath_SetDrawMode(rect, raw.FPDF_FILLMODE_WINDING, False)
                    page.insert_obj(rect)
                if image:
                    picture = Image.new('RGB', (64, 64), '#297250')
                    # A generated plain image has no text; no OCR is used in any QA.
                    data = BytesIO()
                    picture.save(data, format='JPEG')
                    data.seek(0)
                    obj = pdfium.PdfImage.new(document)
                    obj.load_jpeg(data)
                    obj.set_matrix(pdfium.PdfMatrix(a=110, d=110, e=440, f=480))
                    page.insert_obj(obj)
                def add(value, x, y, size=12, angle=0):
                    obj = pdfium.PdfObject(raw.FPDFPageObj_CreateTextObj(document, font, size), pdf=document)
                    assert raw.FPDFText_SetText(obj, wide(value))
                    matrix = pdfium.PdfMatrix(e=x, f=y) if not angle else pdfium.PdfMatrix(0, 1, -1, 0, x, y)
                    obj.set_matrix(matrix)
                    page.insert_obj(obj)
                if not empty and text:
                    add('User guide', 45, 720, 20)
                    if columns:
                        add('Left column', 45, 675)
                        add('Right column', 335, 675)
                        for line in range(lines):
                            add(text, 45, 650 - line * 18, 9)
                            add(text, 335, 650 - line * 18, 9)
                    elif rotated_text:
                        add(text, 80, 100, 12, 90)
                    elif fragments:
                        x = 45
                        for character in text:
                            add(character, x, 670)
                            x += face.width(character, 12)
                    else:
                        for line in range(lines):
                            add(text, 45, 675 - line * 18, 6 if tiny else 12)
                if link:
                    annotation = raw.FPDFPage_CreateAnnot(page, raw.FPDF_ANNOT_LINK)
                    rect = raw.FS_RECTF(45, 735, 250, 700)
                    assert raw.FPDFAnnot_SetRect(annotation, rect)
                    assert raw.FPDFAnnot_SetURI(annotation, b'https://example.org/manual?id=42')
                    raw.FPDFPage_CloseAnnot(annotation)
                page.gen_content()
                page.set_rotation(rotation)
                page.close()
            document.save(path)
        finally:
            fonts.close()
            document.close()
    return path


def render(path, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    with PDF_LOCK, pdfium.PdfDocument(path) as document:
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=1.5)
            target = directory / f'page-{index + 1}.png'
            bitmap.to_pil().save(target)
            bitmap.close()
            page.close()
            paths.append(target)
    return paths
