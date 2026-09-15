class TranslationError(Exception):
    """Safe public messages only: never include input or a backend exception string."""

    default_message = "Не удалось выполнить локальный перевод."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class BackendUnavailableError(TranslationError):
    default_message = "Компонент локального перевода недоступен. Проверьте установку приложения."


class ModelMissingError(BackendUnavailableError):
    default_message = "Компонент локального перевода отсутствует или повреждён."


class ModelCorruptedError(ModelMissingError):
    pass


class UnsupportedLanguageError(TranslationError):
    default_message = "Для этой пары языков нет доступного локального перевода."


class DeviceUnavailableError(TranslationError):
    default_message = "GPU недоступна для локального перевода. Выберите CPU или Auto."


class TranslationCancelledError(TranslationError):
    default_message = "Перевод отменён."


class InputTooLongError(TranslationError):
    default_message = "Текст слишком большой. Переведите его несколькими частями."
