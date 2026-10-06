"""Source-derived AW0.7.3 coverage and real model QA; does not edit corpora."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest, DevicePreference
from app.glossary.bundled import bundled_paths
from app.glossary.engine import GlossaryEngine
from app.translation_memory.engine import TranslationMemoryEngine
from tools.qa_knowledge_harvester import faithful


def run(bundled, database, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    corpus = json.loads(Path('tests/fixtures/pdf/semantic-corpus.json').read_text('utf-8'))
    original_pdf = Path('tests/fixtures/pdf/automotive.pdf')
    original_hash = sha256(original_pdf.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='aw073-qa-') as folder:
        folder = Path(folder)
        memory = TranslationMemoryEngine(folder/'tm.db')
        glossary = GlossaryEngine(folder/'g.db', builtin_paths=bundled_paths(Path(bundled)))
        engine = create_translation_engine(memory=memory, glossary=glossary)
        try:
            rows = []
            for item in corpus:
                request = TranslationRequest(item['source'], 'zh', 'ru', DevicePreference.AUTO, domain='automotive')
                baseline = engine.translate(request, backend_only='m2m100')
                after = engine.translate(request)
                hits = glossary.lookup(item['source'], 'zh', 'ru', 'automotive')
                rows.append(dict(id=item['id'], source=item['source'], before=baseline.translated_text,
                    after=after.translated_text, matched=[dict(source=h.entry.source_term,target=h.entry.target_term,pack=h.entry.source_pack) for h in hits],
                    enforced=after.constraint_status=='enforced', fallback=after.constraint_status=='fallback_unconstrained',
                    constraint_status=after.constraint_status, before_fidelity=faithful(item['source'], baseline.translated_text),
                    after_fidelity=faithful(item['source'], after.translated_text), backend=after.backend, device=after.device))
            terms = ['冷却液','冷却剂','散热器','散热器盖','连接器','怠速']
            coverage = {term:[dict(source=m.entry.source_term,target=m.entry.target_term,pack=m.entry.source_pack,
                                  full_term=m.start==0 and m.end==len(term)) for m in glossary.lookup(term,'zh','ru','automotive')] for term in terms}
            automotive = dict(rows=rows, requested_term_coverage=coverage, summary=dict(segments=len(rows),
                matched_terms=sum(len(r['matched']) for r in rows), matched_segments=sum(bool(r['matched']) for r in rows),
                enforced=sum(r['enforced'] for r in rows), fallback=sum(r['fallback'] for r in rows),
                before_fidelity=sum(r['before_fidelity'] for r in rows), after_fidelity=sum(r['after_fidelity'] for r in rows)),
                source_pdf_sha256=original_hash, immutable_original=sha256(original_pdf.read_bytes()).hexdigest()==original_hash,
                human_semantic_quality_verified=False)
            (output/'automotive.json').write_text(json.dumps(automotive,ensure_ascii=False,indent=2)+'\n','utf-8')
            wanted = ['steel','alloy steel','continuous casting','mold','tundish','billet','slab','bloom','ladle','rolling','heat treatment']
            selections = {term:[] for term in wanted}
            con = sqlite3.connect(database)
            try:
                for (payload,) in con.execute("SELECT payload FROM candidates WHERE domain='metallurgy' AND zh!='' AND ru!='' ORDER BY score DESC,id"):
                    candidate = json.loads(payload)
                    labels = [text.casefold() for text in candidate['en']]
                    for term in wanted:
                        if term in labels or term+'s' in labels:
                            selections[term].append(candidate)
            finally:
                con.close()
            metallurgy = {}; examples = []
            for term, candidates in selections.items():
                available = [c for c in candidates if c['status']=='VERIFIED']
                metallurgy[term] = dict(candidates=len(candidates),verified=len(available),examples=[
                    {key:c[key] for key in ('id','zh','ru','en','status','score','link_type','provenance')} for c in candidates[:3]])
                if available:
                    candidate=available[0]
                    source='检查'+candidate['zh']+'。'
                    result=engine.translate(TranslationRequest(source,'zh','ru',DevicePreference.AUTO,domain='metallurgy'))
                    examples.append(dict(source=source,result=result.translated_text,status=result.constraint_status,
                                         candidate_id=candidate['id'],source_derived_term=candidate['zh'],target=candidate['ru'],
                                         backend=result.backend,pack_ids=result.pack_ids))
            (output/'metallurgy.json').write_text(json.dumps(dict(coverage=metallurgy,sentences=examples,
                sentences_are_synthetic_checks_of_source_terms=True,human_semantic_quality_verified=False),ensure_ascii=False,indent=2)+'\n','utf-8')
            started=perf_counter()
            for term in terms:glossary.lookup(term,'zh','ru','automotive')
            facts=dict(tm_units=memory.stats()['total_units'],user_glossary_rows=len(list(glossary.repository.rows())),
                       six_warm_lookup_ms=(perf_counter()-started)*1000,automotive=automotive['summary'],metallurgy_sentences=len(examples))
            (output/'runtime.json').write_text(json.dumps(facts,indent=2)+'\n','utf-8')
            print(json.dumps(facts),flush=True)
        finally:
            engine.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundled',type=Path,required=True)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('docs/qa/aw073'))
    args=parser.parse_args();run(args.bundled,args.db,args.output)
