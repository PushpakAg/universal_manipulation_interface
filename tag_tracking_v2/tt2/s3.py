"""
S3 access with boto3, replacing aws-cli subprocesses.

Why: every `aws s3api` call is a new process (Python start, credential lookup, TLS handshake),
without timeout, without shared connections. One client with a connection pool, retries and
timeouts does the same work in-process, and is thread safe.

Credentials: the default boto3 chain (AWS_PROFILE, SSO, environment). `make_client(profile=...)`
overrides the profile. An expired SSO token raises TransferError with the fix.

Verified transfer: uploads are checked after the fact by size and, when the object has a plain
MD5 ETag (no KMS), by MD5 (single part) or the multipart ETag computed with the same part size.
Downloads go to `<file>.part` and are renamed when the size matches the object.
"""
import concurrent.futures
import hashlib
import os
import pathlib
import threading
from typing import Dict, List, Optional, Tuple

import boto3
import botocore.config
import botocore.exceptions
from boto3.s3.transfer import TransferConfig

from tt2.errors import TransferError
from tt2.log import get_logger

log = get_logger(__name__)

_CLIENTS: Dict[Optional[str], object] = {}
_LOCK = threading.Lock()
PART_SIZE = 64 * 1024 * 1024
TRANSFER = TransferConfig(multipart_threshold=PART_SIZE, multipart_chunksize=PART_SIZE, max_concurrency=16)


def make_client(profile: Optional[str] = None):
    """Shared client per profile: retries (adaptive, 8 attempts), 10 s connect / 60 s read timeout, 64 connections."""
    with _LOCK:
        if profile not in _CLIENTS:
            session = boto3.Session(profile_name=profile) if profile else boto3.Session()
            _CLIENTS[profile] = session.client('s3', config=botocore.config.Config(
                retries={'max_attempts': 8, 'mode': 'adaptive'}, connect_timeout=10, read_timeout=60,
                max_pool_connections=64))
        return _CLIENTS[profile]


def split(url: str) -> Tuple[str, str]:
    """('bucket', 'prefix/without/trailing/slash') of an s3:// url."""
    if not url.startswith('s3://'):
        raise TransferError(f"not an s3:// url: {url}")
    bucket, _, prefix = url[len('s3://'):].partition('/')
    if not bucket:
        raise TransferError(f"no bucket in {url}")
    return bucket, prefix.rstrip('/')


def _wrap(url: str, e: Exception) -> TransferError:
    text = str(e)
    if 'Token has expired' in text or 'SSO' in text or 'ExpiredToken' in text:
        return TransferError(f"{url}: credentials expired, run `aws sso login` (profile {os.environ.get('AWS_PROFILE', 'default')}) and rerun: {e}")
    return TransferError(f"{url}: {e}")


def list_objects(url: str, profile: Optional[str] = None) -> List[Tuple[str, int]]:
    """(key, size) of all objects under the prefix (paginated)."""
    bucket, prefix = split(url)
    out = []
    try:
        for page in make_client(profile).get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix + '/' if prefix else ''):
            out += [(o['Key'], o['Size']) for o in page.get('Contents', [])]
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as e:
        raise _wrap(url, e) from e
    return out


def list_folders(url: str, profile: Optional[str] = None) -> List[str]:
    """Names of the direct sub-folders of a prefix, using Delimiter (does not list every object)."""
    bucket, prefix = split(url)
    out = []
    try:
        for page in make_client(profile).get_paginator('list_objects_v2').paginate(
                Bucket=bucket, Prefix=prefix + '/' if prefix else '', Delimiter='/'):
            out += [p['Prefix'][len(prefix) + 1 if prefix else 0:].rstrip('/') for p in page.get('CommonPrefixes', [])]
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as e:
        raise _wrap(url, e) from e
    return out


def list_sizes(url: str, profile: Optional[str] = None) -> Dict[str, int]:
    """File name -> size of the objects directly under the prefix (not deeper)."""
    _, prefix = split(url)
    plen = len(prefix) + 1 if prefix else 0
    return {k[plen:]: n for k, n in list_objects(url, profile) if '/' not in k[plen:] and k[plen:]}


def read_range(bucket: str, key: str, start: int, end: int, profile: Optional[str] = None) -> bytes:
    """Bytes [start, end] (inclusive) of an object."""
    try:
        return make_client(profile).get_object(Bucket=bucket, Key=key, Range=f'bytes={start}-{end}')['Body'].read()
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as e:
        raise _wrap(f"s3://{bucket}/{key}", e) from e


