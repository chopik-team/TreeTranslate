from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
from logging.handlers import RotatingFileHandler

from app.config.paths import LOGS_DIR
from app.documents.run_metrics import stage_observed


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure private local logs; document contents must never be logged."""
    logger = logging.getLogger("treetranslate")
    logger.setLevel(level)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    for target, name in ((logger, 'treetranslate.log'),
                         (logging.getLogger('treetranslate.documents'), 'documents.log')):
        target.setLevel(level)
        if any(getattr(handler, '_treetranslate_local', False) for handler in target.handlers):
            continue
        handler = RotatingFileHandler(LOGS_DIR / name, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler._treetranslate_local = True
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s'))
        target.addHandler(handler)
    logger.propagate = False
    return logger


_run_id = ContextVar('document_run_id', default='standalone')
timing_logger = logging.getLogger('treetranslate.documents.timing')


def current_document_run():
    return _run_id.get()


@contextmanager
def document_run(run_id):
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


@contextmanager
def timed_stage(stage, page=None, block=None):
    """Inclusive wall time; nested entries must not be added to their parent."""
    started = perf_counter()
    state = 'ok'
    timing_logger.info('run=%s process=%s event=start page=%s block=%s', _run_id.get(), stage, page, block)
    try:
        yield
    except BaseException as error:
        state = type(error).__name__
        raise
    finally:
        elapsed = perf_counter() - started
        stage_observed(stage, elapsed, state, page, block)
        timing_logger.info('run=%s process=%s event=end page=%s block=%s seconds=%.4f state=%s',
                    _run_id.get(), stage, page, block, elapsed, state)


def timed_process(stage, page_index_arg=None):
    def decorate(method):
        @wraps(method)
        def call(*args, **kwargs):
            token = _run_id.set(getattr(args[0], 'run_id', _run_id.get())) if args else None
            page = (args[page_index_arg] + 1 if page_index_arg is not None
                    and len(args) > page_index_arg else None)
            try:
                with timed_stage(stage, page):
                    return method(*args, **kwargs)
            finally:
                if token is not None:
                    _run_id.reset(token)
        return call
    return decorate
