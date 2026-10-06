class GlossaryError(Exception):
    """Safe diagnostics: no source or target text in exception messages."""


class InvalidGlossary(GlossaryError):
    pass


class GlossaryUnavailable(GlossaryError):
    pass


class ConstraintFailure(GlossaryError):
    pass
