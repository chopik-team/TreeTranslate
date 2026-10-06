"""One-time mechanical extraction of existing job stages; not a runtime tool."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def change_job():
    path=ROOT/'app/documents/job.py'
    code=path.read_text('utf8')
    code=code.replace('    def _run_documents(self):\n', '''    def _run_documents(self):
        # The serial path consumes the same stage implementation as the
        # archive pipeline. Translation, guards and writer remain unchanged.
        for _ in self._document_stages():
            pass
        return tuple(self.completed)

    def _document_stages(self):
''',1)
    code=code.replace('        router = OcrRouter(checkpoint=', '        router_factory = getattr(self, "_pipeline_router_factory", OcrRouter)\n        router = router_factory(checkpoint=',1)
    anchor="                logger.info('run=%s source=%s bytes=%d sha256=%s pages=%d segments=%d chars=%d native_segments=%d ocr_segments=%d', self.run_id,"
    assert code.count(anchor)==1
    code=code.replace(anchor,"                if getattr(self, '_pipeline_active', False):\n                    self._prepared_document = doc\n                    yield 'prepared'\n"+anchor,1)
    code=code.replace('                del doc\n', "                if not getattr(self, '_pipeline_active', False):\n                    del doc\n",1)
    anchor="            with timed_stage('reopen_cached_extraction'):\n                doc = open_document(item.path, self.control, self.config.pdf_limits, extractor)"
    assert code.count(anchor)==1
    code=code.replace(anchor,"            if getattr(self, '_pipeline_active', False):\n                doc = self._prepared_document\n            else:\n                with timed_stage('reopen_cached_extraction'):\n                    doc = open_document(item.path, self.control, self.config.pdf_limits, extractor)",1)
    anchor='            destination = self._destination(item, source, target)\n'
    assert code.count(anchor)==1
    code=code.replace(anchor,anchor+"            if getattr(self, '_pipeline_active', False):\n                self._pipeline_source_target = (source, target)\n                observe('semantic_complete', getattr(self.translate, '__self__', None))\n                yield 'translated'\n",1)
    ast.parse(code)
    path.write_text(code,'utf8')

def change_metrics():
    path=ROOT/'app/documents/run_metrics.py'
    code=path.read_text('utf8').replace('from functools import wraps','from functools import wraps\nfrom threading import RLock',1)
    anchor='class LocalRun:\n'
    code=code.replace(anchor,'''def serialized_metrics(method):
    """One storage owner at a time; document ContextVars remain task-local."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._storage_lock:
            return method(self, *args, **kwargs)
    return call


class LocalRun:
''',1)
    code=code.replace('        self.run_id=run_id or uuid4().hex\n', '        self._storage_lock = RLock()\n        self.run_id=run_id or uuid4().hex\n',1)
    code=code.replace("sqlite3.connect(self.directory/'index.sqlite3')", "sqlite3.connect(self.directory/'index.sqlite3', check_same_thread=False)",1)
    tree=ast.parse(code)
    klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LocalRun')
    for method in klass.body:
        if isinstance(method,ast.FunctionDef) and method.name not in {'__init__','activate'}:
            marker='    def '+method.name+'('
            code=code.replace(marker,'    @serialized_metrics\n'+marker,1)
    marker='    @serialized_metrics\n    def complete_document('
    code=code.replace(marker,'''    @serialized_metrics
    def semantic_complete(self, engine=None):
        doc = _doc.get()
        contextual = getattr(engine, 'context_router', None)
        if doc and contextual:
            doc.engine_after = dict(contextual.metrics)

'''+marker,1)
    code=code.replace('            values=contextual.metrics\n', "            values=getattr(doc, 'engine_after', None) or dict(contextual.metrics)\n",1)
    ast.parse(code)
    path.write_text(code,'utf8')

if __name__=='__main__':
    change_job()
    change_metrics()
    print('Extracted unchanged stages and serialized diagnostics')
