from threading import Condition, Event
from time import monotonic

from app.engine.errors import TranslationCancelledError


class JobControl:
    """Cooperative pause/cancel. Publication and cancellation serialize on one lock."""

    def __init__(self):
        self.cancelled = Event()
        self._condition = Condition()
        self._paused = False
        self._pause_started = 0.0
        self._paused_seconds = 0.0
        self.started = monotonic()

    def pause(self):
        with self._condition:
            if not self._paused:
                self._paused = True
                self._pause_started = monotonic()

    def resume(self):
        with self._condition:
            if self._paused:
                self._paused_seconds += monotonic() - self._pause_started
                self._paused = False
            self._condition.notify_all()

    def cancel(self):
        with self._condition:
            self.cancelled.set()
            self._condition.notify_all()

    def checkpoint(self):
        with self._condition:
            while self._paused and not self.cancelled.is_set():
                self._condition.wait()
            if self.cancelled.is_set():
                raise TranslationCancelledError()

    def publish(self, action):
        with self._condition:
            self.checkpoint()
            return action()

    @property
    def elapsed(self):
        return monotonic() - self.started

    @property
    def active_seconds(self):
        with self._condition:
            paused = self._paused_seconds + (monotonic() - self._pause_started if self._paused else 0)
            return max(0.0, self.elapsed - paused)
