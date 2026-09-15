from app.engine.errors import BackendUnavailableError, UnsupportedLanguageError

LANGUAGE_CODES = {
    "Определить автоматически": "auto", "Авто": "auto",
    "Русский": "ru", "Английский": "en", "Английский (США)": "en", "Немецкий": "de",
    "Испанский": "es", "Французский": "fr", "Китайский": "zh", "Японский": "ja",
}


def language_code(value: str) -> str:
    return LANGUAGE_CODES.get(value, value.lower())


class LanguageResolver:
    """Lazy local langid model (bundled in its wheel); no model download."""

    def __init__(self):
        self._identifier = None

    def resolve(self, text: str, source: str, target: str) -> tuple[str, str]:
        source, target = language_code(source), language_code(target)
        if target == "auto":
            raise UnsupportedLanguageError("Выберите язык перевода явно.")
        if source == "auto":
            if not any(character.isalpha() for character in text):
                raise UnsupportedLanguageError("Не удалось определить язык. Выберите исходный язык явно.")
            if self._identifier is None:
                try:
                    from langid.langid import LanguageIdentifier, model
                except ImportError:
                    raise BackendUnavailableError() from None
                self._identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
            source, _confidence = self._identifier.classify(text)
        return source, target

    def shutdown(self):
        self._identifier = None
