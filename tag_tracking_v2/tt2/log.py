"""
Logging for every script and step.

setup_logging(name, log_file) configures the root logger once: console (INFO) and, if given, a
file (DEBUG) with timestamps. Child processes started by the runner write their own output to
their step log; the parent logs start, end, duration and result of each step.

Use `log = get_logger(__name__)` in modules and `log.info(...)`, never print() for status.
Progress bars (tqdm) stay on stderr and are not logged.
"""
import logging
import pathlib
import sys
from typing import Optional

FORMAT = '%(asctime)s %(levelname)-7s %(name)s: %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
_FILE_HANDLERS = {}


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith('tt2') or name == '__main__' else f"tt2.{name}")


def setup_logging(log_file: Optional[str] = None, level: int = logging.INFO, console: bool = True) -> logging.Logger:
    """
    Configure the root logger. Safe to call again with another log file (the previous file
    handler is replaced). Returns the root logger.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if not any(getattr(h, '_tt2_console', False) for h in root.handlers) and console:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(FORMAT, DATE_FORMAT))
        handler._tt2_console = True
        root.addHandler(handler)
    if log_file is not None:
        set_log_file(log_file)
    return root


def set_log_file(log_file: str):
    """Send DEBUG and above to log_file (appended); replaces the file of an earlier call."""
    root = logging.getLogger()
    old = _FILE_HANDLERS.pop('file', None)
    if old is not None:
        root.removeHandler(old)
        old.close()
    path = pathlib.Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode='a', encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(FORMAT, DATE_FORMAT))
    root.addHandler(handler)
    _FILE_HANDLERS['file'] = handler


def clear_log_file():
    old = _FILE_HANDLERS.pop('file', None)
    if old is not None:
        logging.getLogger().removeHandler(old)
        old.close()
