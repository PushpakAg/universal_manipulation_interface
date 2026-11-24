"""
Detect ArUco tags (corners and single-tag pose) in every <demos>/*/raw_video.mp4, writes tag_detection.pkl next to each
video (skipped if it exists). v2 of scripts_slam_pipeline/04_detect_aruco.py, same options, same output.

Videos are cut into time chunks (1 per worker by default, --chunks_per_worker) and ALL videos share one process pool, two videos ahead: while the last
chunks of one video run, the next video's chunks fill the idle cores. The original starts a new `python
scripts/detect_aruco.py` (interpreter, imports, new pool of 8 spawned workers) for every video and waits for the slowest
chunk of each. The per frame detection is the original code path; the mirror mask is applied with a precomputed mask
(identical pixels, see tt2/wrist_detection.py). tag_detection.pkl is written atomically.
A video that fails is logged and the others continue; the exit code is 1 if any failed.

With --tag_tracking_config, each camera uses its intrinsics from the config's cameras section (camera_intrinsics for
cameras not listed). With --wrist_only as well, only wrist (gripper) camera videos are processed, without the SLAM mapping
video: the tag tracking pipeline detects head camera tags itself (scripts_tag_tracking/00_detect_tag_corners.py).

python tag_tracking_v2/scripts_slam_pipeline/04_detect_aruco.py -i <session>/demos -ci gopro_intrinsics_2_7k.json -ac aruco_config.yaml \\
    -tc tag_tracking.yaml --wrist_only
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
import pickle
import time
import av
import click
import numpy as np
import yaml
from umi.common.exiftool_util import ExifTool
from tt2.errors import InputError, PipelineError, require
from tt2.fsutil import atomic_pickle_dump
from tt2.log import setup_logging, get_logger
from tt2.video_chunk import make_pool, submit_chunked, gather_chunked, run_pipelined
from tt2.wrist_detection import make_wrist_detector

log = get_logger(__name__)


# %%
@click.command()
@click.option('-i', '--input_dir', required=True, help='Directory for demos folder')
@click.option('-ci', '--camera_intrinsics', required=True, help='Camera intrinsics json file (2.7k)')
@click.option('-ac', '--aruco_yaml', required=True, help='Aruco config yaml file')
@click.option('-tc', '--tag_tracking_config', default=None,
    help='Optional tag tracking config: per camera serial intrinsics from its cameras section, '
    'camera_intrinsics for cameras not listed')
@click.option('-wo', '--wrist_only', is_flag=True, default=False,
    help='With --tag_tracking_config: only videos of gripper cameras, not the mapping video')
@click.option('-n', '--num_workers', type=click.IntRange(min=1), default=None, help='Worker processes, default all cores')
@click.option('--chunks_per_worker', type=click.IntRange(min=1), default=1,
    help='Time chunks per worker and video (1 was fastest in the A/B, see CHANGELOG_v2.md)')
def main(input_dir, camera_intrinsics, aruco_yaml, tag_tracking_config, wrist_only, num_workers, chunks_per_worker):
    setup_logging()
    input_dir = user_path(input_dir)
    video_dirs = sorted(x.parent for x in input_dir.glob('*/raw_video.mp4'))
    log.info('Found %d video dirs', len(video_dirs))
    camera_intrinsics, aruco_yaml = str(user_path(camera_intrinsics)), str(user_path(aruco_yaml))
    require(os.path.isfile(camera_intrinsics), f"intrinsics not found: {camera_intrinsics}")
    require(os.path.isfile(aruco_yaml), f"aruco config not found: {aruco_yaml}")
    require((not wrist_only) or (tag_tracking_config is not None), "--wrist_only needs --tag_tracking_config")

    # per camera serial intrinsics and wrist cameras from the tag tracking config
    serial_intrinsics = dict()
    wrist_serials = set()
    if tag_tracking_config is not None:
        config_path = user_path(tag_tracking_config)
        require(config_path.is_file(), f"config not found: {config_path}")
        config = yaml.safe_load(config_path.open('r'))
        serial_intrinsics = {str(k): str(config_path.parent.joinpath(v)) for k, v in config['cameras'].items()}
        for path in serial_intrinsics.values():
            require(os.path.isfile(path), f"intrinsics in the config not found: {path}")
        wrist_serials = {str(b['gripper_camera']) for b in config['bodies'].values() if 'gripper_camera' in b}

    # videos to process and their intrinsics
    video_intrinsics = dict()
    with ExifTool() as et:
        for video_dir in video_dirs:
            serial = list(et.get_metadata(str(video_dir.joinpath('raw_video.mp4'))))[0]['QuickTime:CameraSerialNumber']
            # gripper calibration videos are wrist videos whatever camera recorded them
            is_wrist = serial in wrist_serials or video_dir.name.startswith('gripper_calibration')
            if wrist_only and (not is_wrist or video_dir.name == 'mapping'):
                log.info("%s: skipped (--wrist_only)", video_dir.name)
                continue
            video_intrinsics[video_dir] = serial_intrinsics.get(serial, camera_intrinsics)
            log.info("%s: intrinsics %s", video_dir.name, os.path.basename(video_intrinsics[video_dir]))

    todo = list()
    for video_dir in video_intrinsics:
        if video_dir.joinpath('tag_detection.pkl').is_file():
            log.info("tag_detection.pkl already exists, skipping %s", video_dir.name)
        else:
            todo.append(video_dir)

    t0 = time.time()
    executor = make_pool(num_workers)

    def submit(video_dir):
        video = str(video_dir.joinpath('raw_video.mp4'))
        with av.open(video) as container:
            stream = container.streams.video[0]
            resolution = np.array([stream.width, stream.height])
        return submit_chunked(executor, video, make_wrist_detector, (video_intrinsics[video_dir], aruco_yaml, resolution),
            desc=video_dir.name, chunks_per_worker=chunks_per_worker)

    def finish(video_dir, handle):
        results = gather_chunked(handle)
        atomic_pickle_dump(results, video_dir.joinpath('tag_detection.pkl'))
        log.info("saved %s (%d frames)", video_dir.joinpath('tag_detection.pkl'), len(results))

    try:
        failures = run_pipelined(todo, submit, finish, lookahead=2, errors=(PipelineError, OSError, av.error.FFmpegError))
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    for video_dir, e in failures:
        log.error("FAILED %s: %s", video_dir.name, e)
    log.info("wrist tag detection: %d videos, %d failed, %.1f s", len(todo), len(failures), time.time() - t0)
    # every selected video must have its detections
    failed = [x for x in video_intrinsics if not x.joinpath('tag_detection.pkl').is_file()]
    if failed:
        raise InputError(f"tag detection failed for {len(failed)} videos: {', '.join(x.name for x in failed)}")
    log.info("Done, %d videos have tag_detection.pkl", len(video_intrinsics))

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
