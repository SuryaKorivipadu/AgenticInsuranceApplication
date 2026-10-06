import logging
import os
from logging.handlers import RotatingFileHandler

log_path = os.path.join(os.getcwd(), 'logs')
os.makedirs(log_path, exist_ok=True)

# Add a custom field used by the formatter below.
old_factory = logging.getLogRecordFactory()


def record_factory(*args, **kwargs):
    """Add a project-relative module path used by the log formatter."""
    record = old_factory(*args, **kwargs)
    repl_path = os.path.relpath(record.pathname)
    record.module_path = repl_path.replace(os.sep, '.').replace('.py', "")
    return record

logging.setLogRecordFactory(record_factory)

def get_logger(name: str = 'app', log_path: str = log_path) -> logging.Logger:
    """Return an application logger with console and rotating-file handlers."""
    logger = logging.getLogger(name)
    # Set the logger level before handlers so DEBUG records are not discarded.
    logger.setLevel(logging.DEBUG)
    # These handlers own output; prevent duplicate messages from the root logger.
    logger.propagate = False
    if not logger.handlers:
        log_format = (
            "%(asctime)s | %(levelname)s | %(name)s | %(module_path)s | "
            "%(filename)s:%(lineno)d | %(funcName)s | %(message)s"
        )
        formatter = logging.Formatter(log_format)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Rotate the file when it reaches 5 MB and keep three backups.
        file_handler = RotatingFileHandler(
            os.path.join(log_path, 'app.log'),
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = get_logger()
