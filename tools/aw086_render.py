"""Render all delivered pages with the production PDFium dependency."""
import json
from pathlib import Path
from zipfile import ZipFile
import pypdfium2 as pdfium
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('C:/TreeTranslate');QA=ROOT/'qa/aw086'
folder=QA/'visual';folder.mkdir(exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)


def render(data,stem):
    document=pdfium.PdfDocument(data);tiles=[]
    try:
        for index in range(len(document)):
            page=document[index];bitmap=page.render(scale=1.5);picture=bitmap.to_pil().copy()
            picture.save(folder/f'{stem}-page{index+1}.png')
            picture.thumbnail((395,560));tile=Image.new('RGB',(405,585),'#dddddd')
            tile.paste(picture,((405-picture.width)//2,23));ImageDraw.Draw(tile).text((8,3),f'{stem} / page {index+1}',font=font,fill='black')
            tiles.append(tile);bitmap.close();page.close()
        sheet=Image.new('RGB',(405*min(3,len(tiles)),585*((len(tiles)+2)//3)),'white')
        for index,tile in enumerate(tiles):sheet.paste(tile,((index%3)*405,(index//3)*585))
        sheet.save(folder/f'{stem}-sheet.png')
        print(stem,len(document),flush=True)
    finally:document.close()


if __name__=='__main__':
    body=json.loads((QA/'body_e2e.json').read_text('utf-8'))
    with ZipFile(body['outputs'][0]) as archive:
        for index,name in enumerate(n for n in archive.namelist() if n.endswith('.pdf')):render(archive.read(name),f'body-{index+1}')
    for name in ('coolant','general','mixed'):
        data=json.loads((QA/(name+'_e2e.json')).read_text('utf-8'))
        render(Path(data['outputs'][0]).read_bytes(),name)
