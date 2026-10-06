"""Availability audit on the same eligible segments as AW085, without a model."""
from collections import Counter
import json
from pathlib import Path
import re
import sys
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.engine.types import TranslationRequest
from app.documents.pdf_types import PdfSegment
from app.documents.pdf_ocr_policy import classify,protected_kind
from app.knowledge.profile import ContextProfile
from app.knowledge.segments import SegmentClassifier

QA=ROOT/'qa/aw086';run=json.loads((QA/'body_e2e.json').read_text('utf-8'))
profiles=[p for p in run['context']['profiles'] if p['purpose']=='document']
engine=TranslationKnowledgeEngine(Mock(),Mock(lookup=Mock(return_value=None)),GlossaryEngine(QA/'coverage-isolated-user.db',builtin_paths=bundled_paths()))
rows=[]
for doc,data in zip(run['documents'],profiles):
    profile=ContextProfile(data['source_language'],data['target_language'],data['selected_domain'],
        tuple(data['domain_scores'].items()),tuple(data['selected_subdomains'].items()),tuple(data['document_types'].items()),
        tuple(data['content_types'].items()),tuple(tuple(e) for e in data['evidence']),data['identity'])
    snapshot=engine.context_router.snapshot(profile)
    for data in doc['segments']:
        segment=PdfSegment(**data);kind=classify(segment) if segment.origin=='ocr' else protected_kind(segment.text)
        if kind in ('noise','identifier','measurement') or not re.search('[\u4e00-\u9fff]',segment.text):status='PROTECTED';result=None
        else:
            result=engine.lookup_direct(TranslationRequest(segment.text,'zh','ru',domain='auto',context_profile=profile,
                knowledge_snapshot=snapshot,segment_type=SegmentClassifier.classify(segment.text,segment=segment).value))
            status='KNOWN' if result else 'UNKNOWN'
        rows.append(dict(file=doc['file'],page=segment.page,block=segment.block_id,status=status,source=segment.text,
                         target=result.translated_text if result else None))
counts=Counter(r['status'] for r in rows)
(QA/'knowledge_availability.json').write_text(json.dumps(dict(counts=counts,rows=rows),ensure_ascii=False,indent=2)+'\n','utf-8')
print(dict(counts),flush=True)
