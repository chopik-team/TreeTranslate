"""Quantitative real-world PDF gate; no OCR, no generated semantic reference."""
from pathlib import Path
import json,ctypes,re
from hashlib import sha256
import pypdfium2 as p
import pypdfium2.raw as raw
import numpy as np
from PIL import Image,ImageChops
from tools.pdf_fixtures import render


def inspect(path):
    pages=[]
    with p.PdfDocument(path) as d:
        for i in range(len(d)):
            g=d[i];images=[]
            for o in g.get_objects(max_depth=1):
                if o.type==raw.FPDF_PAGEOBJ_IMAGE:
                    n=raw.FPDFImageObj_GetImageDataRaw(o,None,0)
                    data=(ctypes.c_ubyte*n)();raw.FPDFImageObj_GetImageDataRaw(o,data,n)
                    images.append({'bounds':o.get_bounds(),'sha256':sha256(bytes(data)).hexdigest()})
            pages.append({'dimensions':g.get_size(),'images':images,'annotations':raw.FPDFPage_GetAnnotCount(g)})
            g.close()
    return pages


def background(path,out):
    with p.PdfDocument(path) as d:
        for i in range(len(d)):
            g=d[i]
            for o in list(g.get_objects(max_depth=1)):
                if o.type==raw.FPDF_PAGEOBJ_TEXT:g.remove_obj(o);o.close()
                else:
                    for getter,setter in [(raw.FPDFPageObj_GetFillColor,raw.FPDFPageObj_SetFillColor),(raw.FPDFPageObj_GetStrokeColor,raw.FPDFPageObj_SetStrokeColor)]:
                        c=[ctypes.c_uint() for _ in range(4)]
                        if getter(o,*c):setter(o,*(v.value for v in c))
            g.gen_content();g.close()
        d.save(out)


def main():
    qa=Path('docs/qa/aw061');reports=json.loads((qa/'real-world.json').read_text());results=[]
    for report in reports:
        name=report['name'];source=Path('tests/fixtures/pdf')/(name+'.pdf');output=Path(report['output']);old,new=inspect(source),inspect(output)
        corpus=json.loads((qa/(name+'-corpus.json')).read_text(encoding='utf-8'))
        numeric=[];identifier=[];outside=[];overlaps=[]
        for block in corpus:
            numbers=lambda t:[v.replace(',','.') for v in re.findall(r'\d+(?:[.,]\d+)?',t)]
            if numbers(block['text'])!=numbers(block['translated']):numeric.append(block['block_id'])
            ids=re.findall(r'(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])',block['text'])
            if any(v not in block['translated'] for v in ids):identifier.append(block['block_id'])
            w,h=old[block['page']]['dimensions']
            for box in block['written_boxes']:
                if box[0]<-.5 or box[1]<-.5 or box[2]>w+.5 or box[3]>h+.5:outside.append(block['block_id'])
        for i,a in enumerate(corpus):
            for b in corpus[i+1:]:
                if a['page']!=b['page']:continue
                if any(min(x[2],y[2])-max(x[0],y[0])>.5 and min(x[3],y[3])-max(x[1],y[1])>.5 for x in a['written_boxes'] for y in b['written_boxes']):overlaps.append([a['block_id'],b['block_id']])
        scratch=Path('build/aw061/backgrounds')/name;scratch.mkdir(parents=True,exist_ok=True)
        paths=[]
        for tag,path in [('before',source),('after',output)]:
            out=scratch/(tag+'.pdf');background(path,out);paths.append(render(out,scratch/tag))
        differences=[]
        for i in range(len(old)):
            diff=np.asarray(ImageChops.difference(Image.open(paths[0][i]),Image.open(paths[1][i])))
            differences.append(float((diff.max(axis=2)>2).mean()))
        result=dict(name=name,dimensions_preserved=all(a['dimensions']==b['dimensions'] for a,b in zip(old,new)),images_preserved=all(a['images']==b['images'] for a,b in zip(old,new)),image_count=sum(len(a['images']) for a in old),background_pixel_difference_ratio=differences,numeric_failures=numeric,identifier_failures=identifier,text_outside_page=outside,text_overlaps=overlaps,annotations=sum(a['annotations'] for a in new))
        results.append(result)
    (qa/'gates.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results))


if __name__=='__main__':main()
