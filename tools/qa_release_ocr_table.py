"""Bounded OCR table/worker reuse measurements with existing local models."""
import json
from pathlib import Path
import sys
from time import perf_counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from PIL import Image,ImageDraw,ImageFont
    from app.ocr.router.ocr_router import OcrRouter
    from app.ocr.types import OcrRequest
    image=Image.new('RGB',(1000,440),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30)
    for y in (20,120,220,320,420):draw.line((20,y,980,y),fill='black',width=3)
    for x in (20,500,980):draw.line((x,20,x,420),fill='black',width=3)
    for i,values in enumerate([('Parameter','Value'),('Voltage','220 V'),('Length','42 mm'),('Pressure','12 bar')]):
        for x,text in zip((40,520),values):draw.text((x,50+i*100),text,font=font,fill='black')
    image.save(ROOT/'docs/qa/aw08/table-fixture.png')
    rows=[]
    for profile in ('fast','maximum'):
        router=OcrRouter()
        try:
            for iteration in range(2):
                start=perf_counter()
                result=router.recognize(OcrRequest(image,source_language='en',device_preference='gpu',performance_profile=profile,complexity={'lines':8,'regions':8,'columns':2}))
                rows.append({'profile':profile,'iteration':iteration,'state':'cold' if iteration==0 else 'warm same worker',
                             'wall_seconds':perf_counter()-start,'timings':result.timings,'backend':result.backend,
                             'text':' '.join(x.text for x in result.segments),'segments':len(result.segments)})
                (ROOT/'docs/qa/aw08/ocr-table.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
                print(profile,iteration,rows[-1]['wall_seconds'],result.backend,flush=True)
        finally:router.shutdown()
    image.close()


if __name__=='__main__':main()
