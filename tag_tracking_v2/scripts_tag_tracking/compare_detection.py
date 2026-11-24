"""
Compare tag detection at reduced search resolution against full resolution on real frames.

Decides whether --detect_scale < 1 may be used: for each scale it reports, over sampled frames,
- time per frame (single process, detection only);
- recall: share of the (frame, tag id) detections of the full-resolution run that are also found;
- extra: detections found at the scale but not at full resolution (false positives would show here);
- corner error against full resolution (mean, 95th percentile, max, in pixels).
A scale is usable if recall is ~100% on the tags that matter and the corner error is a small
fraction of the tracking noise (compare with `median std` in the 03_track_bodies log).
The output is a table in the log and, with -o, a json file.

python tag_tracking_v2/scripts_tag_tracking/compare_detection.py -v data/.../demo_X/raw_video.mp4 -c example/tag_tracking/tag_tracking_station1.yaml --frames 300
"""
# %%
import sys
import pathlib

V2_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V2_ROOT))
from tt2.bootstrap import setup_paths, user_path
setup_paths()

# %%
import json
import time
import av
import av.logging
import click
import cv2
import numpy as np
from umi.tag_tracking.config import load_tag_tracking_config
from tt2.errors import PipelineError, require
from tt2.fsutil import atomic_json_dump
from tt2.log import setup_logging, get_logger
from tt2.tag_detection import detect_tag_corners, detect_tag_corners_scaled, make_parameters

log = get_logger(__name__)


def sample_gray_frames(video: str, n_frames: int, stride: int) -> list:
    """n_frames gray frames, every `stride`-th frame from the start of the video."""
    av.logging.set_level(av.logging.ERROR)
    out = []
    with av.open(video) as container:
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'
        for i, frame in enumerate(container.decode(stream)):
            if i % stride == 0:
                out.append(frame.to_ndarray(format='gray'))
            if len(out) >= n_frames:
                break
    return out


def compare(frames, aruco_dict, tag_ids, scales) -> list:
    """Per scale: time, recall, extra, corner error statistics against the full resolution detections."""
    cv2.setNumThreads(1)
    full_param = make_parameters(subpix=True)
    t = time.time()
    reference = [detect_tag_corners(g, aruco_dict, tag_ids, full_param) for g in frames]
    rows = [{'scale': 1.0, 'ms_per_frame': (time.time() - t) / len(frames) * 1000, 'recall': 1.0, 'extra': 0,
        'err_mean_px': 0.0, 'err_p95_px': 0.0, 'err_max_px': 0.0,
        'detections': int(sum(len(r) for r in reference))}]
    coarse_param = make_parameters(subpix=False)
    for scale in scales:
        t = time.time()
        found = [detect_tag_corners_scaled(g, aruco_dict, tag_ids, scale, coarse_param) for g in frames]
        ms = (time.time() - t) / len(frames) * 1000
        hit, total, extra, errors = 0, 0, 0, []
        for ref, got in zip(reference, found):
            total += len(ref)
            extra += len(set(got) - set(ref))
            for k in set(ref) & set(got):
                hit += 1
                errors.append(np.linalg.norm(ref[k] - got[k], axis=1))
        err = np.concatenate(errors) if errors else np.zeros(1)
        rows.append({'scale': scale, 'ms_per_frame': ms, 'recall': hit / max(total, 1), 'extra': extra,
            'err_mean_px': float(err.mean()), 'err_p95_px': float(np.percentile(err, 95)), 'err_max_px': float(err.max()),
            'detections': int(sum(len(r) for r in found))})
    return rows


# %%
@click.command()
@click.option('-v', '--video', required=True, help='Head video (raw_video.mp4)')
@click.option('-c', '--config', required=True, help='Tag tracking config yaml')
@click.option('--frames', type=click.IntRange(min=10), default=200, help='Number of frames to compare')
@click.option('--stride', type=click.IntRange(min=1), default=20, help='Take every n-th frame')
@click.option('--scales', default='0.75,0.5', help='Comma separated search scales below 1.0')
@click.option('-o', '--output', default=None, help='Write the table as json')
def main(video, config, frames, stride, scales, output):
    setup_logging()
    video = user_path(video)
    require(video.is_file(), f"video not found: {video}")
    try:
        scale_list = [float(x) for x in scales.split(',')]
    except ValueError:
        raise PipelineError(f"--scales must be comma separated numbers, got {scales!r}")
    require(all(0.2 <= x < 1.0 for x in scale_list), "scales must be in [0.2, 1.0)")
    config = load_tag_tracking_config(str(user_path(config)))
    gray = sample_gray_frames(str(video), frames, stride)
    require(len(gray) >= 10, f"only {len(gray)} frames could be read from {video}")
    log.info("%s: %d frames (every %d-th), %dx%d", video.parent.name, len(gray), stride, gray[0].shape[1], gray[0].shape[0])
    rows = compare(gray, config['aruco_dict'], config['known_tag_ids'], scale_list)
    log.info("scale  ms/frame  recall   extra  err mean / p95 / max (px)")
    for r in rows:
        log.info("%.2f   %7.1f   %5.1f%%  %6d  %.3f / %.3f / %.3f", r['scale'], r['ms_per_frame'], r['recall'] * 100,
            r['extra'], r['err_mean_px'], r['err_p95_px'], r['err_max_px'])
    if output:
        atomic_json_dump({'video': str(video), 'frames': len(gray), 'rows': rows}, user_path(output))

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
