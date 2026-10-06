"""Restore precisely the pre-project bytes, proving every file by baseline SHA."""
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from tools.aw081_nmt_batch_scheduler_5pdf import ROOT, QA, read, save, frozen_hashes


def run():
    assert not (QA/'rollback.json').exists(),'Baseline already restored; rollback is a one-shot operation'
    baseline=read(QA/'baseline.json')['production_before']
    paths=['app/documents/job.py','app/documents/run_metrics.py',
           'app/engine/runtime/runtime_manager.py','app/engine/backends/m2m100_backend.py']
    texts={p:(ROOT/p).read_text('utf8') for p in paths}
    patches=[]
    for call in read(QA/'patch_calls.json'):
        for match in re.finditer(r'tools\.apply_patch\(("(?:[^"\\]|\\.)*")\)',call):
            patches.append(json.loads(match[1]))
    for patch in reversed(patches):
        for part in re.split(r'\*\*\* (?:Update|Add) File: ',patch)[1:]:
            header,*lines=part.splitlines()
            relative=Path(header).relative_to(ROOT).as_posix()
            if relative not in texts or relative.endswith('/job.py'):continue
            hunks=[];hunk=[]
            for line in lines:
                if line.startswith('@@') or line.startswith('***'):
                    if hunk:hunks.append(hunk);hunk=[]
                elif line[:1] in {' ','+','-'}:hunk.append(line)
            if hunk:hunks.append(hunk)
            for hunk in reversed(hunks):
                old='\n'.join(x[1:] for x in hunk if x[:1]!='+')+'\n'
                new='\n'.join(x[1:] for x in hunk if x[:1]!='-')+'\n'
                assert texts[relative].count(new)==1,(relative,new)
                texts[relative]=texts[relative].replace(new,old,1)
    s=texts['app/documents/job.py']
    a=s.index('            def translate_segment(segment):\n')
    b=s.index("            self.control.checkpoint()\n            update(stage='WRITING')",a)
    prefix=s[a:b].split('            def translate_segment(segment):\n',1)[1]
    before,body=prefix.split('                    try:\n',1)
    body=body.split('                    finally:\n',1)[0]
    original='            for segment in doc.segments:\n'+before
    original+='\n'.join(line[4:] for line in body.splitlines())+'\n'
    original+='''                if file_done:
                    durations.append(max(0, self.control.active_seconds - started))
                file_done += 1
                done += 1
                update()
'''
    texts['app/documents/job.py']=s[:a]+original+s[b:]
    restored={}
    for relative,text in texts.items():
        expected=baseline[relative.replace('/','\\')]
        choices=[text.encode('utf8'),text.replace('\n','\r\n').encode('utf8')]
        matching=[data for data in choices if hashlib.sha256(data).hexdigest()==expected]
        assert matching,('Cannot prove exact baseline restoration',relative)
        restored[relative]=matching[0]
    prototype=ROOT/'app/engine/runtime/nmt_batch_scheduler.py'
    tests=ROOT/'tests/test_nmt_batch_scheduler.py'
    with ZipFile(QA/'rejected_prototype.zip','x',compression=ZIP_DEFLATED) as out:
        for relative in [*paths,'app/engine/runtime/nmt_batch_scheduler.py','tests/test_nmt_batch_scheduler.py']:
            out.write(ROOT/relative,relative)
        out.writestr('targeted_tests.json',json.dumps(dict(status='PASS',passed=51,failures=0,errors=0,duration_seconds=33.20,
            scheduler_tests=20,existing_runtime_pipeline_tests=31,scope='Prototype protocol tests before rollback; real native replay FAILED'),indent=2))
    for relative,data in restored.items():(ROOT/relative).write_bytes(data)
    assert 'app\\engine\\runtime\\nmt_batch_scheduler.py' not in baseline
    prototype.unlink();tests.unlink()  # Only these two new task-owned, archived files.
    assert frozen_hashes()==baseline,'Production must exactly equal measured baseline'
    save(QA/'rollback.json',dict(status='PASS',production_exact_baseline=True,restored_files=paths,
        rejected_prototype='rejected_prototype.zip',production_hashes=frozen_hashes()))
    (QA/'patch_calls.json').unlink()
    print('EXACT BASELINE RESTORED: all production hashes match',flush=True)


if __name__=='__main__':run()
