import logging

from app.config import logging_config


def test_logging_is_local_rotating_and_idempotent(tmp_path, monkeypatch) -> None:
    logger = logging.getLogger("treetranslate")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    monkeypatch.setattr(logging_config, "LOGS_DIR", tmp_path)

    configured = logging_config.configure_logging(logging.DEBUG)
    assert logging_config.configure_logging(logging.DEBUG) is configured
    assert len(configured.handlers) == 1
    configured.warning("UI state only")
    configured.handlers[0].flush()
    assert "UI state only" in (tmp_path / "treetranslate.log").read_text(encoding="utf-8")
