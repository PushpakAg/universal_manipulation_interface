"""
Detect corners of all tags with a configured size in every video of the observing (head) camera
of a session (v2 of scripts_tag_tracking/00_detect_tag_corners.py).

One process pool is created once and shared by all videos, two videos ahead (each video is cut into time chunks,
--chunks_per_worker per worker), instead of one pool per video and a wait for its slowest chunk. Writes tag_corners.pkl next to each raw_video.mp4
atomically (a killed run never leaves a half-written file); videos that already have one are
skipped unless --overwrite (needed after changing tag sizes/ids). A video that fails is logged and
the others continue; the exit code is 1 if any failed.

--detect_scale < 1 searches tags on a downscaled frame (faster, see tt2/tag_detection.py);
validate with compare_detection.py first. Default 1.0 = original algorithm, identical output.

python tag_tracking_v2/scripts_tag_tracking/00_detect_tag_corners.py -i data_workspace/session -c umi_calib/tag_tracking.yaml
"""
# %%
import sys
import os
import pathlib

V2_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V2_ROOT))
from tt2.bootstrap import setup_paths, user_path
setup_paths()

# %%
import time
import click
from umi.common.exiftool_util import ExifTool
from umi.tag_tracking.config import load_tag_tracking_config
from tt2.errors import InputError, PipelineError, require
from tt2.fsutil import atomic_pickle_dump
from tt2.log import setup_logging, get_logger
from tt2.tag_detection import submit_video_tag_corners
from tt2.video_chunk import make_pool, gather_chunked, run_pipelined

log = get_logger(__name__)


# %%
# %%
@click.command()
@click.option('-i', '--input', required=True, help='Session directory')
@click.option('-c', '--config', required=True, help='Tag tracking config yaml')
@click.option('-ow', '--overwrite', is_flag=True, default=False, help='Re-detect videos that have tag_corners.pkl')
@click.option('-n', '--num_workers', type=int, default=None, help='Worker processes, default all cores')
@click.option('--detect_scale', type=click.FloatRange(0.2, 1.0), default=1.0,
    help='Search scale, 1.0 = full resolution (original algorithm)')
@click.option('--chunks_per_worker', type=click.IntRange(min=1), default=1, help='Time chunks per worker and video')
def main(input, config, overwrite, num_workers, detect_scale, chunks_per_worker):
    setup_logging()
    session = user_path(input)
    require(session.is_dir(), f"session folder not found: {session}")
    config_path = str(user_path(config))
    require(os.path.isfile(config_path), f"config not found: {config_path}")
    config = load_tag_tracking_config(config_path)
    head_camera = config['head_camera']

    video_paths = list()
    with ExifTool() as et:
        for video_path in sorted(session.glob('demos/*/raw_video.mp4')):
            try:
                serial = list(et.get_metadata(str(video_path)))[0]['QuickTime:CameraSerialNumber']
            except (KeyError, IndexError) as e:
                log.error("%s: no camera serial in the metadata (%s), skipped", video_path.parent.name, e)
                continue
            if serial != head_camera:
                continue
            if video_path.parent.joinpath('tag_corners.pkl').is_file() and not overwrite:
                log.info("tag_corners.pkl already exists, skipping %s", video_path.parent.name)
                continue
            video_paths.append(video_path)
    log.info("Detecting tags in %d videos of camera %s (scale %.2f)", len(video_paths), head_camera, detect_scale)

    t0 = time.time()
    executor = make_pool(num_workers)

    def submit(video_path):
        log.info("submit %s", video_path.parent.name)
        return submit_video_tag_corners(executor, str(video_path), config['aruco_dict'], config['known_tag_ids'],
            detect_scale, chunks_per_worker)

    def finish(video_path, handle):
        results = gather_chunked(handle)
        output = video_path.parent.joinpath('tag_corners.pkl')
        atomic_pickle_dump(results, output)
        log.info("Saved %s (%d frames)", output, len(results))

    try:
        # two videos ahead in the shared pool: no idle cores while the last chunks of a video finish
        failures = run_pipelined(video_paths, submit, finish, lookahead=2)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    failed = [v.parent.name for v, e in failures]
    for v, e in failures:
        log.error("%s failed: %s", v.parent.name, e)
    log.info("head tag detection: %d videos, %d failed, %.1f s", len(video_paths), len(failed), time.time() - t0)
    if failed:
        raise InputError(f"detection failed for {len(failed)} videos: {', '.join(failed)}")

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
