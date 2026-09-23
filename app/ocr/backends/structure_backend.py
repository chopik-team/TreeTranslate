from app.ocr.backends.paddle_backend import PaddleBackend


class StructureBackend(PaddleBackend):
    """PP-StructureV3 layout/table analysis with exclusively local artifacts."""
    name = 'structure'
