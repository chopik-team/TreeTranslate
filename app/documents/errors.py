class DocumentError(Exception):
    """Safe user-facing message; never include extracted document text."""


class InvalidDocumentError(DocumentError):
    def __init__(self):
        super().__init__("Не удалось открыть DOCX: файл повреждён, защищён или имеет неподдерживаемую структуру.")


class SourceChangedError(DocumentError):
    def __init__(self):
        super().__init__("Исходный файл изменился во время перевода. Результат для него не сохранён.")
