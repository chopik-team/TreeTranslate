"""Own one isolated Paddle runtime; never import Paddle into the translation process."""
from pathlib import Path
from queue import Queue, Empty
import json
import os
import subprocess
import tempfile
from threading import Thread, RLock, Timer
from time import monotonic

from app.config.paths import PROJECT_ROOT as ROOT_DIR
from app.ocr.config import configuration
from app.ocr.errors import OcrError


class OcrRuntimeManager:
    def __init__(self, python=None, checkpoint=lambda: None):
        self.python = Path(python or ROOT_DIR / '.venv-ocr/Scripts/python.exe')
        self.checkpoint = checkpoint
        self.process = None
        self._lock = RLock()
        self._timer = None
        self._device = None

    def _start(self, device):
        if not self.python.is_file():
            raise OcrError('runtime')
        environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        if device == 'cpu':
            environment['CUDA_VISIBLE_DEVICES'] = ''
        self._device = device
        self.process = subprocess.Popen([str(self.python), '-m', 'app.ocr.runtime.worker'],
            cwd=ROOT_DIR, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self._replies = Queue()
        stream = self.process.stdout
        replies = self._replies
        def reader():
            try:
                for line in stream:
                    if len(line) > 16_000_000:
                        replies.put({'error': 'limit'})
                        break
                    replies.put(json.loads(line))
            except (ValueError, OSError):
                pass
            finally:
                replies.put({'error': 'runtime'})
        Thread(target=reader, daemon=True, name='ocr-protocol').start()

    def run(self, image, command):
        with self._lock:
            self.checkpoint()
            if self._timer:
                self._timer.cancel()
            if self.process and self._device != command['device']:
                self.shutdown()
            if not self.process or self.process.poll() is not None:
                self._start(command['device'])
            with tempfile.TemporaryDirectory(prefix='treetranslate-ocr-') as directory:
                path = Path(directory) / 'region.png'
                image.save(path)
                if path.stat().st_size > configuration()['limits']['temp_bytes']:
                    raise OcrError('limit')
                self.process.stdin.write(json.dumps(dict(command, op='recognize', image=str(path))) + '\n')
                self.process.stdin.flush()
                deadline = monotonic() + configuration()['runtime']['timeout_seconds']
                # Cancellation/pause is cooperative at native-call boundaries. Do
                # not kill a CUDA call or remove its input while it is executing.
                while True:
                    try:
                        result = self._replies.get(timeout=.1)
                        break
                    except Empty:
                        if monotonic() > deadline:
                            self.shutdown(force=True)
                            raise OcrError('timeout')
                self.checkpoint()
                if 'error' in result:
                    raise OcrError(result['error'])
                self._timer = Timer(configuration()['runtime']['idle_seconds'], self.shutdown)
                self._timer.daemon = True
                self._timer.start()
                return result

    def shutdown(self, force=False):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            process, self.process = self.process, None
            if process:
                try:
                    if process.poll() is None:
                        if not force:
                            process.stdin.write('{"op":"shutdown"}\n')
                            process.stdin.flush()
                            process.wait(timeout=15)
                        else:
                            process.terminate()
                    process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait()
                finally:
                    process.stdin.close()
                    process.stdout.close()
