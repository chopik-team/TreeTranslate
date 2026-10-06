"""Render every successfully validated delivered PDF; no validation overrides."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zipfile import ZipFile
from PIL import Image
from tools import aw086_render as renderer
from tools.aw088_prepare import ROOT,QA,save

renderer.folder=QA/'visual';renderer.folder.mkdir(exist_ok=True)
body=json.loads((QA/'body_e2e.json').read_text('utf8'))
with ZipFile(body['outputs'][0]) as archive:
    for index,name in enumerate(n for n in archive.namelist() if n.endswith('.pdf')):renderer.render(archive.read(name),f'body-{index+1}')
coolant=json.loads((QA/'coolant_e2e.json').read_text('utf8'));renderer.render(Path(coolant['outputs'][0]).read_bytes(),'coolant')
samples=json.loads((QA/'sample_pdf_e2e.json').read_text('utf8'))
for path in samples['outputs']:renderer.render(Path(path).read_bytes(),Path(path).stem)
groups=[['body-'+str(n) for n in range(1,8)]+['coolant'],[Path(p).stem for p in samples['outputs']]]
for group_index,stems in enumerate(groups):
    for offset in range(0,len(stems),4):
        selected=stems[offset:offset+4];pictures=[]
        for stem in selected:
            with Image.open(renderer.folder/f'{stem}-sheet.png') as original:
                picture=original.copy();picture.thumbnail((610,900));pictures.append(picture)
        sheet=Image.new('RGB',(1220,1800),'#eeeeee')
        for n,picture in enumerate(pictures):sheet.paste(picture,((n%2)*610,(n//2)*900))
        sheet.save(renderer.folder/f'overview-{group_index}-{offset//4}.png')
save('visual_inventory.json',dict(rendered_outputs=len(samples['outputs'])+8,folder=str(renderer.folder),
    qa_status='PENDING_VISUAL_REVIEW',geometry_validators_unmodified=True))
