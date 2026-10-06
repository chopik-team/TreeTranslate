"""Safe native context. Never include exception messages or document strings."""
from contextlib import contextmanager
import logging
import json
from functools import lru_cache
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from app.documents.pdf_types import PdfError, PdfKind

from app.config.logging_config import timed_process, timed_stage, current_document_run

logger = logging.getLogger('treetranslate.documents.pdf')

@lru_cache(maxsize=1)
def known_layout_registry():
    from app.config.paths import ASSETS_DIR
    path=ASSETS_DIR/'config/pdf-known-layout-warnings.json'
    return json.loads(path.read_text('utf8')).get('documents',{}) if path.exists() else {}

def known_layout_findings(source_hash):
    return known_layout_registry().get(source_hash,[])


def context(stage, operation, page=None, object_index=None, object_type=None, native_code=None):
    return dict(stage=stage, operation=operation, page=page, object_index=object_index,
                object_type=object_type, native_code=int(raw.FPDF_GetLastError()) if native_code is None else native_code)


@contextmanager
def diagnostic(stage, operation, page=None, object_index=None, object_type=None):
    try:
        with timed_stage(stage + '.' + operation, page, object_index):
            yield
    except (PdfError, pdfium.PdfiumError) as error:
        data = getattr(error, 'diagnostic', None) or context(stage, operation, page, object_index, object_type,
                                                          getattr(error, 'err_code', None))
        logger.error('run=%s PDF diagnostic %s', current_document_run(), data)
        raise PdfError(getattr(error, 'kind', PdfKind.UNSUPPORTED_PDF), data) from None


def preserved(stage, operation, page, object_index, object_type):
    logger.warning('run=%s PDF preserved %s', current_document_run(), context(stage, operation, page, object_index, object_type))
