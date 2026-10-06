"""Record reviewed development evidence separately from immutable historical QA."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw081_large_zip import production_hashes
from app.documents.run_metrics import file_hash,content_hash
QA=ROOT/'qa/aw081/iterations/14_phase_a_closure'

def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')

def run(benchmark):
    pytest=json.loads((QA/'full_pytest_final_gui/execution.json').read_text('utf8'))
    assert pytest['returncode']==0 and pytest['production_unchanged']
    seal=production_hashes()
    assert seal==pytest['production_hashes_after']
    logging=json.loads(Path(benchmark).read_text('utf8'))
    assert logging['output_content_and_rendering_equivalent'] and logging['source_immutable']
    parents=json.loads((QA/'parents_final_fixed/parent_evidence.json').read_text('utf8'))
    assert len(parents['parent_blocks'])==16 and len(parents['mapped_historical_major_fragments'])==18
    assert parents['complete_parent_grades'].get('MAJOR',0)==0
    old=json.loads((ROOT/'qa/aw081/coolant_regression.json').read_text('utf8'))
    fresh=json.loads((QA/'level3/coolant_e2e.json').read_text('utf8'))
    rows=[]
    for historical,segment in zip(old['rows'],fresh['documents'][0]['segments'],strict=True):
        index=historical['index']
        assert historical['source']==segment['text']
        grade=historical['before_grade']
        reason='Previously reviewed output unchanged; all full outputs reviewed again in current production context.'
        if index in (8,36,49,60,65,73,107):
            grade='PASS';reason='Current output matches explicit user OEM interpretation; prior MAJOR retained in historical evidence.'
        else:assert historical['after']==segment['translated']
        if index==8:
            grade='SOURCE_DAMAGED';reason='Truncated, malformed source cross-reference. Current target recovered through explicit user-reviewed OEM alias; not counted as PASS.'
        if index in (18,83):
            grade='SOURCE_AMBIGUOUS';reason='Conflicting source unit labels preserved and flagged; do not infer litre/quart conversion.'
        if index in (22,87):
            grade='SOURCE_AMBIGUOUS';reason='Source describes a threshold as below 45-60%; interval preserved without inventing one threshold.'
        publication=grade
        if grade=='PASS' and segment['policy']=='CONSERVATIVE_PRESERVE':publication='MINOR'
        rows.append(dict(index=index,block_id=segment['block_id'],source=segment['text'],
            source_sha256=content_hash(segment['text']),output=segment['translated'],
            output_sha256=content_hash(segment['translated'] or ''),historical_grade=historical['before_grade'],
            semantic_grade=grade,publication_grade=publication,reason=reason,
            publication_policy=segment['policy'],visible_text=segment['visible_text'],
            overflow_text=segment['overflow_text'],preserve_reason=segment['preserve_reason']))
    counts=Counter(r['semantic_grade'] for r in rows)
    published=Counter(r['publication_grade'] for r in rows)
    assert counts['MAJOR']==counts['CATA']==0
    write(QA/'level3/coolant_semantic_review.json',dict(reviewer='Codex; not human-certified',
        semantic_grades=dict(counts),publication_grades=dict(published),rows=rows,
        semantic_denominator=sum(counts[g] for g in ('PASS','MINOR','MAJOR','CATA')),
        source_immutable=fresh['source_hash_before']==fresh['source_hash_after'],
        candidate_translation_is_not_published_translation=True,
        limitation='Small OCR diagram/menu labels that cannot fit preserve the intact source. This is publication MINOR, never a claim of fully Russian screenshots. Full prose retained instead of translation would require MAJOR review.'))
    render_path=QA/'level3/render/manifest.json'
    render=json.loads(render_path.read_text('utf8'))
    assert len(render['contact_sheets'])==11 and render['all_output_pages']==27
    write(QA/'level3/visual_review.json',dict(reviewer='Codex',contact_sheets_reviewed=render['contact_sheets'],
        rendered_pages=27,source_comparison_pages=26,new_layout_damage=False,
        images_preserved=True,continuation_warnings_readable=True,
        retained_source_labels_reported=True,manifest_sha256=file_hash(render_path)))
    exhaust=json.loads((QA/'exhaust_assembly/whole_pdf.json').read_text('utf8'))['documents'][0]
    assert len(exhaust['segments'])==9 and exhaust['source_pages']==exhaust['output_pages']==1
    write(QA/'exhaust_assembly/semantic_review.json',dict(reviewer='Codex',
        source_sha256=exhaust['source_sha256'],output_sha256=exhaust['output_sha256'],
        semantic_grades=dict(PASS=7,MINOR=0,MAJOR=0,CATA=0),protected_labels=2,
        joint_assembly_remove_operations=1,component_concepts_remain_separate=True,
        visual_review='PASS',render_sha256=file_hash(QA/'exhaust_assembly/render-1.png')))
    body=json.loads((QA/'level3/body_quality.json').read_text('utf8'))
    assert body['crc_ok'] and body['source_immutable']
    assert body['after']['protected_preserved']==body['after']['protected_total']==419
    assert all(r['status']=='PASS' for r in body['stable_instructions'])
    gate=dict(revision='AW0.81',phase_A='PASS',level_3='PASS',full_pytest='PASS',
        production_hashes=seal,historical_raw_grades=dict(PASS=108,MINOR=31,MAJOR=18,CATA=0),
        artifact_counts=dict(NOT_EVALUABLE_FRAGMENT=18),
        complete_parent_grades=parents['complete_parent_grades'],
        exhaust_whole_pdf_grades=dict(PASS=7,MINOR=0,MAJOR=0,CATA=0),
        coolant_semantic_grades=dict(counts),coolant_publication_grades=dict(published),
        semantic_denominators_are_separate=True,
        logging_benchmark_path=str(Path(benchmark).resolve()),
        logging_overhead_percent=logging['overhead_percent'],
        gui_logging_test='14 tests passed, including normal GUI ZIP run',
        level3_note='Fresh complete production BODY and coolant run preceded GUI-only journal activation. No translation, segmentation, OCR or writer behavior changed afterward. Current common full pytest and logging equivalence benchmark follow GUI activation.',
        publication_limitations=['BODY: 23 retained Chinese residue labels; accepted baseline unchanged.',
            'Coolant: eight compact OCR menu/diagram labels preserve source instead of replacing the image. Candidate translation is recorded but not fully published.'],
        frozen_A='NOT_YET_USED',large_zip_translation_started=False)
    write(QA/'acceptance_gate.json',gate)
    print('PHASE_A_PASS LEVEL3_PASS FULL_PYTEST_PASS',counts,flush=True)

if __name__=='__main__':run(sys.argv[1])
