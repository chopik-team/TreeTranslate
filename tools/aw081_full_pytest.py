"""Run the complete suite once with reproducible command/state evidence."""
import json
import argparse
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw081_large_zip import production_hashes
from app.documents.run_metrics import file_hash

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'qa/aw081/iterations/14_phase_a_closure/full_pytest')
QA=parser.parse_args().output.resolve()
QA.mkdir(exist_ok=False)
command=[sys.executable,'-X','utf8','-m','pytest','-q','--junitxml='+str(QA/'junit.xml')]
before=production_hashes()
git={}
for name,args in [('head',['rev-parse','HEAD']),('status',['status','--porcelain=v1','-z']),('diff-stat',['diff','--stat']),('diff',['diff','--binary']),('staged-diff',['diff','--cached','--binary'])]:
    result=subprocess.run(['git',*args],cwd=ROOT,capture_output=True)
    (QA/('git-'+name+'.txt')).write_bytes(result.stdout)
    git[name]=dict(returncode=result.returncode,sha256=file_hash(QA/('git-'+name+'.txt')))
started=perf_counter()
with (QA/'stdout.txt').open('w',encoding='utf8') as stdout,(QA/'stderr.txt').open('w',encoding='utf8') as stderr:
    result=subprocess.run(command,cwd=ROOT,stdout=stdout,stderr=stderr)
after=production_hashes()
report=dict(command=command,cwd=str(ROOT),returncode=result.returncode,seconds=perf_counter()-started,
            git=git,production_hashes_before=before,production_hashes_after=after,production_unchanged=before==after,
            evidence_hashes={p.name:file_hash(p) for p in QA.iterdir() if p.is_file()})
(QA/'execution.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(result.returncode,report['seconds'],report['production_unchanged'])
raise SystemExit(result.returncode)
