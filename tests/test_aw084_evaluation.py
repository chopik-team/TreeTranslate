"""Fault checks for the isolated evaluation; no candidate enters production."""
import ast
import hashlib
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from app.engine.errors import ModelCorruptedError,ModelMissingError,TranslationCancelledError
from app.engine.runtime.model_manager import ModelManager
from app.engine.types import InferenceOptions,PairKind,TranslationRequest
from tools import aw084_backend as qa


@pytest.fixture
def candidate(tmp_path,monkeypatch):
    monkeypatch.setattr(qa,'ROOT',tmp_path)
    root=tmp_path/'build/aw084/candidates';folder=root/'m2m100-1.2b';folder.mkdir(parents=True)
    (tmp_path/'qa/aw084').mkdir(parents=True)
    (folder/'model.bin').write_bytes(b'qa model')
    files=[{'path':'model.bin','size':8,'sha256':hashlib.sha256(b'qa model').hexdigest()}]
    row=dict(id='m2m100-1.2b',backend='m2m100',path='m2m100-1.2b',version='pinned',source='local',
             languages=['zh','ru','en','de','fr','es','ja'],pairs=[],format='ctranslate2',
             quantization='int8',license='MIT',size=8,files=files)
    (root/'models_manifest.json').write_text(json.dumps({'schema_version':1,'models':[row]}),'utf-8')
    (tmp_path/'qa/aw084/m2m100-1.2b-prepared.json').write_text(json.dumps({'converted_files':files}),'utf-8')
    return qa.CandidateBackend('m2m100-1.2b')


def test_candidate_manifest_and_checksum(candidate):
    assert candidate.models.validate(candidate.record,full=True)==candidate.root
    (candidate.root/'model.bin').write_bytes(b'badmodel')
    with pytest.raises(ModelCorruptedError):candidate.models.validate(candidate.record,full=True)


def test_candidate_missing_file(candidate):
    (candidate.root/'model.bin').unlink()
    with pytest.raises(ModelMissingError):candidate.models.validate(candidate.record)


@pytest.mark.parametrize('device,compute',[('cpu','int8'),('cuda','int8_float16')])
def test_adapter_load_reuse_and_unload(candidate,monkeypatch,device,compute):
    import ctranslate2
    import app.engine.backends.m2m100_tokenizer as tokens
    loads=[];unloads=[]
    def translator(path,**kwargs):
        loads.append(kwargs)
        return SimpleNamespace(unload_model=lambda **kw:unloads.append(kw))
    monkeypatch.setattr(ctranslate2,'Translator',translator)
    monkeypatch.setattr(qa,'LocalM2M100Tokenizer',lambda p:object())
    options=InferenceOptions(device,compute,8,4,2048,384,512)
    candidate._load(options);candidate._load(options)
    assert len(loads)==1 and loads[0]['device']==device and loads[0]['compute_type']==compute
    candidate.shutdown()
    assert unloads==[{'to_cpu':False}] and candidate._translator is None


def test_cancel_never_loads_model(candidate,monkeypatch):
    monkeypatch.setattr(candidate,'_load',lambda _:pytest.fail('loaded after cancel'))
    event=Event();event.set()
    with pytest.raises(TranslationCancelledError):
        candidate.translate(TranslationRequest('测量点','zh','ru'),PairKind.DIRECT,
            InferenceOptions('cpu','int8',8,4,2048,384,512),event)


def test_candidate_languages_use_existing_contract(candidate):
    for source,target in [('zh','ru'),('ru','zh'),('en','de'),('ja','en')]:
        assert candidate.supports_pair(source,target)
    assert not candidate.supports_pair('xx','ru')
    assert not candidate.supports_pair('ru','ru')


def test_production_cannot_import_evaluation_or_dev_dependencies():
    for path in Path('app').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text('utf-8'))):
            if isinstance(node,ast.Import):names=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom):names=[node.module or '']
            else:continue
            assert not any(n.split('.')[0] in {'torch','transformers','huggingface_hub'} or n.startswith('tools.aw084') for n in names),path


def test_gold_is_not_imported_by_application():
    for path in Path('app').rglob('*.py'):
        text=path.read_text('utf-8')
        assert 'engine_semantic_gold' not in text and 'semantic_gold.json' not in text,path


def test_router_can_fallback_to_existing_418_contract():
    from test_router import FakeBackend,FakeDevices
    from app.engine.router.translation_router import TranslationRouter
    from app.engine.router.route_decision import RouteDecision,RouteCandidate
    from app.engine.types import DevicePreference,PerformanceProfile
    bad=FakeBackend('candidate',languages=['zh','ru']);bad.fail={'cpu','cuda'}
    baseline=FakeBackend('m2m100-418m',languages=['zh','ru'])
    router=TranslationRouter({'candidate':bad,'baseline':baseline},devices=FakeDevices())
    # QA-only route injection tests the existing fallback mechanism, without
    # introducing an unapproved candidate route in production.
    router.decide=lambda *_:RouteDecision('candidate','QA candidate',
        (RouteCandidate('baseline',PairKind.DIRECT),),'cpu',PerformanceProfile.AUTOMATIC,PairKind.DIRECT)
    try:
        result=router.translate(TranslationRequest('检查测量点。','zh','ru',DevicePreference.CPU))
        assert result.backend=='baseline' and result.fallback_used
        assert result.model_ids==('m2m100-418m-test',)
    finally:router.shutdown()
