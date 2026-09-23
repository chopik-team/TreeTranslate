"""Safe native context. Never include exception messages or document strings."""
from contextlib import contextmanager
import logging
import pypdfium2 as pdfium
import pypdfium2.raw as raw
from app.documents.pdf_types import PdfError, PdfKind


def context(stage, operation, page=None, object_index=None, object_type=None, native_code=None):
    return dict(stage=stage, operation=operation, page=page, object_index=object_index,
                object_type=object_type, native_code=int(raw.FPDF_GetLastError()) if native_code is None else native_code)


@contextmanager
def diagnostic(stage, operation, page=None, object_index=None, object_type=None):
    try:
        yield
    except (PdfError, pdfium.PdfiumError) as error:
        data = getattr(error, 'diagnostic', None) or context(stage, operation, page, object_index, object_type,
                                                          getattr(error, 'err_code', None))
        logging.getLogger(__name__).error('PDF diagnostic %s', data)
        raise PdfError(getattr(error, 'kind', PdfKind.UNSUPPORTED_PDF), data) from None


def preserved(stage, operation, page, object_index, object_type):
    logging.getLogger(__name__).warning('PDF preserved %s', context(stage, operation, page, object_index, object_type))
