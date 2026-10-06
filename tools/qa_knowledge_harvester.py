"""Existing automotive corpus and source-derived metallurgy through real models."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest,DevicePreference,PerformanceProfile
from app.translation_memory.engine import TranslationMemoryEngine
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.glossary.constraints import validate_result
from app.glossary.errors import ConstraintFailure


def faithful(source,target):
    try:validate_result(source,target);return True
    except ConstraintFailure:return False


def main():
    output=Path('docs/qa/aw072');output.mkdir(parents=True,exist_ok=True)
    source_pdf=Path('tests/fixtures/pdf/automotive.pdf');original=sha256(source_pdf.read_bytes()).hexdigest()
    corpus=json.loads(Path('tests/fixtures/pdf/semantic-corpus.json').read_text('utf-8'))
    with tempfile.TemporaryDirectory(prefix='harvest-real-qa-') as folder:
        folder=Path(folder);tm=TranslationMemoryEngine(folder/'tm.db')
        glossary=GlossaryEngine(folder/'g.db',builtin_paths=bundled_paths())
        engine=create_translation_engine(memory=tm,glossary=glossary);rows=[]
        try:
            for item in corpus:
                source=item['source'];request=TranslationRequest(source,'zh','ru',DevicePreference.AUTO,PerformanceProfile.BALANCED,domain='automotive')
                hits=glossary.lookup(source,'zh','ru','automotive')
                baseline=engine.translate(request,backend_only='m2m100');result=engine.translate(request)
                rows.append(dict(id=item['id'],source=source,before=baseline.translated_text,after=result.translated_text,
                    matched=[dict(source=m.entry.source_term,target=m.entry.target_term,pack=m.entry.source_pack) for m in hits],
                    known_targets_present=sum(m.entry.target_term in result.translated_text for m in hits),
                    baseline_fidelity=faithful(source,baseline.translated_text),after_fidelity=faithful(source,result.translated_text),
                    forbidden_before=[t for t in item.get('forbidden_additions',[]) if t in baseline.translated_text],
                    forbidden_after=[t for t in item.get('forbidden_additions',[]) if t in result.translated_text],
                    constraint_status=result.constraint_status,backend=result.backend,device=result.device,model_ids=result.model_ids))
            result=engine.translate(TranslationRequest('检查合金钢。','zh','ru',DevicePreference.AUTO,domain='metallurgy'))
            matches=glossary.lookup('检查合金钢。','zh','ru','metallurgy')
            assert len(matches)==1 and matches[0].entry.source_term=='合金钢'
            assert not glossary.lookup('合金钢','zh','ru','automotive')
            assert result.constraint_status=='enforced' and 'легированная сталь' in result.translated_text
            (output/'metallurgy.json').write_text(json.dumps(dict(source='检查合金钢。',output=result.translated_text,
                source_derived_term=matches[0].entry.source_term,target=matches[0].entry.target_term,
                provenance=matches[0].entry.provenance,longest_match=True,domain_isolation=True,status=result.constraint_status),ensure_ascii=False,indent=2),'utf-8')
            report=dict(corpus='tests/fixtures/pdf/semantic-corpus.json',source_pdf_sha256=original,
                immutable_original=sha256(source_pdf.read_bytes()).hexdigest()==original,rows=rows,
                summary=dict(segments=len(rows),matched_terms=sum(len(r['matched']) for r in rows),
                    enforced=sum(r['constraint_status']=='enforced' for r in rows),
                    fallbacks=sum(r['constraint_status']=='fallback_unconstrained' for r in rows),
                    baseline_fidelity_passes=sum(r['baseline_fidelity'] for r in rows),after_fidelity_passes=sum(r['after_fidelity'] for r in rows)),
                tm_units=tm.stats()['total_units'],human_semantic_quality_verified=False)
            (output/'automotive.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
            print(json.dumps(report['summary']))
        finally:engine.shutdown()


if __name__=='__main__':main()
