"""Render only the four known CATA's published pages, not a whole semantic cycle."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/aw081/iterations/15_diagnostic_live_readiness/operational'
result=json.loads((QA/'execution.json').read_text('utf8'))
render=QA/'cata_render';render.mkdir(exist_ok=False)
with sqlite3.connect(Path(result['logs'])/'index.sqlite3') as database:
    docs=[json.loads(payload) for payload, in database.execute('SELECT payload FROM documents')]
captures={r['index']:r for r in (json.loads(line) for line in (QA/'successful_documents.jsonl').read_text('utf8').splitlines())}
original=json.loads((ROOT/'qa/aw081/final_holdout_manifest.json').read_text('utf8'))['documents']
poppler=Path('C:/Users/PC/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
import pypdfium2 as pdfium
rows=[]
with ZipFile(result['output_archive']) as archive:
    for index in (5,9):
        row=next(d for d in docs if d['source_sha256']==original[index]['sha256'])
        data=archive.read(row['output_archive_member'])
        assert sha256(data).hexdigest()==row['output_sha256']
        path=render/f'document-{index}.pdf';path.write_bytes(data)
        subprocess.run([str(poppler),'-f','1','-l','2','-r','110','-png',str(path),str(render/f'document-{index}')],check=True)
        d=pdfium.PdfDocument(path)
        texts={}
        try:
            for page_index in (0,1):
                p=d[page_index];t=p.get_textpage()
                try:texts[page_index]=' '.join(t.get_text_range().split())
                finally:t.close();p.close()
        finally:d.close()
        for case in result['known_cata']:
            if case['index']!=index:continue
            segment=next(s for s in captures[index]['segments'] if s['block_id']==case['block_id'])
            published=segment['visible_text'] or ''
            assert not segment['overflow_text'] and not segment['continuation_lines']
            assert ' '.join(case['translated'].split()) in texts[segment['page']]
            rows.append(dict(case,visible_text=published,full_instruction_in_published_text=True,
                output_pdf_sha256=row['output_sha256'],output_member=row['output_archive_member'],
                png=str(render/f'document-{index}-{segment["page"]+1}.png'),
                source_sha256=row['source_sha256'],visual_review='PENDING'))
(render/'manifest.json').write_text(json.dumps(dict(cases=rows,pages=4,review='PENDING'),ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(rows,ensure_ascii=False,indent=2))
