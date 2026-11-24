"""
File system helpers that make outputs safe to interrupt.

atomic_path / atomic_write_bytes / atomic_pickle_dump / atomic_json_dump: write to `<name>.tmp-<pid>`
in the same folder, then os.replace (atomic on one file system). A crash or kill leaves the
old file (or none), never a half-written one. On an exception the temp file is removed.

swap_directory: replace a directory with a fully built new one; the old one is kept aside
until the new one is in place, and put back if the swap fails.

fingerprint: short hash of files / values, used to decide that a step can be skipped.
"""
import contextlib
import hashlib
import json
import os
import pathlib
import pickle
import shutil
import time
from typing import Iterable

from tt2.log import get_logger

log = get_logger(__name__)


@contextlib.contextmanager
def atomic_path(path):
    """
    Yield a temp path next to `path`; on normal exit it replaces `path`, on error it is deleted.
    The temp name is `.<name>.tmp-<pid>` (hidden, never matched by a glob for the real files).
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # hidden and without the final suffix: a leftover of a killed run is never matched by '*.mcap' / '*.pkl' globs
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        yield tmp
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


def atomic_write_bytes(path, data: bytes):
    with atomic_path(path) as tmp:
        tmp.write_bytes(data)


def atomic_pickle_dump(obj, path):
    with atomic_path(path) as tmp:
        with tmp.open('wb') as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def atomic_json_dump(obj, path, indent=2):
    with atomic_path(path) as tmp:
        with tmp.open('w') as f:
            json.dump(obj, f, indent=indent)


def swap_directory(new_dir, target, archive_prefix: str = None) -> str:
    """
    Make `new_dir` the directory `target`. An existing `target` is moved to
    `<archive_prefix>_<date>_<time>` (default `<target>_<date>_<time>`) first and moved back if
    the rename of new_dir fails. Returns the archive path or ''.
    """
    new_dir, target = pathlib.Path(new_dir), pathlib.Path(target)
    archived = ''
    if target.exists():
        prefix = archive_prefix or str(target)
        archived = f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}"
        os.rename(target, archived)
    try:
        os.rename(new_dir, target)
    except BaseException:
        if archived:
            os.rename(archived, target)
        raise
    return archived


def fingerprint(paths: Iterable = (), values: Iterable = ()) -> str:
    """
    Hash of the content of the given files (path -> bytes; a missing file counts as missing) and
    of the given values (repr). 16 hex characters.
    """
    h = hashlib.sha256()
    for p in paths:
        p = pathlib.Path(p)
        h.update(str(p.name).encode())
        if p.is_file():
            with p.open('rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
        else:
            h.update(b'<missing>')
    for v in values:
        h.update(repr(v).encode())
    return h.hexdigest()[:16]


def file_signature(paths: Iterable) -> list:
    """(name, size, mtime_ns) of each file, for a cheap change check of large inputs (videos)."""
    out = []
    for p in sorted(str(x) for x in paths):
        try:
            st = os.stat(p)
            out.append((os.path.basename(p), st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((os.path.basename(p), -1, -1))
    return out
