"""One active + one latest pending lookup; dictionaries load off the GUI thread."""
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, Signal, Slot

from app.services.lexical_assistance import LexicalAssistance


class LexicalWorker(QObject):
    ready = Signal(object)
    _finished = Signal(object)

    def __init__(self, parent=None, lexicon=None):
        super().__init__(parent)
        self.lexicon = lexicon or LexicalAssistance()
        self._executor = None
        self._active = False
        self._pending = None
        self._closed = False
        self._finished.connect(self._complete, Qt.ConnectionType.QueuedConnection)

    def submit(self, ticket, word, source, target, *, spelling=False, suggestion_word=None):
        if self._closed:
            return
        self._pending = ticket, word, source, target, spelling, suggestion_word
        if not self._active:
            self._dispatch()

    def _dispatch(self):
        request, self._pending = self._pending, None
        self._active = True
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lexicon")
        def work():
            ticket, word, source, target, spelling, suggestion_word = request
            reference = self.lexicon.reference(word, source, target)
            suggestions = self.lexicon.suggest(suggestion_word or word, source) if spelling else ()
            return ticket, reference, suggestions
        def done(future):
            if not self._closed:
                # Never log text, lookup terms or native exception messages.
                try:
                    result = future.result()
                except Exception:
                    result = request[0], None, ()
                self._finished.emit(result)
        self._executor.submit(work).add_done_callback(done)

    @Slot(object)
    def _complete(self, result):
        self._active = False
        if self._closed:
            return
        self.ready.emit(result)
        if self._pending:
            self._dispatch()

    def shutdown(self):
        self._closed = True
        self._pending = None
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
