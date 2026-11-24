"""
Per-frame processing of a long video on all CPU cores (v2 of umi/common/video_chunk_util.py).

Same contract as the original: the video is cut into time chunks, each worker seeks to the keyframe
before its chunk, decodes, skips frames before it and stops at its end, so every frame is processed
exactly once; results come back in frame order and the frame count is checked.

Changes against the original:
- more chunks than workers (default 4 per worker): chunks finish at different times (keyframe
  seek, scene content), with one chunk per worker the slowest chunk decides the video's time;
- an optional shared executor: the original builds a spawn pool per video, paying interpreter and
  cv2/av import for every video (the first chunk of the first video took 37 s of 43 s in the real run);
- failures name the video and chunk (time range); a failed chunk cancels the rest instead of
  leaving the pool running;
- consistency checks raise errors with the video name instead of `assert`;
- logs start, end and speed of each video.

Workers are started with 'spawn' (see the original module for why). The factory must be importable.
"""
import concurrent.futures
import math
import multiprocessing
import time
from typing import Callable, List, Optional, Tuple

import av
import av.logging
from tqdm import tqdm

from tt2.errors import PipelineError, InputError
from tt2.log import get_logger

log = get_logger(__name__)
SEEK_MARGIN_SEC = 1.0
CHUNKS_PER_WORKER = 4


def get_chunk_bounds(video_path: str, n_chunks: int) -> Tuple[List[Tuple[float, float]], int]:
    """n_chunks time intervals [start, end) covering all frames (boundaries halfway between frames) and the frame count."""
    try:
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            n_frames = stream.frames
            fps = float(stream.average_rate)
            first_time = float(next(container.decode(stream)).pts * stream.time_base)
    except (av.error.FFmpegError, OSError, IndexError, StopIteration) as e:
        raise InputError(f"{video_path}: cannot read the video ({type(e).__name__}: {e})") from e
    if n_frames <= 0:
        raise InputError(f"{video_path}: frame count unknown in the container, cannot split into chunks")
    n_chunks = max(1, min(n_chunks, n_frames))
    starts = [first_time + (k * n_frames // n_chunks - 0.5) / fps for k in range(n_chunks)]
    starts[0] = -math.inf
    ends = starts[1:] + [math.inf]
    return list(zip(starts, ends)), n_frames


def _process_chunk(video_path: str, start: float, end: float,
        make_processor: Callable, processor_args: tuple) -> List[dict]:
    av.logging.set_level(av.logging.ERROR)
    process = make_processor(*processor_args)
    results = list()
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        stream.thread_count = 1
        if start > -math.inf:
            container.seek(max(0, int((start - SEEK_MARGIN_SEC) / stream.time_base)),
                stream=stream, backward=True, any_frame=False)
        for frame in container.decode(stream):
            time_ = float(frame.pts * stream.time_base)
            if time_ < start:
                continue
            if time_ >= end:
                break
            results.append(process(frame, time_))
    return results


def make_pool(num_workers: Optional[int] = None) -> concurrent.futures.ProcessPoolExecutor:
    """A spawn pool to share between videos (pass as `executor`)."""
    return concurrent.futures.ProcessPoolExecutor(max_workers=num_workers or multiprocessing.cpu_count(),
        mp_context=multiprocessing.get_context('spawn'))


def submit_chunked(executor: concurrent.futures.Executor, video_path: str, make_processor: Callable,
        processor_args: tuple = (), desc: Optional[str] = None, chunks_per_worker: int = CHUNKS_PER_WORKER) -> dict:
    """
    Submit the chunks of one video to a shared executor without waiting; collect with gather_chunked.
    Lets several videos share the pool: while one video's last chunks run, the next video's chunks
    already occupy the idle workers (no tail where cores wait for the slowest chunk).
    """
    workers = getattr(executor, '_max_workers', None) or multiprocessing.cpu_count()
    bounds, n_frames = get_chunk_bounds(video_path, workers * chunks_per_worker)
    futures = [executor.submit(_process_chunk, video_path, start, end, make_processor, processor_args)
        for start, end in bounds]
    return {'path': video_path, 'desc': desc or video_path, 'bounds': bounds, 'n_frames': n_frames,
        'futures': futures, 'workers': workers, 't0': time.time()}


def gather_chunked(handle: dict, progress: bool = True) -> List[dict]:
    """Results of a submitted video in frame order (checked), each with 'frame_idx' and 'time'."""
    video_path, bounds, futures = handle['path'], handle['bounds'], handle['futures']
    chunks = [None] * len(futures)
    index = {f: k for k, f in enumerate(futures)}
    try:
        done = concurrent.futures.as_completed(futures)
        if progress:
            done = tqdm(done, total=len(futures), desc=f"{handle['desc']} ({len(bounds)} chunks)")
        for future in done:
            k = index[future]
            try:
                chunks[k] = future.result()
            except Exception as e:
                raise PipelineError(f"{video_path}: chunk {k} ({bounds[k][0]:.2f}..{bounds[k][1]:.2f} s) failed: "
                    f"{type(e).__name__}: {e}") from e
    except BaseException:
        for f in futures:
            f.cancel()
        raise
    results = [x for chunk in chunks for x in chunk]
    times = [x['time'] for x in results]
    if len(results) != handle['n_frames']:
        raise PipelineError(f"{video_path}: {len(results)} frames processed, stream has {handle['n_frames']}")
    if not all(a < b for a, b in zip(times[:-1], times[1:])):
        raise PipelineError(f"{video_path}: frames out of order")
    for i, (x, time_) in enumerate(zip(results, times)):
        x['frame_idx'] = i
        x['time'] = time_
    seconds = time.time() - handle['t0']
    log.info("%s: %d frames, %.1f s since submitted (%d chunks, %d workers)", handle['desc'], handle['n_frames'],
        seconds, len(bounds), handle['workers'])
    return results


def process_video_chunked(video_path: str, make_processor: Callable, processor_args: tuple = (),
        num_workers: Optional[int] = None, desc: Optional[str] = None,
        executor: Optional[concurrent.futures.Executor] = None,
        chunks_per_worker: int = CHUNKS_PER_WORKER) -> List[dict]:
    """
    Results of process(frame, time) for every frame in order, each with 'frame_idx' and 'time' set.
    executor: reuse this pool (its worker count sets the chunk count); else a pool is created and closed here.
    """
    own = executor is None
    if own:
        executor = make_pool(num_workers)
    try:
        return gather_chunked(submit_chunked(executor, video_path, make_processor, processor_args, desc,
            chunks_per_worker))
    finally:
        if own:
            executor.shutdown(wait=True)


def run_pipelined(items, submit: Callable, finish: Callable, lookahead: int = 2, errors=(PipelineError, OSError)) -> list:
    """
    Process items with the submit/finish pattern: submit(item) starts the work (returns a handle), finish(item, handle)
    collects it. Up to `lookahead` items are submitted ahead of the one being finished, so the pool always has queued
    work while the main process post-processes a finished item. Items are finished in order. An item whose submit or
    finish raises one of `errors` is recorded and the others continue. Returns [(item, exception), ...].
    """
    import collections
    pending, failures = collections.deque(), []

    def finish_oldest():
        item, handle = pending.popleft()
        try:
            finish(item, handle)
        except errors as e:
            failures.append((item, e))

    for item in items:
        try:
            pending.append((item, submit(item)))
        except errors as e:
            failures.append((item, e))
        while len(pending) > lookahead:
            finish_oldest()
    while pending:
        finish_oldest()
    return failures
