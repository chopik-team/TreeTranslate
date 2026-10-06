"""Inventory diagnostic causes and native geometry; never develop from Set A."""
from collections import Counter,defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=ROOT/'qa/aw081'


def folded(text):
    return re.sub(r'\s+','',text)


def run():
    from tools.aw088_prepare import ZIP
    from app.documents.pdf_document import PdfDocument
    from app.documents.pdf_types import PdfError,PdfLimits
    review=json.loads((QA/'iterations/00_inventory/diagnostic_before_iteration.json').read_text('utf8'))
    production_path=QA/'diagnostic/holdout_after_production.json'
    actual={r['id']:r for r in json.loads(production_path.read_text('utf8'))['rows']}
    cases=json.loads((QA/'diagnostic/representative_holdout.json').read_text('utf8'))['documents']
    baseline={r['id']:r for r in json.loads((QA/'diagnostic_before.json').read_text('utf8'))['rows']}
    majors=[r for r in review['rows'] if r['grade']=='MAJOR']
    assert len(majors)==51
    originals=QA/'diagnostic/originals'
    originals.mkdir(exist_ok=True)
    geometry={}
    with ZipFile(ZIP) as archive:
        for index in sorted({int(r['id'].split(':')[0]) for r in majors}):
            doc=cases[index]
            data=archive.read(doc['member'])
            assert sha256(data).hexdigest()==doc['sha256']
            path=originals/f'{index}.pdf'
            path.write_bytes(data)
            try:
                native=PdfDocument(path)
                geometry[index]=[asdict(s) for s in native.segments]
            except PdfError:
                # Read native geometry even when production eligibility requires
                # OCR. This is inventory evidence, never a successful PDF job.
                import pypdfium2 as pdfium
                from app.documents.pdf_document import NativeTextExtractor
                source=pdfium.PdfDocument(path)
                geometry[index]=[]
                try:
                    for page_index in range(len(source)):
                        page=source[page_index]
                        try:
                            extracted=NativeTextExtractor().extract(page,page_index,list(page.get_objects(max_depth=1)),PdfLimits())
                            geometry[index].extend(asdict(s) for s in extracted.segments)
                        finally:
                            page.close()
                finally:
                    source.close()
    rows=[]
    for old in majors:
        r=actual[old['id']]
        assert r['source']==old['source'] and r['output']==old['output']
        matches=[];seen=set()
        for e in r['events']:
            if e['layer']!='glossary_lookup':continue
            for m in e['selected']:
                key=(m['source'],m['target'],m['concept_id'],m['store'],m['start'],m['end'])
                if key not in seen:
                    seen.add(key);matches.append(m)
        layout=[s for s in geometry[int(r['id'].split(':')[0])] if folded(r['source']) in folded(s['text'])]
        model=[e for e in r['events'] if e['layer']=='model']
        split=any(folded(s['text'])!=folded(r['source']) for s in layout)
        reason=[]
        if r['glossary_counter_delta'].get('placeholder_failures'):
            category='CONSTRAINT_TOKEN_INTEGRITY'
            layer='Glossary / PlaceholderCodec'
            reason.append('Actual constrained model call followed by placeholder rejection and unconstrained fallback; selected concepts existed.')
        elif split:
            category='SPLIT_TABLE_OR_PARAGRAPH'
            layer='Diagnostic native-line adapter / production segmentation comparison'
            reason.append('Whole native production block contains this line plus additional text; the diagnostic adapter translated a raw native line independently.')
        elif r['source'].startswith(('[','［')):
            category='LITERAL_IDENTIFIER_FORMAT'
            layer='PDF protected-kind policy'
            reason.append('Standalone paired-bracket Latin code reaches model; translation adds or changes surrounding content.')
        elif r['id'] in {'16:9','16:10'}:
            category='AMBIGUOUS_LABEL'
            layer='Source review / label semantics'
            reason.append('Source wording before/seconds is inconsistent with reservoir quantity-table context; no justified component meaning yet. Not excluded from MAJOR.')
        elif r['id']=='3:9':
            category='UNRESOLVED_CROSS_REFERENCE_LABEL'
            layer='Reviewed compound / cross-reference labels'
            reason.append('Known section retained; unknown whole subsection title annotated exactly, with warning. No translated verified whole title.')
        elif r['source'].endswith(('？','?')):
            category='DIAGNOSTIC_QUESTION'
            layer='Question relation / deterministic grammar'
            reason.append('Model retained question punctuation but changed the diagnostic finding relation; punctuation is not sufficient semantic safety.')
        elif r['id'].split(':')[0] in {'12','13'}:
            category='WEAR_CONDITION'
            layer='Condition/comparison grammar / compound semantics'
            reason.append('Known noun constraints survive; visual inspection, wear subtype or missing-rib condition remains wrong.')
        elif r['constraint_status'].startswith('semantic_source_preserved:'):
            category='SEMANTIC_GUARD_BACKOFF'
            layer='Guard / bounded safe repair coverage'
            reason.append('Guard correctly rejected a conflict but no safe repair succeeded; untranslated known meaning remains MAJOR.')
        elif any(e['source'] in {'控制电路','电路'} for e in matches):
            category='CONTROL_CIRCUIT'
            layer='Electrical compound / constrained rendering'
            reason.append('Control-circuit concept selected; relation or rendering still wrong.')
        elif r['id'] in {'2:3','3:5','3:10','3:12','17:1'}:
            category='LOST_OR_WRONG_ACTION_AND_COMPOUND'
            layer='Action role / verified whole-object coverage'
            reason.append('Action role is dropped/distorted and selected shorter noun does not cover the complete commanded object; not enough evidence to call this only a dictionary gap.')
        else:
            category='PROSE_RELATION_OR_COMPOUND'
            layer='Context / grammar / compound resolution'
            reason.append('Selected nouns alone do not preserve the relation or whole compound meaning; additional DEV/geometry diagnosis required before adding entries.')
        templates=[e['selected_template'] for e in r['events'] if e['layer']=='template' and e['selected_template']]
        rows.append(dict(id=r['id'],source_file_sha256=r['sha256'],source_text_sha256=sha256(r['source'].encode('utf8')).hexdigest(),
            source=r['source'],current_output=r['output'],reference=baseline[r['id']]['reference'],reference_evaluation_only=True,
            domain=r['profile']['selected_domain'],subdomains=r['profile']['selected_subdomains'],stratum=r['stratum'],
            segment_type=r['segment_type'],route_used=dict(knowledge_source=r['knowledge_source'],backend=r['backend'],
                constraint_status=r['constraint_status'],route_reason=r['route_reason']),
            selected_knowledge=matches,selected_concepts=sorted({m['concept_id'] for m in matches if m['concept_id']}),
            selected_templates=templates,model_fallback_status=dict(model_calls=len(model),
                unconstrained_fallback=r['glossary_counter_delta'].get('fallbacks',0),
                placeholder_failures=r['glossary_counter_delta'].get('placeholder_failures',0),
                source_preserved=r['constraint_status'].startswith('semantic_source_preserved:'),events=model),
            native_layout_matches=layout,raw_line_is_part_of_larger_native_block=split,
            root_cause=category,root_cause_evidence=reason,responsible_layer=layer,diagnosis_status='EVIDENCE_RECORDED_NOT_A_PASS'))
    groups=defaultdict(list)
    for r in rows:groups[r['root_cause']].append(r)
    result=dict(revision='AW0.81',starting_major=51,reviewer='Codex; not human-certified',
        reference_sha256=review['immutable_reference_sha256'],production_trace_sha256=sha256(production_path.read_bytes()).hexdigest(),
        untouched_final_set_not_read=True,production_assets_unchanged=True,rows=rows,
        groups=[dict(category=k,count=len(v),examples=[r['id'] for r in v[:4]],
            common_source_structure=sorted({r['segment_type'] for r in v}),
            current_routes=dict(Counter(r['route_used']['constraint_status'] for r in v)),
            actual_root_cause=sorted({reason for r in v for reason in r['root_cause_evidence']}),
            proposed_fix_layers=sorted({r['responsible_layer'] for r in v})) for k,v in groups.items()])
    (QA/'major_root_causes.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print({k:len(v) for k,v in groups.items()})


if __name__=='__main__':
    run()
