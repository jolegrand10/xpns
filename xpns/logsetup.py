"""Module logsetup.py - home of functions for logging configuration"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "xpns.log"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"


def setup_logger(level=logging.INFO, log_file=LOG_FILE):
    """Configure the root logger to write to the console and to a log file.

    Existing handlers are replaced, so calling it twice does not duplicate
    output. The log file directory is created if needed.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    for handler in (
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    return root


def main():
    """Smoke test: configure logging and emit one message per level."""
    setup_logger(logging.DEBUG)
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    print(f"Log file: {LOG_FILE}")


if __name__ == "__main__":
    main()
