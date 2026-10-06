import sys,json
from pathlib import Path
from zipfile import ZipFile
from PIL import Image,ImageDraw,ImageFont
import pypdfium2 as pdfium
ROOT=Path('C:/TreeTranslate')
data=json.loads((ROOT/'qa/aw085/accepted_segments.json').read_text('utf-8'))
folder=ROOT/'build/aw085-quality/rendered';folder.mkdir(exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
with ZipFile(data['outputs'][0]) as archive:
    for i,name in enumerate(n for n in archive.namelist() if n.endswith('.pdf')):
        pdf=pdfium.PdfDocument(archive.read(name));thumbs=[]
        for p in range(len(pdf)):
            page=pdf[p];bitmap=page.render(scale=1.6);image=bitmap.to_pil().copy()
            image.save(folder/f'doc{i+1}-page{p+1}.png')
            image.thumbnail((395,560));tile=Image.new('RGB',(405,585),'#dddddd')
            tile.paste(image,((405-image.width)//2,23));ImageDraw.Draw(tile).text((8,3),f'Doc {i+1} / page {p+1}',font=font,fill='black')
            thumbs.append(tile);bitmap.close();page.close()
        sheet=Image.new('RGB',(405*min(3,len(thumbs)),585*((len(thumbs)+2)//3)),'white')
        for j,tile in enumerate(thumbs):sheet.paste(tile,((j%3)*405,(j//3)*585))
        sheet.save(folder/f'doc{i+1}-sheet.png');pdf.close()
        print(i+1,name,len(thumbs))
