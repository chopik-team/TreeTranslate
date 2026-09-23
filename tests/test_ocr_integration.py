"""Real models only: no fake success when local artifacts are absent."""
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image,ImageDraw,ImageFont
import pytest

from app.ocr.router.ocr_router import OcrRouter
from app.ocr.runtime.ocr_runtime_manager import OcrRuntimeManager
from app.ocr.types import OcrRequest

pytestmark=pytest.mark.integration


@pytest.fixture(scope='module')
def runtime():
    if not Path('.venv-ocr/Scripts/python.exe').is_file() or not Path('vendor/models/ocr/models_manifest.json').is_file():
        pytest.skip('Prepared local Paddle runtime/models absent')
    runtime=OcrRuntimeManager()
    yield runtime
    runtime.shutdown()


@pytest.mark.parametrize('device',['cpu','gpu','auto'])
def test_real_ocr_devices_offline(runtime,device):
    image=Image.new('RGB',(900,180),'white')
    ImageDraw.Draw(image).text((20,40),'Engine GDS ITM IVT 6.6 45-60',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',36),fill='black')
    router=OcrRouter(runtime=runtime)
    result=router.recognize(OcrRequest(image,source_language='en',device_preference=device,performance_profile='fast'))
    assert 'GDS ITM IVT 6.6 45-60' in ' '.join(s.text for s in result.segments)
    assert result.device==('gpu' if device in ('gpu','auto') else 'cpu')
    assert result.timings['network_attempts']==0


def test_process_network_guard(runtime):
    process=subprocess.run([str(runtime.python),'-m','app.ocr.runtime.worker'],
        input=json.dumps({'op':'network_test'})+'\n',capture_output=True,text=True,timeout=15)
    assert json.loads(process.stdout)['error']=='network'


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_real_orientation_coordinates(runtime,angle):
    image=Image.new('RGB',(900,300),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32)
    for y,text in [(20,'Engine configuration guide'),(85,'Save the file before restarting.'),(150,'GDS ITM IVT 6.6')]:
        draw.text((40,y),text,font=font,fill='black')
    image=image.rotate(angle,expand=True)
    result=OcrRouter(runtime=runtime).recognize(OcrRequest(image,source_language='en',device_preference='gpu'))
    assert 'GDS' in ' '.join(s.text for s in result.segments)
    assert all(0<=s.bbox[0]<s.bbox[2]<=image.width and 0<=s.bbox[1]<s.bbox[3]<=image.height for s in result.segments)
    assert result.segments[0].angle==(-angle)%360


def test_auto_cyrillic(runtime):
    image=Image.new('RGB',(1000,200),'white')
    ImageDraw.Draw(image).text((20,50),'Сохраните файл перед запуском',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',40),fill='black')
    result=OcrRouter(runtime=runtime).recognize(OcrRequest(image,source_language='auto',device_preference='gpu'))
    assert 'Сохраните файл' in ' '.join(s.text for s in result.segments)
    assert all('cyrillic' in s.model_id for s in result.segments)
