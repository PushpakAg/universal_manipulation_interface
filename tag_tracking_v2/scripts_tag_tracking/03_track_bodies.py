"""
Per frame pose of every calibrated body in each head camera task video (v2 of 03_track_bodies.py).
(demos/demo_*; the head_mapping walk is only used for calibration).
The static body (environment) gives the head camera pose in the world; moving bodies (gripper
cubes) are expressed in the head camera frame and, where the head pose is known, in the world
frame. Covariances are propagated to the world frame; a pose is valid if its uncertainty meets
the accuracy in the config.
With episodes (tag_tracking/episodes.json from 00b_segment_episodes.py), only frames within
--margin seconds of an episode are tracked (others NaN), unless --whole_take.
Writes tag_tracking.pkl next to each tag_corners.pkl (atomically), with the tracked frame windows
('windows', used by 03b_fuse_head_imu.py).

Scheduling (the change against the original): the chunks of ALL bodies of a video are submitted to
the pool at once, and the next video is submitted before the current one is post-processed
(covariance propagation runs in the main process), so the workers do not wait for the main process
or for the slowest chunk of one body. Numerical results are identical to the original.
A video that fails is logged, the others continue; exit code 1 if any failed.

python tag_tracking_v2/scripts_tag_tracking/03_track_bodies.py -i data_workspace/session -c umi_calib/tag_tracking.yaml
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
import json
import pickle
import time
import click
import numpy as np
from umi.tag_tracking.config import load_tag_tracking_config
from umi.tag_tracking.windows import episode_windows, window_frames, scatter
from umi.tag_tracking.noise_model import TagNoiseModel
from umi.tag_tracking.uncertainty import (
    inverse_covariance,
    compose_covariance,
    pose_std
)
from tt2.parallel import make_executor, submit_track_bodies, gather_track_bodies, CHUNKS_PER_WORKER
from tt2.errors import InputError, PipelineError, require
from tt2.fsutil import atomic_pickle_dump
from tt2.log import setup_logging, get_logger

log = get_logger(__name__)


def prepare(corner_path, episodes, margin, camera, calibration, config, noise_model, line_delay, executor, n_chunks):
    """Load one video's detections, select the frames to track, submit all bodies' tracking."""
    detections = pickle.load(corner_path.open('rb'))
    frames = [{'time': x['time'], 'corners': x['corners'], 'sequence': 0} for x in detections]
    times = np.array([x['time'] for x in detections])
    video_episodes = None
    if episodes is not None and corner_path.parent.name in episodes:
        video_episodes = episodes[corner_path.parent.name]['episodes']
    windows = episode_windows(times, video_episodes, margin)
    selected, idx = window_frames(frames, windows)
    log.info("%s: tracking %d of %d frames in %d windows", corner_path.parent.name, len(selected), len(frames),
        len(windows))
    bodies = {name: {int(k): np.array(v) for k, v in body['T_body_tags'].items()}
        for name, body in calibration['bodies'].items()}
    submitted = submit_track_bodies(executor, camera, selected, bodies, config['tag_sizes'], noise_model,
        line_delay, n_chunks)
    return {'path': corner_path, 'frames': frames, 'times': times, 'windows': windows, 'selected': selected,
        'idx': idx, 'submitted': submitted}


def finish(prep, config, calibration):
    """Gather the tracking, propagate to the world frame, write tag_tracking.pkl."""
    corner_path, frames, times, windows = prep['path'], prep['frames'], prep['times'], prep['windows']
    selected, idx = prep['selected'], prep['idx']
    tracks = gather_track_bodies(prep['submitted'])
    result = {
        'time': times,
        'camera_serial': config['head_camera'],
        'windows': windows,
        'bodies': dict()
    }
    accuracy = config['accuracy']
    is_accurate = lambda position_std, rotation_std: (position_std <= accuracy['position_std']) \
        & (rotation_std <= accuracy['rotation_std_rad'])
    n = len(frames)

    static_name = None
    for name, body in calibration['bodies'].items():
        track = scatter(len(frames), idx, tracks[name])
        # body pose in the camera frame accepted if its uncertainty meets the accuracy
        track['is_valid'] = is_accurate(track['position_std'], track['rotation_std'])
        result['bodies'][name] = track
        if body['static']:
            static_name = name
    if static_name is not None:
        # head camera pose in the world (static body frame)
        env = result['bodies'][static_name]
        head = {
            'T_world_cam': np.full((n, 4, 4), np.nan),
            'covariance': np.full((n, 6, 6), np.nan),
            'position_std': np.full(n, np.nan),
            'rotation_std': np.full(n, np.nan)
        }
        for i in np.flatnonzero(~np.isnan(env['T_cam_body'][:, 0, 0])):
            head['T_world_cam'][i] = np.linalg.inv(env['T_cam_body'][i])
            head['covariance'][i] = inverse_covariance(env['T_cam_body'][i], env['covariance'][i])
            head['position_std'][i], head['rotation_std'][i] = pose_std(
                head['T_world_cam'][i], head['covariance'][i])
        head['is_valid'] = is_accurate(head['position_std'], head['rotation_std'])
        result['head'] = head

        # moving bodies in the world, head and body uncertainty combined
        for name, track in result['bodies'].items():
            if name == static_name:
                continue
            track['T_world_body'] = np.full((n, 4, 4), np.nan)
            track['world_covariance'] = np.full((n, 6, 6), np.nan)
            track['world_position_std'] = np.full(n, np.nan)
            track['world_rotation_std'] = np.full(n, np.nan)
            both = ~np.isnan(head['T_world_cam'][:, 0, 0]) & ~np.isnan(track['T_cam_body'][:, 0, 0])
            for i in np.flatnonzero(both):
                track['T_world_body'][i] = head['T_world_cam'][i] @ track['T_cam_body'][i]
                track['world_covariance'][i] = compose_covariance(head['T_world_cam'][i],
                    head['covariance'][i], track['T_cam_body'][i], track['covariance'][i])
                track['world_position_std'][i], track['world_rotation_std'][i] = pose_std(
                    track['T_world_body'][i], track['world_covariance'][i])
            track['is_valid_world'] = is_accurate(track['world_position_std'], track['world_rotation_std'])

    tag_ids = lambda name: {int(k) for k in calibration['bodies'][name]['T_body_tags']}
    # statistics over the tracked frames
    tag_visible = lambda name: np.mean([len(tag_ids(name) & set(f['corners'])) > 0 for f in selected]) * 100
    for name, track in result['bodies'].items():
        if name == static_name:
            continue
        estimated = ~np.isnan(track['T_cam_body'][:, 0, 0])
        log.info(f"{corner_path.parent.name} {name}: tag visible {tag_visible(name):.0f}%, "
            f"estimated {estimated[idx].mean() * 100:.0f}%, valid in head frame {track['is_valid'][idx].mean() * 100:.0f}% "
            f"(median std {np.nanmedian(track['position_std']) * 1000:.1f} mm, "
            f"{np.degrees(np.nanmedian(track['rotation_std'])):.2f} deg)"
            + (f", valid in world {track['is_valid_world'][idx].mean() * 100:.0f}%" if 'is_valid_world' in track else ''))
    if static_name is not None:
        head = result['head']
        log.info(f"{corner_path.parent.name} head in world: tag visible {tag_visible(static_name):.0f}%, "
            f"estimated {(~np.isnan(head['T_world_cam'][idx, 0, 0])).mean() * 100:.0f}%, valid {head['is_valid'][idx].mean() * 100:.0f}% "
            f"(median std {np.nanmedian(head['position_std']) * 1000:.1f} mm, "
            f"{np.degrees(np.nanmedian(head['rotation_std'])):.2f} deg)")
    output = corner_path.parent.joinpath('tag_tracking.pkl')
    atomic_pickle_dump(result, output)
    log.info("Saved to %s", output)


# %%
@click.command()
@click.option('-i', '--input', required=True, help='Session directory')
@click.option('-c', '--config', required=True, help='Tag tracking config yaml')
@click.option('-m', '--margin', type=float, default=0.5, help='Track this long before / after each episode (s)')
@click.option('-wt', '--whole_take', is_flag=True, default=False, help='Track all frames, ignore episodes.json')
@click.option('-j', '--num_workers', type=int, default=None, help='Worker processes, default all cores')
def main(input, config, margin, whole_take, num_workers):
    setup_logging()
    session = user_path(input)
    require(session.is_dir(), f"session folder not found: {session}")
    config = load_tag_tracking_config(str(user_path(config)))
    camera = config['head_camera']
    camera = config['cameras'][camera]
    bodies_path = session.joinpath('tag_tracking', 'bodies.json')
    require(bodies_path.is_file(), f"{bodies_path} not found: run the calibration step (00c_use_setup / 02_calibrate_bodies) first")
    calibration = json.load(bodies_path.open('r'))
    noise_model = TagNoiseModel.from_dict(calibration['noise_model'])
    line_delay = calibration['line_delay']

    episodes = None
    episodes_path = session.joinpath('tag_tracking', 'episodes.json')
    if not whole_take and 'episodes' in config:
        require(episodes_path.is_file(), "run 00b_segment_episodes.py first, or --whole_take")
        episodes = json.load(episodes_path.open('r'))['videos']
    corner_paths = sorted(session.glob('demos/demo_*/tag_corners.pkl'))
    require(corner_paths, f"no demos/demo_*/tag_corners.pkl in {session}: run the head_tags step first")
    executor = make_executor(num_workers)
    n_chunks = executor._max_workers * CHUNKS_PER_WORKER
    t0 = time.time()
    failed = list()

    pending = None   # (path, prepared) of the video submitted ahead
    try:
        for k, corner_path in enumerate(corner_paths + [None]):
            current, pending = pending, None
            if corner_path is not None:
                try:
                    pending = prepare(corner_path, episodes, margin, camera, calibration, config, noise_model,
                        line_delay, executor, n_chunks)
                except (PipelineError, OSError, pickle.UnpicklingError, KeyError) as e:
                    log.error("%s: cannot start tracking: %s", corner_path.parent.name, e)
                    failed.append(corner_path.parent.name)
            if current is not None:
                try:
                    finish(current, config, calibration)
                except (PipelineError, OSError) as e:
                    log.error("%s: tracking failed: %s", current['path'].parent.name, e)
                    failed.append(current['path'].parent.name)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    log.info("track_bodies: %d videos, %d failed, %.1f s", len(corner_paths), len(failed), time.time() - t0)
    if failed:
        raise InputError(f"tracking failed for {len(failed)} videos: {', '.join(failed)}")

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
