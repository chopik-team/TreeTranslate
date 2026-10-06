class MemoryError(Exception):
    """Messages must never contain translation text or database diagnostics."""


class MemoryUnavailable(MemoryError):
    pass


class InvalidMemoryData(MemoryError):
    pass
