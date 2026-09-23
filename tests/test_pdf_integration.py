"""Optional real-model PDF coverage; regular fixtures never need model weights."""
from hashlib import sha256
from pathlib import Path
import socket

from tools.pdf_fixtures import make_pdf
import pypdfium2 as pdfium

def extract(path):
    with pdfium.PdfDocument(path) as doc:
        page = doc[0]
        tp = page.get_textpage()
        value = tp.get_text_range()
        tp.close()
        page.close()
        return value

import pytest

from app.documents.control import JobControl
from app.documents.docx_document import validate_docx
from app.documents.job import DocumentConfig, DocumentJob
from app.documents.scanner import scan_sources
from app.engine.factory import create_translation_engine
from app.engine.types import DevicePreference, PerformanceProfile

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def engine():
    if not all((Path('vendor/models') / p).is_file() for p in (
        'argos/argos-en-ru/model/model.bin', 'm2m100-418m-int8/model/model.bin')):
        pytest.skip('Prepared local Argos/M2M100 models are absent')
    engine = create_translation_engine()
    yield engine
    engine.shutdown()


@pytest.mark.parametrize('device', list(DevicePreference))
@pytest.mark.parametrize('text,language', [('Save the configuration file before restarting the application.', 'en'),
                                         ('请在重新启动应用程序之前保存配置文件。', 'zh')])
def test_real_pdf(engine, tmp_path, device, text, language, monkeypatch):
    if device == DevicePreference.GPU and not engine.devices.gpu_available():
        pytest.skip('No CUDA device')
    path = make_pdf(tmp_path / '原文.pdf', text, pages=2, lines=3)
    digest = sha256(path.read_bytes()).hexdigest()
    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('Network attempted')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    control = JobControl()
    requests, resolved = [], []
    def translate(request, cancelled):
        requests.append(request)
        return engine.translate(request, cancelled)
    def resolve(text, source, target):
        pair = engine.languages.resolve(text, source, target)
        resolved.append(pair)
        return pair
    progress = []
    with engine.runtime.keep_warm():
        output, = DocumentJob(scan_sources([path], control).files,
                              DocumentConfig(device=device, profile=PerformanceProfile.BALANCED), control,
                              translate, resolve, progress.append).run()
    assert resolved == [(language, 'ru')]
    assert all(r.source_language == language for r in requests)
    assert sha256(path.read_bytes()).hexdigest() == digest
    assert not attempts
    result = extract(output)
    assert text not in result
    assert any('а' <= c.lower() <= 'я' for c in result)
    assert progress[-1].percent == 100
