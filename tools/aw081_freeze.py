"""Freeze unseen whole-document evaluation before any AW0.81 production fix."""
from collections import Counter,defaultdict
from hashlib import sha256
import json,shutil,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.knowledge.profile import DocumentProfiler
QA=ROOT/'qa/aw081';PREVIOUS=ROOT/'qa/aw088'
QA.mkdir(parents=True,exist_ok=True)
def save(name,value):(QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')
def read(path):return json.loads(path.read_text('utf8'))

def freeze():
    path=QA/'final_holdout_manifest.json'
    if path.exists():print('Already frozen');return
    held=read(PREVIOUS/'frozen_holdout_manifest.json');development=read(PREVIOUS/'development_manifest.json')
    previous=read(PREVIOUS/'representative_holdout.json')['documents']
    old_groups={d['group'] for d in previous};dev_groups={d['group'] for d in development['documents']}
    allowed={d['member']:d for d in held['documents'] if d['group'] not in old_groups}
    families={
      'restraint':['airbag','空气囊','安全带','pretensioner','拉紧器','srs'],
      'steering':['steering','转向柱','转向系统','方向盘','转向齿轮箱'],
      'fuel_emissions':['fuel','燃油','排放控制','emission','oxygen','催化','purge','egr'],
      'hvac':['hvac','空调','heating','heater','blower','compressor','ventilation']}
    profiler=DocumentProfiler();pools=defaultdict(list)
    with sqlite3.connect(PREVIOUS/'native_corpus.db') as con:
        for member,digest,_,raw in con.execute('SELECT * FROM documents'):
            if member not in allowed:continue
            data=json.loads(raw);lines=data.get('lines',[])
            if not 1<=data.get('pages',0)<=4 or not 120<=sum(map(len,lines))<=2800:continue
            item=allowed[member];p=profiler.profile('zh','ru',segments=lines,filename=member,folders=(member,))
            scopes=dict(p.subdomains);branch=max(scopes,key=scopes.get).split('.',1)[-1] if scopes else 'common_service'
            branch=branch.split('.')[0];branch=branch if branch in {'engine','transmission','brakes','suspension','electrical','diagnostics','hvac','body'} else 'common_service'
            for family,cues in families.items():
                if any(cue in member.lower() for cue in cues):branch=family;break
            normalized='\n'.join(' '.join(line.split()) for line in lines)
            record=dict(member=member,sha256=digest,normalized_text_sha256=sha256(normalized.encode()).hexdigest(),
                domain=p.primary_domain,subdomains=list(scopes),stratum=branch,pages=data['pages'],group=item['group'],
                semantic_segments=sum(bool(__import__('re').search('[\u4e00-\u9fff]',line)) for line in lines))
            pools[branch].append(record)
    selected=[];used=set()
    for branch in ['engine','transmission','brakes','suspension','electrical','diagnostics','hvac','body','restraint','fuel_emissions','steering','common_service']:
        added=0
        for d in sorted(pools[branch],key=lambda d:sha256(('aw081-A:'+d['group']).encode()).hexdigest()):
            if d['group'] in used:continue
            selected.append(d);used.add(d['group']);added+=1
            if added>=4:break
        assert added>=1,(branch,added)
    assert len(selected)>=30 and not used & (old_groups|dev_groups)
    baseline=QA/'baseline';baseline.mkdir(exist_ok=True);hashes={}
    for p in [ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db',*sorted((ROOT/'assets/config').glob('*.json'))]:
        hashes[str(p.relative_to(ROOT))]=sha256(p.read_bytes()).hexdigest();shutil.copy2(p,baseline/p.name)
    save(path.name,dict(set_id='FINAL_HOLDOUT_A',frozen_before_first_fix=True,documents=selected,
        development_manifest_sha256=sha256((PREVIOUS/'development_manifest.json').read_bytes()).hexdigest(),
        native_cache_sha256=sha256((PREVIOUS/'native_corpus.db').read_bytes()).hexdigest(),
        baseline_hashes=hashes,selection='Deterministic stratified whole PDFs, four unique text groups per major family; former diagnostic text groups excluded',
        strata=dict(Counter(d['stratum'] for d in selected)),semantic_segments=sum(d['semantic_segments'] for d in selected)))
    save('diagnostic_before.json',dict(set_id='DIAGNOSTIC_REGRESSION_SET',
        source_file=str(PREVIOUS/'holdout_semantic_review.json'),sha256=sha256((PREVIOUS/'holdout_semantic_review.json').read_bytes()).hexdigest(),
        immutable_old_set=True,**read(PREVIOUS/'holdout_semantic_review.json')))
    save('holdout_rotation_log.json',dict(sets=[dict(set_id='FINAL_HOLDOUT_A',status='FROZEN_UNSEEN',
        manifest=str(path),sha256=sha256(path.read_bytes()).hexdigest())],diagnostic_old_set='DIAGNOSTIC_REGRESSION_SET'))
    save('knowledge_before.json',read(PREVIOUS/'knowledge_after.json'))
    print('FROZEN',len(selected),'whole PDFs',sum(d['semantic_segments'] for d in selected),'semantic lines',Counter(d['stratum'] for d in selected),flush=True)

if __name__=='__main__':freeze()
