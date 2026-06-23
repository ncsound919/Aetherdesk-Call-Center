import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Resolve log directory relative to the project root (not CWD) so that
# the path is predictable regardless of where the process is started.
_LOG_DIR = Path(os.getenv("APP_LOG_DIR", str(Path(__file__).resolve().parent.parent.parent / "logs")))
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE = _LOG_DIR / "app.log"
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _build_logger(name: str = __name__) -> logging.Logger:
    """Create (or return the existing) logger with a rotating file handler.

    The ``if not logger.handlers`` guard prevents duplicate handlers when
    the module is re-imported (e.g. in test runners, importlib.reload, or
    multiprocessing forking).  ``propagate = False`` stops logs from being
    written a second time by the root handler.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=1024 * 1024,  # 1 MB per file
        backupCount=5,
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    file_handler.setLevel(logging.ERROR)

    logger.addHandler(file_handler)
    return logger


logger = _build_logger()


def log_error(message: str, exc_info: bool = True) -> None:
    """Log *message* at ERROR level with optional exception info."""
    logger.error(message, exc_info=exc_info)
