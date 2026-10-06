"""Suite B: replay frozen segments through unchanged production components."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.aw084_backend import backend
from app.engine.factory import create_translation_engine
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.engine import TranslationMemoryEngine
from app.documents.job import DocumentJob,DocumentConfig
from app.documents.control import JobControl
from app.documents.pdf_fidelity import FidelityMismatch
from app.engine.types import DevicePreference


def create(model):
    folder=ROOT/'build/aw084'/model;folder.mkdir(exist_ok=True)
    engine=create_translation_engine(memory=TranslationMemoryEngine(folder/'tm.db'),
        glossary=GlossaryEngine(folder/'glossary.db',builtin_paths=bundled_paths()))
    if model!='m2m100-418m':
        engine.router.backends['m2m100']=backend(model)
    if model=='madlad-3b':
        from app.engine.runtime.device_manager import DeviceManager
        class CandidateDevices(DeviceManager):
            def options(self,device,policy):
                rows=super().options(device,policy)
                return tuple(r for r in rows if r.compute_type=='int8_float32') if device=='cuda' else rows
        engine.router.devices=CandidateDevices()
    return engine


def main():
    parser=argparse.ArgumentParser();parser.add_argument('model');args=parser.parse_args()
    engine=create(args.model)
    job=DocumentJob([],DocumentConfig(source='zh',target='ru',domain='automotive',device=DevicePreference.GPU),
                    JobControl(),engine.translate,engine.languages.resolve)
    source=json.loads((ROOT/'qa/aw083/accepted_segments.json').read_text('utf-8'))
    rows=[];started=time.perf_counter()
    try:
        with engine.runtime.keep_warm():
            for document in source['documents']:
                for segment in document['segments']:
                    begin=time.perf_counter();text=segment['text'];reason=''
                    try:
                        if segment['origin']=='ocr' and segment['ocr_kind'] in {'noise','identifier','measurement'}:
                            translated=text;reason=segment['ocr_kind']
                        else:
                            translated=job._pdf_translation(text,'zh','ru')
                    except FidelityMismatch as error:
                        translated=text;reason='guard:'+str(error)
                    rows.append({'file':document['file'],'page':segment['page'],'block_id':segment['block_id'],
                        'source':text,'text':translated,'reason':reason,'seconds':time.perf_counter()-begin,
                        'accepted_083':segment['translated'],'origin':segment['origin']})
                print(args.model,document['file'],len(rows),flush=True)
    finally:
        engine.shutdown()
        (ROOT/'qa/aw084'/f'{args.model}-production.json').write_text(json.dumps({'model':args.model,'rows':rows,
            'seconds':time.perf_counter()-started,'suite':'frozen segmentation; real Knowledge/DocumentJob/guards; placement evaluated only in suite C'},
            ensure_ascii=False,indent=2)+'\n','utf-8')


if __name__=='__main__':main()
