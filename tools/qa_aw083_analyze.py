"""Post-run structural evidence; never changes production or translated PDFs."""
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import json
import re
import subprocess
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

from qa_aw083_baseline import ROOT, QA, BUILD, CORPUS, ARCHIVE, digest, save, normalized, pdf_inventory


def load(name): return json.loads((QA/name).read_text('utf-8'))


def image_signatures(path):
    from pypdf import PdfReader
    from hashlib import sha256
    result=[]
    for page in PdfReader(path).pages:
        items=[]
        def collect(resources, seen):
            resources=resources.get_object() if hasattr(resources,'get_object') else resources
            xobjects=resources.get('/XObject',{})
            xobjects=xobjects.get_object() if hasattr(xobjects,'get_object') else xobjects
            for obj in xobjects.values():
                key=(getattr(obj,'idnum',None),getattr(obj,'generation',None))
                if key in seen:continue
                seen.add(key);obj=obj.get_object()
                if obj.get('/Subtype')=='/Image':
                    items.append((int(obj['/Width']),int(obj['/Height']),sha256(obj.get_data()).hexdigest()))
                elif obj.get('/Subtype')=='/Form':collect(obj.get('/Resources',{}),seen)
        collect(page.get('/Resources',{}),set())
        result.append(Counter(items))
    return result


def tokens(text):
    return {
        'numbers':Counter(re.findall(r'(?<![A-Za-z])\d+(?:[.,]\d+)?',text)),
        'dimensions':Counter(re.findall(r'\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?',text,re.I)),
        'diameter':Counter(re.findall('[Øø⌀Φφ]',text)),
        'units':Counter(re.findall(r'\b(?:mm|inch)\b',text,re.I)),
        'labels':Counter(re.findall(r'\b[A-Z]\b',text)),
    }


