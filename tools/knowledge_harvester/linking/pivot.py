"""Deterministic English sense retrieval; supporting evidence never proves a translation."""
from collections import OrderedDict
import json
import re
from ..normalization import normalize, preferred, variants
from ..domains import classify


def lexemes(record):
    items=[('preferred',record['labels'].get('en',''))]
    items.extend(('alias',v) for v in record['aliases'].get('en',[]))
    items.extend(('gloss',v) for v in record['definitions'])
    for kind,original in items:
        if not original or re.match(r'(?i)^(CL:|see |variant of |old variant of |abbr\.)',original):continue
        for fragment in original.split(';'):
            qualifiers=re.findall(r'\(([^()]*)\)',fragment)
            text=normalize(re.sub(r'\([^()]*\)','',fragment)).casefold()
            if text and len(text)<=100 and len(text.split())<=6:
                yield dict(term=text,kind=kind,original=original,qualifiers=qualifiers)


def prepare_index(con):
    con.execute('CREATE TEMP TABLE pivot_terms(term TEXT,concept TEXT,kind TEXT,original TEXT)')
    for row in con.execute('SELECT id,payload FROM concepts ORDER BY id'):
        records=json.loads(row['payload'])['records']
        con.executemany('INSERT INTO pivot_terms VALUES(?,?,?,?)',
            ((item['term'],row['id'],item['kind'],item['original']) for r in records for item in lexemes(r)))
    con.execute('CREATE INDEX pivot_lookup ON pivot_terms(term,concept)')


def tokens(text):
    return set(re.findall(r'[a-z]{3,}',text.casefold()))-{'the','and','for','with','from','that','this','type','used','use'}


class Pivot:
    def __init__(self,con,config):
        self.con=con;self.config=config;self.cache=OrderedDict()

    def concept(self,uid):
        if uid not in self.cache:
            record=json.loads(self.con.execute('SELECT payload FROM concepts WHERE id=?',(uid,)).fetchone()[0])
            self.cache[uid]=record
            if len(self.cache)>512:self.cache.popitem(last=False)
        else:self.cache.move_to_end(uid)
        return self.cache[uid]

    def find(self,uid,records,source_domains):
        meanings=[item for r in records for item in lexemes(r)]
        targets={};truncated=len(meanings)>64
        for item in meanings[:64]:
            matches=list(self.con.execute('SELECT DISTINCT concept,kind,original FROM pivot_terms WHERE term=? AND concept!=? ORDER BY concept,kind,original LIMIT 65',(item['term'],uid)))
            truncated|=len(matches)>64
            for row in matches[:64]:
                if row['concept'] not in targets and len(targets)>=128:
                    truncated=True;continue
                targets.setdefault(row['concept'],[]).append(dict(source=item,target_kind=row['kind'],target_original=row['original']))
        source_zh={normalize(v) for r in records for v in variants(r,'zh')}
        source_parents={tuple(p) for r in records for p in r['relations']}
        source_tokens=tokens(' '.join(v for r in records for v in [*r['definitions'],*r['descriptions'].values()]))
        for target_id,matches in sorted(targets.items()):
            target=self.concept(target_id);target_records=target['records']
            russian=sorted({preferred(r['labels'],'ru') for r in target_records}-{''})
            if not russian:continue
            if 'classification' not in target:
                target['classification']=classify(self.con,target_id,target_records,self.config)
            target_domains,excluded,exhausted=target['classification']
            shared_zh=sorted(source_zh & {normalize(v) for r in target_records for v in variants(r,'zh')})
            shared_parents=sorted(source_parents & {tuple(p) for r in target_records for p in r['relations']})
            shared_domains=sorted(set(source_domains)&set(target_domains)-{'unclassified'})
            text=' '.join(v for r in target_records for v in [*r['descriptions'].values(),*r['definitions']])
            definition_overlap=sorted(source_tokens & tokens(text))
            ambiguous=len(targets)!=1 or len(russian)!=1 or truncated
            detail=dict(version=2,target=target_id,english_matches=matches,shared_zh=shared_zh,
                        shared_parents=shared_parents,shared_domains=shared_domains,definition_token_overlap=definition_overlap,
                        target_domain_evidence=target_domains,competing_concepts=sorted(targets),retrieval_truncated=truncated,
                        quality_tier='REVIEW_HIGH' if shared_zh and not ambiguous else 'REVIEW_AMBIGUOUS',
                        note='English/definition evidence is supporting only; no automatic pivot verification.')
            domains=source_domains if set(source_domains)-{'unclassified'} else {
                domain:[dict(kind='pivot_target_domain_review_only',target=target_id)] for domain in target_domains}
            if not domains:domains={'unclassified':[dict(kind='no_technical_evidence')]}
            yield target_id,target_records,russian,domains,excluded,exhausted,ambiguous,detail
