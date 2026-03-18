import logging
import os
import sys

_loggers: dict = {}

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger for the given name.
    Each unique name gets its own logger instance, but they are cached
    so repeated calls with the same name return the same logger.
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    # Only add handlers if the logger doesn't already have them
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)

    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # Prevent messages from propagating to the root logger (avoids duplicate output)
    logger.propagate = False

    _loggers[name] = logger
    return logger
