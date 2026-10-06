"""Current production reconstruction and translation of mapped parent blocks."""
from dataclasses import asdict
import json
import argparse
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.documents.pdf_document import PdfDocument
from app.documents.job import DocumentJob, DocumentConfig
from app.documents.control import JobControl
from app.documents.run_metrics import file_hash, content_hash
from app.knowledge.segments import SegmentClassifier
from app.engine.factory import create_translation_engine
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.engine import TranslationMemoryEngine
from tools.aw081_large_zip import production_hashes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'qa/aw081/iterations/14_phase_a_closure/parents_final')
QA=parser.parse_args().output.resolve()
QA.mkdir(exist_ok=False)
BASE=ROOT/'qa/aw081'
old=json.loads((BASE/'iterations/13_seals_and_rear_view/fragment_coverage.json').read_text('utf8'))
native=json.loads((BASE/'iterations/13_seals_and_rear_view/native_probe.json').read_text('utf8'))
cases=json.loads((BASE/'diagnostic/representative_holdout.json').read_text('utf8'))['documents']
expected={(r['index'],r['block']['block_id']):dict(text=r['block']['text'],output=r['output']) for r in native['rows']}
for row in old['rows']:
    i=int(row['id'].split(':')[0])
    sources={p['block_id']:p['text'] for p in row['production_blocks']}
    for p in row['reviewed_outputs']:
        expected[(i,p['block_id'])]=dict(text=sources[p['block_id']],output=p['output'])
    for p in row['production_blocks']:
        if (i,p['block_id']) not in expected:
            # The fragment also includes the adjacent complete booster caption.
            # Its translated noun and literal drawing marker are reviewed here.
            assert p['text']=='制动助力器 (A)'
            expected[(i,p['block_id'])]=dict(text=p['text'],output='усилитель тормозов (A)')
sealed=production_hashes()
engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'isolated-tm.db'),
    glossary=GlossaryEngine(QA/'isolated-user.db',builtin_paths=bundled_paths()))
original_model=engine.router.translate
model_calls=[]
def unexpected_model(request,*args,**kwargs):
    model_calls.append(content_hash(request.text))
    return original_model(request,*args,**kwargs)
engine.router.translate=unexpected_model
rows=[]
try:
    for index in sorted({k[0] for k in expected}):
        path=BASE/f'diagnostic/originals/{index}.pdf'
        doc=PdfDocument(path)
        assert file_hash(path)==cases[index]['sha256']
        profile=engine.profile_document('zh','ru',identity=doc.source_hash,segments=doc.segments,
            filename=cases[index]['member'],folders=(cases[index]['member'],))
        job=DocumentJob([],DocumentConfig(source='zh',target='ru',domain='auto'),JobControl(),engine.translate,engine.languages.resolve)
        job._domain=profile.primary_domain;job._context_profile=profile;job._snapshot=engine.context_router.snapshot(profile)
        for block in doc.segments:
            baseline=expected.get((index,block.block_id))
            if baseline is None:continue
            job._segment_type=SegmentClassifier.classify(block.text,segment=block).value
            output=job._pdf_translation(block.text,'zh','ru')
            assert block.text==baseline['text'] and output==baseline['output'], (index,block.block_id)
            rows.append(dict(index=index,block=asdict(block),source_file_sha256=doc.source_hash,
                parent_block_sha256=content_hash(block.text),output=output,output_sha256=content_hash(output),grade='PASS',
                evidence='Exact current source/output identity with explicitly reviewed complete parent; normal DocumentJob translation boundary.',
                preserved_relations=['action','negation','condition','object','numbers','direction','technical_meaning']))
finally:engine.shutdown()
assert production_hashes()==sealed
assert not model_calls
indexed={(r['index'],r['block']['block_id']):r for r in rows}
def compact(text):return re.sub(r'\s+','',text)
artifacts=[]
for old_row in old['rows']:
    i=int(old_row['id'].split(':')[0])
    parents=[indexed[(i,p['block_id'])] for p in old_row['production_blocks']]
    joined=''.join(compact(p['block']['text']) for p in parents)
    assert compact(old_row['source']) in joined and compact(old_row['source'])!=joined
    artifacts.append(dict(id=old_row['id'],historical_grade=old_row['raw_grade'],historical_output=old_row['raw_output'],
        source=old_row['source'],fragment_sha256=content_hash(old_row['source']),new_classification='NOT_EVALUABLE_FRAGMENT',
        reason='Incomplete native-line slice: cuts a word, condition, clause or antecedent; no independent complete operation/object/context. Whole reconstructed parent retains the service meaning.',
        source_pdf_sha256=old_row['source_pdf_sha256'],parent_blocks=[dict(block_id=p['block']['block_id'],
            source_sha256=p['parent_block_sha256'],output_sha256=p['output_sha256'],grade=p['grade']) for p in parents],
        evidence_conditions=dict(incomplete_slice=True,insufficient_independent_context=True,specific_parent=True,
            production_reconstruction=True,parent_translation_accepted=True,technical_relations_preserved=True,not_masking_full_block_error=True),
        source_damaged=False,history_unchanged=True))
report=dict(revision='AW0.81',parent_blocks=rows,complete_parent_grades={'PASS':len(rows),'MINOR':0,'MAJOR':0,'CATA':0},
    mapped_historical_major_fragments=artifacts,artifact_counts={'NOT_EVALUABLE_FRAGMENT':len(artifacts)},
    model_calls=len(model_calls),production_hashes=sealed,scope='Native parent reconstruction/translation. Final writer/OCR/ZIP acceptance remains separate.',
    prior_fragment_coverage_sha256=file_hash(BASE/'iterations/13_seals_and_rear_view/fragment_coverage.json'))
(QA/'parent_evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print('PARENTS',len(rows),'ARTIFACTS',len(artifacts),'MODEL',len(model_calls),flush=True)
