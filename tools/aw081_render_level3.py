"""Render every BODY/coolant output page, keeping immutable source comparisons."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from zipfile import ZipFile
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.documents.run_metrics import file_hash
QA=ROOT/'qa/aw081/iterations/14_phase_a_closure/level3'
OUT=QA/'render'
OUT.mkdir(exist_ok=False)
POPPLER=Path('C:/Users/PC/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
body=json.loads((QA/'body_e2e.json').read_text('utf8'))
coolant=json.loads((QA/'coolant_e2e.json').read_text('utf8'))
tasks=[]
for database in (QA/'logs').glob('*/index.sqlite3'):
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as con:
        if con.execute('SELECT COUNT(*) FROM documents').fetchone()[0]!=7:continue
        for index,(payload,) in enumerate(con.execute('SELECT payload FROM documents ORDER BY id')):
            d=json.loads(payload)
            paths=[]
            for kind,archive,member in [('source',d['source_archive_path'],d['archive_member_path']),
                                        ('translated',body['outputs'][0],d['output_archive_member'])]:
                path=OUT/f'body-{index}-{kind}.pdf'
                with ZipFile(archive) as zipfile,zipfile.open(member) as source,path.open('wb') as target:
                    shutil.copyfileobj(source,target)
                assert file_hash(path)==d['source_sha256' if kind=='source' else 'output_sha256']
                paths.append(path)
            tasks.append(dict(id=f'body-{index}',source=str(paths[0]),output=str(paths[1]),source_pages=d['source_pages'],output_pages=d['output_pages']))
tasks.append(dict(id='coolant',source=str(ROOT/'tests/fixtures/pdf/automotive.pdf'),output=coolant['outputs'][0],
                  source_pages=4,output_pages=coolant['documents'][0]['output_pages']))
rendered=[]
for task in tasks:
    rows={}
    for kind,key in [('source','source'),('translated','output')]:
        prefix=OUT/(task['id']+'-'+kind)
        command=[str(POPPLER),'-scale-to','1400','-png',task[key],str(prefix)]
        result=subprocess.run(command,capture_output=True)
        (OUT/(task['id']+'-'+kind+'.stderr.txt')).write_bytes(result.stderr)
        assert result.returncode==0
        pages=sorted(OUT.glob(prefix.name+'-*.png'))
        assert len(pages)==task['source_pages' if kind=='source' else 'output_pages']
        rows[kind]=pages
    width=600;cell_height=850;count=max(len(rows['source']),len(rows['translated']))
    for start in range(0,count,3):
        canvas=Image.new('RGB',(width*2,cell_height*min(3,count-start)), 'white');draw=ImageDraw.Draw(canvas)
        for offset in range(min(3,count-start)):
            page_index=start+offset
            for col,kind in enumerate(('source','translated')):
                draw.text((col*width+12,offset*cell_height+8),f"{task['id']} / {kind} / page {page_index+1}",fill='black')
                if page_index<len(rows[kind]):
                    with Image.open(rows[kind][page_index]) as image:
                        image.thumbnail((width-20,cell_height-35))
                        canvas.paste(image,(col*width+10,offset*cell_height+30))
        sheet=OUT/(task['id']+f'-comparison-{start//3}.png');canvas.save(sheet)
        rendered.append(str(sheet))
manifest=dict(tasks=tasks,contact_sheets=rendered,all_source_pages=sum(t['source_pages'] for t in tasks),
              all_output_pages=sum(t['output_pages'] for t in tasks),visual_review='PENDING',
              png_hashes={p.name:file_hash(p) for p in OUT.glob('*.png')})
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf8')
print('RENDERED',manifest['all_output_pages'],'OUTPUT PAGES',len(rendered),'SHEETS',flush=True)
