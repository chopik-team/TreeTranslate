"""Export numeric timing priors from accepted evidence; never translate inputs."""
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parents[1]


def build():
    qa=ROOT/'qa/aw081/100pdf_final_speed_calibration'
    summary=json.loads((qa/'run_summary.json').read_text('utf8'))
    manifest=json.loads((qa/'run_manifest.json').read_text('utf8'))
    sources=json.loads((qa/'raw/source_contracts.json').read_text('utf8'))
    good=[d for d in summary['documents'] if d['output_status']=='TRANSLATED']
    classes={}
    for kind in sorted({d['classification'] for d in good}):
        rows=[d for d in good if d['classification']==kind]
        density=[sum(len(s['text']) for s in sources[d['archive_member_path']])/max(1,d['segments']) for d in rows]
        ocr=[d['ocr_measurement_seconds']/d['ocr_region_timings']['regions'] for d in rows if d['ocr_region_timings'].get('regions')]
        classes[kind]=dict(samples=len(rows),segment_seconds=median(d['translation_only_seconds']/max(1,d['segments']) for d in rows),
            write_page_seconds=median(d['writer_seconds']/max(1,d['source_pages']) for d in rows),
            chars_per_segment=median(density),segments_per_page=median(d['segments']/max(1,d['source_pages']) for d in rows),
            ocr_seconds=median(ocr) if ocr else 0.,document_page_seconds=median(d['total_wall_seconds']/max(1,d['source_pages']) for d in rows))
    weights=[max(.25,(d['source_size']/32768)**.5) for d in summary['documents']]
    record=dict(schema=1,version='0.81',source_language='zh',target_language='ru',device='cuda',
        hardware=manifest['hardware'],runs=[summary['run_id']],classes=classes,
        segment_seconds=median(d['translation_only_seconds']/max(1,d['segments']) for d in good),
        write_page_seconds=median(d['writer_seconds']/max(1,d['source_pages']) for d in good),
        chars_per_segment=median(sum(len(s['text']) for s in sources[d['archive_member_path']])/max(1,d['segments']) for d in good),
        segments_per_page=median(d['segments']/max(1,d['source_pages']) for d in good),
        ocr_seconds=classes['mixed']['ocr_seconds'],docs_per_hour=summary['docs_hour'],pages_per_hour=summary['source_pages_hour'],
        archive_seconds_per_size_unit=summary['wall_seconds']/sum(weights),size_unit_bytes=32768,
        cold_start_seconds=summary['time_to_first_document_start'],
        references=[dict(run_id=summary['run_id'],kind='accepted representative 100 PDF',documents=100,wall_seconds=summary['wall_seconds'],
                         docs_per_hour=summary['docs_hour'],used_for_rates=True),
                    dict(run_id='2bf4fd0f345e',kind='current NMT-heavy diagnostic fixed5 baseline',documents=5,wall_seconds=350.8883503,
                         docs_per_hour=5*3600/350.8883503,used_for_rates=False),
                    dict(run_id='25825c3f75a7',kind='historical pre-performance 100 PDF',documents=100,wall_seconds=summary['historical_wall_precise'],
                         docs_per_hour=100*3600/summary['historical_wall_precise'],used_for_rates=False)],
        note='Approximate priors for this measured hardware. Successful documents define complexity rates; failed documents are not treated as cheap successful translations. Archive size prior reproduces accepted 100 wall, without opening all members. Rejected batched replay is excluded.')
    path=ROOT/'assets/config/document-performance.json';path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf8')
    print(path);print(json.dumps(classes,ensure_ascii=False))


if __name__=='__main__':build()
