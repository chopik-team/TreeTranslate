"""Deterministic multi-label profiles; evidence is retained without source text."""
from collections import OrderedDict,Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from pathlib import Path
from time import perf_counter
from app.config.paths import ASSETS_DIR
from app.documents.run_metrics import measure

@dataclass(frozen=True)
class ContextProfile:
    source_language: str
    target_language: str
    primary_domain: str
    domains: tuple
    subdomains: tuple
    document_types: tuple
    content_types: tuple
    evidence: tuple
    identity: str
    version: str='0.8.6'
    semantic_facts: tuple=()

    def summary(self):
        return dict(source_language=self.source_language,target_language=self.target_language,selected_domain=self.primary_domain,
            domain_scores=dict(self.domains),selected_subdomains=dict(self.subdomains),document_types=dict(self.document_types),
            content_types=dict(self.content_types),content_characteristics=dict(self.content_types),
            confidence=dict(self.domains).get(self.primary_domain,0.),
            evidence=self.evidence,identity=self.identity,version=self.version,semantic_facts=self.semantic_facts)

class DocumentProfiler:
    def __init__(self,config=None):
        self.config=config or json.loads((ASSETS_DIR/'config/knowledge-context.json').read_text('utf-8'))
        self.semantic_rules=json.loads((ASSETS_DIR/'config/source-semantic-corrections.json').read_text('utf-8'))['facts']
        self.cache=OrderedDict();self.calls=0;self.cache_hits=0;self.seconds=0.

    @measure('DocumentProfiler')
    def profile(self,source,target,*,identity='',segments=(),filename='',folders=(),archive='',parent=None):
        from .segments import SegmentClassifier
        items=list(segments)
        semantic=[s for s in items if not getattr(s,'ocr_kind','') in ('noise','identifier','measurement')]
        if len(semantic)>24:
            semantic=[semantic[round(i*(len(semantic)-1)/23)] for i in range(24)]
        texts=[s if isinstance(s,str) else s.text for s in semantic]
        # Spread bounded content rather than duplicating entire PDFs in caches.
        text='\n'.join(texts)
        if len(text)>8000:text=text[:2666]+text[len(text)//2:len(text)//2+2667]+text[-2667:]
        content_hash=sha256(text.encode('utf-8')).hexdigest()
        key=(identity,source,target,self.config['version'],content_hash,filename,tuple(folders),archive,parent.identity if parent else '')
        if key in self.cache:
            self.cache_hits+=1;value=self.cache.pop(key);self.cache[key]=value;return value
        started=perf_counter();self.calls+=1
        sources={'content':text,'filename':Path(filename).stem,'folder':'\n'.join(folders),'archive':Path(archive).stem}
        weighted=Counter();unique={};evidence=[]
        for branch,signals in self.config['signals'].items():
            seen=set()
            for origin,data in sources.items():
                data=data.casefold()
                for term in signals:
                    count=data.count(term.casefold())
                    if count:
                        seen.add(term);weighted[branch]+=self.config['weights'][origin]*(1+.1*min(3,count-1))
                        evidence.append((branch,origin,sha256(term.encode('utf-8')).hexdigest()[:12],min(count,4)))
            unique[branch]=seen
        # Parent is a bounded prior. Strong child content is never relabelled.
        if parent:
            for branch,confidence in parent.subdomains:
                # An inherited candidate stays below direct content evidence.
                weighted[branch]+=self.config['weights']['parent']*confidence
                evidence.append((branch,'parent',parent.identity[:12],round(confidence,4)))
        scores={b:round(min(.995,1-math.exp(-v/self.config['confidence_scale'])),4) for b,v in weighted.items()}
        domain_raw=Counter();domain_unique={}
        for branch,value in weighted.items():
            domain=branch.split('.')[0];domain_raw[domain]+=value
            domain_unique.setdefault(domain,set()).update(unique.get(branch,()))
        domains={d:round(min(.995,1-math.exp(-v/self.config['confidence_scale'])),4) for d,v in domain_raw.items()}
        accepted={d:s for d,s in domains.items() if s>=self.config['primary_threshold'] and len(domain_unique.get(d,()))>=self.config['minimum_signals']}
        primary=max(accepted,key=accepted.get) if accepted else 'general'
        # Weak candidates are kept with their true scores, not promoted to certainty.
        subdomains=tuple(sorted((b,s) for b,s in scores.items() if s>=self.config['candidate_threshold']))
        if parent and not accepted and not any(unique.values()):
            # Empty/opaque child names can reuse the prior, explicitly discounted.
            domains={d:round(s*.6,4) for d,s in parent.domains}
            primary=parent.primary_domain if max(domains.values(),default=0)>=.45 else 'general'
            subdomains=tuple((b,round(s*.6,4)) for b,s in parent.subdomains if s*.6>=self.config['candidate_threshold'])
        kinds=Counter(SegmentClassifier.classify(t,segment=s if not isinstance(s,str) else None).value for s,t in zip(semantic,texts))
        types=[]
        for name,signals in self.config['document_signals'].items():
            hits=sum(term.casefold() in text.casefold() for term in signals)
            if hits:types.append((name,round(1-math.exp(-hits/2),4)))
        facts=tuple(rule['id'] for rule in self.semantic_rules if source=='zh' and
                    all(re.search(pattern,text,re.I) for pattern in rule['all_patterns']))
        value=ContextProfile(source,target,primary,tuple(sorted(domains.items())),subdomains,tuple(types),
            tuple(sorted((k,v/max(1,len(texts))) for k,v in kinds.items())),tuple(evidence),sha256(repr(key).encode()).hexdigest(),
            version=self.config['version'],semantic_facts=facts)
        self.cache[key]=value
        while len(self.cache)>self.config['profile_cache_limit']:self.cache.popitem(last=False)
        self.seconds+=perf_counter()-started;return value

    def clear(self):self.cache.clear()
