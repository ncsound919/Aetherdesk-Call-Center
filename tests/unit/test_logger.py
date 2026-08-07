import logging

from services.logger import _build_logger, log_error


def test_build_logger_returns_existing_with_handlers():
    existing = logging.getLogger("already.configured.logger")
    existing.handlers = []
    existing.addHandler(logging.NullHandler())

    result = _build_logger("already.configured.logger")

    assert result is existing
    assert len(result.handlers) == 1


def test_log_error_emits_error_record():
    import services.logger as logger_mod

    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture()
    logger_mod.logger.addHandler(handler)
    try:
        logger_mod.log_error("boom", exc_info=False)
    finally:
        logger_mod.logger.removeHandler(handler)

    assert "boom" in records
