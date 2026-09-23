"""Format dispatch for the shared file job. DOCX implementation stays unchanged."""
from app.documents.docx_document import DocxDocument
from app.documents.errors import DocumentError


def open_document(path, control, pdf_limits=None, pdf_extractor=None):
    extension = path.suffix.lower()
    if extension == '.docx':
        return DocxDocument(path)
    if extension == '.pdf':
        from app.documents.pdf_document import PdfDocument
        return PdfDocument(path, limits=pdf_limits, checkpoint=control.checkpoint, extractor=pdf_extractor)
    raise DocumentError('Формат пока не поддерживается.')
