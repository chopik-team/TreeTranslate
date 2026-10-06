"""LEVEL 2: complete cached native blocks; no writer or implicit raw-line grade."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa/aw081'

def run():
    from app.engine.factory import create_translation_engine
    from app.engine.types import TranslationRequest
    from app.glossary.engine import GlossaryEngine
    from app.glossary.bundled import bundled_paths
    from app.translation_memory.engine import TranslationMemoryEngine
    from app.knowledge.segments import SegmentClassifier
    inventory=json.loads((QA/'major_root_causes.json').read_text('utf8'))['rows']
    documents=json.loads((QA/'diagnostic/representative_holdout.json').read_text('utf8'))['documents']
    paths=list((ROOT/'app').rglob('*.py'))+list((ROOT/'assets/config').glob('*.json'))
    paths+=list(bundled_paths())+[ROOT/'assets/knowledge/manifest.json']
    hashes={p:sha256(p.read_bytes()).hexdigest() for p in paths}
    engine=create_translation_engine(memory=TranslationMemoryEngine(QA/'native-relation-isolated-tm.db'),
        glossary=GlossaryEngine(QA/'native-relation-isolated-user.db',builtin_paths=bundled_paths()))
    rows=[]
    try:
        for case in ('2:5','6:1','15:1'):
            row=next(row for row in inventory if row['id']==case)
            assert len(row['native_layout_matches'])==1
            block=row['native_layout_matches'][0]
            doc=documents[int(case.partition(':')[0])]
            profile=engine.profile_document('zh','ru',identity=doc['sha256'],segments=doc['lines'],
                filename=doc['member'],folders=(doc['member'],))
            source=block['text']
            if source.startswith('• '):source=source[2:]
            result=engine.lookup_direct(TranslationRequest(source,'zh','ru',context_profile=profile,
                segment_type=SegmentClassifier.classify(source).value))
            assert result is not None and result.backend=='knowledge_template'
            rows.append(dict(case=case,source_file_sha256=doc['sha256'],block_id=block['block_id'],
                bbox=block['bbox'],source=source,source_sha256=sha256(source.encode()).hexdigest(),
                output=result.translated_text,output_sha256=sha256(result.translated_text.encode()).hexdigest(),
                route_reason=result.route_reason,constraint_status=result.constraint_status,
                profile=profile.summary(),grade='UNREVIEWED',model_called=False))
    finally:engine.shutdown()
    assert all(sha256(p.read_bytes()).hexdigest()==value for p,value in hashes.items())
    data=dict(revision='AW0.81',level=2,scope='Existing complete native source blocks with recorded geometry; no writer/OCR rerun.',
        references_evaluation_only=True,raw_157_grades_not_replaced=True,final_proof=False,
        source_inventory_sha256=sha256((QA/'major_root_causes.json').read_bytes()).hexdigest(),
        production_hashes={str(p.relative_to(ROOT)):h for p,h in hashes.items()},rows=rows)
    (QA/'native_relation_probe.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
    print('Native complete-block probes',len(rows),'model calls',0)

if __name__=='__main__':run()