def analyze():
    inventory=load('corpus-inventory.json'); raw=load('raw-instrumentation.json'); memory=load('memory.json')
    runs={name:load(name+'-run.json') for name in ('cold','warm')}
    allmetrics=[];quality=[];repetition={};pipelines={};domains={}
    render_jobs=[]
    for name,run in runs.items():
        events=[e for e in raw['events'] if e['run']==name]
        records=[d for d in raw['documents'] if d['run']==name]
        ocr=[d for d in raw['ocr'] if d['run']==name]
        totals=defaultdict(lambda:dict(calls=0,inclusive_s=0.,exclusive_s=0.))
        for event in events:
            entry=totals[event['stage']];entry['calls']+=1
            entry['inclusive_s']+=event['seconds'];entry['exclusive_s']+=event['self_seconds']
        pipelines[name]=dict(stages=dict(totals),
            note='Inclusive stages overlap. Exclusive stages subtract wrapped children only; instrumentation callbacks and uncaptured work remain in parent/self or wall time. OCR returned timings cover the selected recognizer only: Auto may test multiple recognizers and reroute. Selected init/inference below are partial, NOT total OCR time. All worker roundtrips and router wall time are measured. PDF parsing is load calls, not all object enumeration. Classification/postprocess residual is not independently split.',
            ocr_selected_load_s=sum(o['timings'].get('load_seconds',0) for o in ocr),
            ocr_selected_inference_s=sum(o['timings'].get('inference_seconds',0) for o in ocr),
            ocr_all_candidates_init_s=None,ocr_all_candidates_inference_s=None)
        domains[name]=[dict(file=d['file'],source=d['source'],target=d['target'],evidence=d['evidence'])
                       for d in raw['domains'] if d['run']==name]
        segments=[s['text'] for d in records for s in d['segments']]
        model=[d for d in raw['backend'] if d['run']==name]
        chunks=[d for d in raw['chunks'] if d['run']==name]
        counts=Counter(segments); norms=Counter(map(normalized,segments))
        phrase='本图中所示的这些尺寸值为实际测量的尺寸值。'
        repetition[name]=dict(segments=len(segments),unique_exact=len(counts),unique_normalized=len(norms),
            exact_duplicates=len(segments)-len(counts),normalized_duplicates=len(segments)-len(norms),
            backend_calls=len(model),native_inference_calls=sum(i['run']==name for i in raw['inference']),
            backend_unique_request_texts=len({normalized(b['request']['text']) for b in model}),
            request_local_chunks=sum(c['total'] for c in chunks),unique_chunks_per_request_sum=sum(c['unique'] for c in chunks),
            chunks_sent=sum(c['sent'] for c in chunks),duplicate_chunks_avoided=sum(c['avoided'] for c in chunks),
            repeated_ocr_region_hashes=len(ocr)-len({o['image_sha256'] for o in ocr}),
            repeated_target_phrase_occurrences=sum(phrase in s for s in segments),
            repeated_texts=[dict(text=k,count=v) for k,v in counts.most_common(30) if v>1],
            tm_counter_delta={k:v-run['runtime_before']['tm_counters'].get(k,0) for k,v in run['runtime_after']['tm_counters'].items()},
            glossary_counter_delta={k:v-run['runtime_before']['glossary_counters'].get(k,0) for k,v in run['runtime_after']['glossary_counters'].items()},
            direct_knowledge_results=sum(e['stage']=='knowledge_direct' for e in raw['results'] if e['run']==name),
            note='TM lookup hits include prefetch/repeated lookups; reused is actual reuse. Exact repeated document segments are not automatically avoided model calls. Chunk dedup is per request only.')
        assert len(records)==len(run['outputs']), (name,len(records),run['outputs'])
        for doc,output in zip(records,run['outputs']):
            rel=doc['file'];source=CORPUS/rel;output=Path(output)
            before,source_text=pdf_inventory(source);after,translated_text=pdf_inventory(output)
            es=[e for e in events if e['file']==rel]
            opens=[e for e in raw['opens'] if e['run']==name and e['file']==rel]
            publication=next(e for e in raw['published'] if e['run']==name and e['file']==rel)
            attributed=opens[0]['seconds']+(publication['start']+publication['seconds']-opens[1]['start'])
            oc=[o for o in ocr if o['file']==rel]
            rss=[s for s in memory['ram'] if s['run']==name and s['file']==rel]
            domain=next(d for d in domains[name] if d['file']==rel)
            def duration(stage):return sum(e['seconds'] for e in es if e['stage']==stage)
            metric=dict(run=name,file=rel,pages=before['pages'],source_bytes=before['size'],
                output=str(output),output_pages=after['pages'],output_bytes=after['size'],
                classification=doc['classification'],ocr=bool(oc),ocr_regions=len(oc),
                ocr_pages=len({o['page'] for o in oc}),source_language=domain['source'],domain=domain['evidence'],
                total_file_attributed_s=attributed,parse_s=duration('pdf_parse'),
                native_extract_s=duration('native_extraction_grouping'),ocr_s=duration('ocr_total'),
                ocr_selected_init_s=sum(o['timings'].get('load_seconds',0) for o in oc),
                ocr_selected_inference_s=sum(o['timings'].get('inference_seconds',0) for o in oc),
                translate_s=duration('translation_backend'),layout_write_s=duration('pdf_write'),
                validation_s=duration('validation'),publication_s=duration('publication'),
                peak_main_rss=max((s['main_rss'] for s in rss),default=0),
                peak_combined_rss=max((s['combined'] for s in rss),default=0),status='completed',
                per_file_time_note='First extraction/open duration plus second-open to publication interval; first-pass domain time reported separately. Not file wall span including other PDFs.')
            allmetrics.append(metric);save(QA/'metrics'/name/Path(rel).with_suffix('.json'),dict(**metric,warnings=doc['warnings']))
            save(QA/'segment-mapping'/name/Path(rel).with_suffix('.json'),doc['segments'])
            dest=QA/'translated-text'/name/Path(rel).with_suffix('.txt');dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text('\n\n'.join(f'=== PAGE {i+1} ===\n{text}' for i,text in enumerate(translated_text)),'utf-8')
            src_images=image_signatures(source);out_images=image_signatures(output)
            image_ok=all(not (old-new) for old,new in zip(src_images,out_images))
            native_tokens=tokens('\n'.join(source_text));out_tokens=tokens('\n'.join(translated_text))
            missing={kind:dict(values-out_tokens[kind]) for kind,values in native_tokens.items()}
            segment_missing=[]
            for s in doc['segments']:
                if s['translated'] is None:continue
                a=tokens(s['text']);b=tokens(s['translated'])
                diffs={kind:dict(count-b[kind]) for kind,count in a.items() if count-b[kind]}
                if diffs:segment_missing.append(dict(page=s['page']+1,block=s['block_id'],origin=s['origin'],missing=diffs))
            outside=[];overlaps=[]
            for s in doc['segments']:
                w,h=before['page_inventory'][s['page']]['size']
                for box in s['written_boxes']:
                    if box[0]<-.5 or box[1]<-.5 or box[2]>w+.5 or box[3]>h+.5:
                        outside.append(dict(page=s['page']+1,block=s['block_id'],box=box))
            for i,s in enumerate(doc['segments']):
                for other in doc['segments'][i+1:]:
                    if other['page']!=s['page']:continue
                    for a in s['written_boxes']:
                        for b in other['written_boxes']:
                            overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                            area=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
                            if area>0 and overlap/area>.2:overlaps.append(dict(page=s['page']+1,blocks=[s['block_id'],other['block_id']],ratio=overlap/area))
            q=dict(run=name,file=rel,opens=True,production_validation=doc['validated'],
                source_sha256_unchanged=before['sha256']==next(f['sha256'] for f in inventory['files'] if f['file']==rel),
                source_pages=before['pages'],output_pages=after['pages'],continuation_pages=doc['continuations'],
                original_image_streams_preserved=image_ok,source_unique_image_resources=sum(sum(c.values()) for c in src_images),
                blank_page_candidates=[p['page'] for p in after['page_inventory'] if not p['native_chars'] and not p['images'] and not p['paths']],
                native_tokens_missing_from_extracted_output=missing,segment_token_difference_candidates=segment_missing,
                written_boxes_outside_page=outside,written_box_overlap_candidates=overlaps,
                preserved_segments=sum(s['policy']=='CONSERVATIVE_PRESERVE' for s in doc['segments']),
                untranslated_cjk_segments=[dict(page=s['page']+1,block=s['block_id'],origin=s['origin'],policy=s['policy'])
                    for s in doc['segments'] if re.search('[\u4e00-\u9fff]',s['translated'] or s['text'])],
                warnings=doc['warnings'],semantic_translation_certified=False)
            quality.append(q)
            if name=='warm':render_jobs.append((rel,source,output))
    save(QA/'pipeline-timings.json',pipelines);save(QA/'repetition-analysis.json',repetition)
    save(QA/'domain-results.json',domains);save(QA/'quality-structure.json',quality)
    save(QA/'per-file-summary.json',allmetrics)
    before=json.loads((BUILD/'production-before.json').read_text('utf-8'))
    changed=[rel for rel,h in before.items() if not (ROOT/rel).is_file() or digest(ROOT/rel)!=h]
    validation=dict(production_hashes_checked=len(before),production_changes=changed,
        source_archive_unchanged=digest(ARCHIVE)==inventory['archive_sha256'],
        source_files_unchanged=all(q['source_sha256_unchanged'] for q in quality),
        all_outputs_open=all(q['opens'] for q in quality),all_production_validation=all(q['production_validation'] for q in quality),
        image_streams_preserved=all(q['original_image_streams_preserved'] for q in quality),
        main_network_attempts=len(raw['network']),ocr_network_attempts=max((o['timings'].get('network_attempts',0) for o in raw['ocr']),default=0),
        network_scope='Python audit events plus OCR worker counters; native-library OS traffic not packet-captured. Existing offline runtime settings remain active.',
        semantic_quality='Not certified; independent user reference comparison pending.')
    save(QA/'validation.json',validation)
    # Render only after both measurements so QA does not warm or load the measured runtime.
    render_dir=QA/'renders';render_dir.mkdir(exist_ok=True)
    for index,(rel,source,output) in enumerate(render_jobs,1):
        for kind,path in [('source',source),('warm',output)]:
            subprocess.run(['pdftoppm','-scale-to','900','-png',str(path),str(render_dir/f'{index:02}-{kind}')],check=True,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)
    from PIL import Image,ImageDraw
    for index,(rel,source,output) in enumerate(render_jobs,1):
        src=sorted(render_dir.glob(f'{index:02}-source-*.png'));out=sorted(render_dir.glob(f'{index:02}-warm-*.png'))
        width=660;height=480*max(len(src),len(out))
        sheet=Image.new('RGB',(width,height),'#dedede');draw=ImageDraw.Draw(sheet)
        for col,paths in enumerate((src,out)):
            for row,path in enumerate(paths):
                with Image.open(path) as im:
                    im.thumbnail((325,450));sheet.paste(im,(col*330,row*480+24))
                draw.text((col*330+5,row*480+5),f'{"SOURCE" if col==0 else "WARM OUTPUT"} / PAGE {row+1}',fill='black')
        sheet.save(render_dir/f'{index:02}-contact.png')
    print(json.dumps(dict(validation=validation,cold_s=runs['cold']['wall_seconds'],warm_s=runs['warm']['wall_seconds'],
                         repetition=repetition,metrics=allmetrics),ensure_ascii=False,indent=2))


if __name__=='__main__':analyze()
