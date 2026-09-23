"""Measure changes outside explicit raster masks and written text; inspect both renderers separately."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as raw


def check(source,output):
    metrics=[]
    with pdfium.PdfDocument(source) as before,pdfium.PdfDocument(output) as after:
        for i in range(len(before)):
            a,b=before[i],after[i]
            bm=a.render(scale=1.5);original=np.array(bm.to_pil().convert('RGB'));bm.close()
            bm=b.render(scale=1.5);result=np.array(bm.to_pil().convert('RGB'));bm.close()
            protected=np.ones(original.shape[:2],dtype=bool)
            height,width=protected.shape
            for obj in b.get_objects():
                if obj.type in (raw.FPDF_PAGEOBJ_TEXT,raw.FPDF_PAGEOBJ_PATH):
                    x,y,r,t=obj.get_bounds()
                    x,r=int(x*1.5)-3,int(r*1.5)+4
                    y,t=height-int(t*1.5)-3,height-int(y*1.5)+4
                    protected[max(0,y):min(height,t),max(0,x):min(width,r)]=False
            diff=np.max(np.abs(original.astype(int)-result.astype(int)),axis=2)
            changed=int(np.sum((diff>2)&protected))
            metrics.append(dict(page=i+1,unmasked_pixels=int(protected.sum()),unexpected_changed_pixels=changed))
            assert changed==0,(i,changed)
            a.close();b.close()
        pages=len(after)
    return metrics,pages


def main():
    root=Path(__file__).resolve().parents[1]
    qa=root/'docs/qa/aw062';rows=[]
    outputs={item['case']:Path(item['output']) for item in json.loads((qa/'end-to-end.json').read_text('utf-8'))}
    for name in ('automotive','silverstone','english','rotated'):
        source=root/'build/aw062'/(name+'-scan.pdf')
        output=outputs[name]
        if not output.is_absolute():output=root/output
        metrics,pages=check(source,output)
        rows.append(dict(case=name,output=str(output),pages=pages,metrics=metrics))
    (qa/'visual-invariants.json').write_text(json.dumps(rows,indent=2),'utf-8')
    print(f'All pixels outside masks and written text unchanged on {sum(len(row["metrics"]) for row in rows)} original pages')


if __name__=='__main__':main()
