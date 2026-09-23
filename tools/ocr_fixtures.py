"""Developer regression scans: rasterize a known native PDF without altering it."""
from io import BytesIO
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image,ImageDraw,ImageFont


def rasterize(source, output, dpi=200, angle=0):
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    source_doc = pdfium.PdfDocument(source)
    target = pdfium.PdfDocument.new()
    try:
        for index in range(len(source_doc)):
            page = source_doc[index]
            bitmap = page.render(scale=dpi/72)
            image = bitmap.to_pil().convert('RGB')
            w,h = page.get_size()
            if angle:
                image = image.rotate(angle,expand=True)
                if angle in (90,270):
                    w,h = h,w
            dest = target.new_page(w,h)
            stream = BytesIO()
            image.save(stream,format='JPEG',quality=95)
            stream.seek(0)
            obj = pdfium.PdfImage.new(target)
            obj.load_jpeg(stream)
            obj.set_matrix(pdfium.PdfMatrix(a=w,d=h))
            dest.insert_obj(obj)
            dest.gen_content()
            dest.close()
            image.close()
            bitmap.close()
            page.close()
        target.save(output)
    finally:
        target.close()
        source_doc.close()
    return output


def make_mixed(output):
    from tools.pdf_fixtures import make_pdf
    output=Path(output)
    native=make_pdf(output.with_name(output.stem+'-native.pdf'),lines=1,background=False)
    with pdfium.PdfDocument(native) as document:
        page=document[0]
        image=Image.new('RGB',(1400,250),'white')
        ImageDraw.Draw(image).text((35,75),'Read the instructions before installation.',
                                  font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',50),fill='black')
        stream=BytesIO();image.save(stream,format='JPEG');stream.seek(0)
        obj=pdfium.PdfImage.new(document);obj.load_jpeg(stream)
        obj.set_matrix(pdfium.PdfMatrix(a=500,d=90,e=45,f=450));page.insert_obj(obj)
        page.gen_content();page.close();document.save(output)
    return output