def md5_etag(path, size_bytes: int = None, part_size: int = PART_SIZE, threshold: int = PART_SIZE) -> str:
    """ETag S3 reports for a file uploaded with boto3 TransferConfig(part_size): md5, or md5-of-md5s '-N'."""
    path = pathlib.Path(path)
    size = path.stat().st_size if size_bytes is None else size_bytes
    with path.open('rb') as f:
        if size < threshold:
            h = hashlib.md5()
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
            return h.hexdigest()
        digests = []
        while True:
            h, left = hashlib.md5(), part_size
            while left > 0:
                chunk = f.read(min(left, 1 << 20))
                if not chunk:
                    break
                h.update(chunk)
                left -= len(chunk)
            if left == part_size:
                break
            digests.append(h.digest())
            if left > 0:
                break
        return f"{hashlib.md5(b''.join(digests)).hexdigest()}-{len(digests)}"


def upload_verified(path, url: str, profile: Optional[str] = None) -> str:
    """
    Upload a file to s3://bucket/key (url is the full object url) and verify it. Returns a
    description ('size', 'md5' or 'size only (kms etag)'). Raises TransferError on mismatch.
    """
    path = pathlib.Path(path)
    bucket, key = split(url)
    client = make_client(profile)
    try:
        client.upload_file(str(path), bucket, key, Config=TRANSFER)
        head = client.head_object(Bucket=bucket, Key=key)
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError, OSError) as e:
        raise _wrap(url, e) from e
    local_size = path.stat().st_size
    if head['ContentLength'] != local_size:
        raise TransferError(f"{url}: size {head['ContentLength']} on S3, {local_size} local")
    if head.get('ServerSideEncryption') == 'aws:kms':
        return 'size only (kms etag)'
    expected, got = md5_etag(path), head['ETag'].strip('"')
    if expected != got:
        raise TransferError(f"{url}: ETag {got} on S3, expected {expected} (corrupt upload)")
    return 'md5'


def verify_remote(path, url: str, profile: Optional[str] = None, deep: bool = False) -> bool:
    """True if the object at url has the local file's size (and, with deep, its ETag)."""
    path = pathlib.Path(path)
    bucket, key = split(url)
    try:
        head = make_client(profile).head_object(Bucket=bucket, Key=key)
    except botocore.exceptions.ClientError as e:
        if e.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound'):
            return False
        raise _wrap(url, e) from e
    if head['ContentLength'] != path.stat().st_size:
        return False
    if deep and head.get('ServerSideEncryption') != 'aws:kms':
        return md5_etag(path) == head['ETag'].strip('"')
    return True


def download_prefix(url: str, dest, profile: Optional[str] = None, workers: int = 8) -> dict:
    """
    Download every object under url into dest (relative layout kept). Files already there with the
    same size are skipped. Each file goes to `<name>.part` and is renamed after a size check.
    Returns {'files': n, 'downloaded': n, 'skipped': n, 'bytes': n}. Raises TransferError listing failures.
    """
    dest = pathlib.Path(dest)
    _, prefix = split(url)
    plen = len(prefix) + 1 if prefix else 0
    bucket = split(url)[0]
    objects = [(k, n) for k, n in list_objects(url, profile) if not k.endswith('/')]
    client = make_client(profile)
    stats = {'files': len(objects), 'downloaded': 0, 'skipped': 0, 'bytes': 0}
    lock = threading.Lock()

    def one(item):
        key, size = item
        target = dest / key[plen:]
        if target.is_file() and not target.is_symlink() and target.stat().st_size == size:
            with lock:
                stats['skipped'] += 1
            return
        # a hard link or symlink from sort_videos must not be overwritten through: skip those that resolve
        if target.exists() and target.resolve().is_file() and target.resolve().stat().st_size == size:
            with lock:
                stats['skipped'] += 1
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + '.part')
        client.download_file(bucket, key, str(part), Config=TRANSFER)
        if part.stat().st_size != size:
            part.unlink()
            raise TransferError(f"s3://{bucket}/{key}: downloaded size differs from {size}")
        os.replace(part, target)
        with lock:
            stats['downloaded'] += 1
            stats['bytes'] += size

    failures = []
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(one, o): o[0] for o in objects}
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError, OSError, TransferError) as e:
                failures.append(f"{futures[f]}: {_wrap(url, e) if not isinstance(e, TransferError) else e}")
    if failures:
        raise TransferError(f"{len(failures)} of {len(objects)} files failed under {url}: {failures[:3]}")
    log.info("download %s -> %s: %d files, %d downloaded (%.2f GB), %d skipped", url, dest, stats['files'],
        stats['downloaded'], stats['bytes'] / 1e9, stats['skipped'])
    return stats
