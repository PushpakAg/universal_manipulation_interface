"""
ArUco corner detection (v2 of umi/tag_tracking/tag_detection.py).

Changes against the original:
- the detector parameters are built once per worker, not per frame;
- detect_scale < 1 searches for markers on a downscaled frame and refines the corners of the
  found markers at full resolution (cv2.cornerSubPix, same window / criteria as ArUco's SUBPIX).
  Profile: the marker search over the full 2.7K image costs ~95 ms/frame and the sub-pixel refinement
  almost nothing, so the search resolution is what to cut (half resolution: ~3x faster).
  detect_scale = 1.0 (default) is the original algorithm, results identical. Below 1.0 recall of
  small / distant tags and corner accuracy must be checked with scripts_tag_tracking/compare_detection.py
  before use on delivery data;
- video detection uses tt2.video_chunk (shared pool, more chunks than workers).
"""
from typing import Dict, Optional, Sequence, Set
import os
import cv2
import numpy as np
from tt2.video_chunk import process_video_chunked

SUBPIX_WIN = (5, 5)
SUBPIX_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_COUNT, 30, 0.1)


def get_tag_object_points(tag_size: float) -> np.ndarray:
    """
    (4,3) tag corners in the tag frame, in ArUco detection order,
    same convention as cv2.SOLVEPNP_IPPE_SQUARE (z out of the tag).
    """
    h = tag_size / 2
    return np.array([
        [-h, h, 0],
        [h, h, 0],
        [h, -h, 0],
        [-h, -h, 0]
    ], dtype=np.float64)


def make_parameters(subpix: bool = True) -> cv2.aruco.DetectorParameters:
    param = cv2.aruco.DetectorParameters()
    param.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX if subpix else cv2.aruco.CORNER_REFINE_NONE
    return param


def detect_tag_corners_scaled(img: np.ndarray, aruco_dict: cv2.aruco.Dictionary, tag_ids: Optional[Set[int]],
        scale: float, param_coarse: cv2.aruco.DetectorParameters) -> Dict[int, np.ndarray]:
    """
    Coarse-to-fine detection: markers on the image resized by `scale` (no refinement), corners mapped
    back and refined at full resolution with cornerSubPix.
    """
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    corners, ids, _ = cv2.aruco.detectMarkers(image=small, dictionary=aruco_dict, parameters=param_coarse)
    result = dict()
    if ids is None:
        return result
    for tag_id, c in zip(ids.flatten(), corners):
        tag_id = int(tag_id)
        if tag_ids is not None and tag_id not in tag_ids:
            continue
        full = (c.reshape(4, 1, 2) / scale).astype(np.float32)
        cv2.cornerSubPix(img, full, SUBPIX_WIN, (-1, -1), SUBPIX_CRITERIA)
        result[tag_id] = full.reshape(4, 2).astype(np.float64)
    return result


def detect_tag_corners(
        img: np.ndarray,
        aruco_dict: cv2.aruco.Dictionary,
        tag_ids: Optional[Set[int]] = None,
        param: Optional[cv2.aruco.DetectorParameters] = None
        ) -> Dict[int, np.ndarray]:
    """
    Detect ArUco tags with sub-pixel corner refinement, same detector
    settings as umi.common.cv_util.detect_localize_aruco_tags.
    No single-tag pose is computed here: a single planar tag has
    two ambiguous poses, poses are estimated jointly downstream.

    Returns: tag id -> (4,2) corner pixel coordinates
    """
    if param is None:
        param = make_parameters()
    corners, ids, _ = cv2.aruco.detectMarkers(
        image=img, dictionary=aruco_dict, parameters=param)
    result = dict()
    if ids is None:
        return result
    for tag_id, tag_corners in zip(ids.flatten(), corners):
        tag_id = int(tag_id)
        if (tag_ids is None) or (tag_id in tag_ids):
            result[tag_id] = tag_corners.reshape(4, 2).astype(np.float64)
    return result


def make_corner_detector(dict_bytes: np.ndarray, marker_size: int, max_correction_bits: int,
        tag_ids: Optional[Set[int]], detect_scale: float = 1.0):
    """
    Per frame corner detector, built in each worker process
    (cv2.aruco.Dictionary is not picklable, it is rebuilt from its parts).
    """
    cv2.setNumThreads(1)
    aruco_dict = cv2.aruco.Dictionary(dict_bytes, marker_size, max_correction_bits)
    param = make_parameters(subpix=detect_scale >= 1.0)

    def detect(frame, time):
        gray = frame.to_ndarray(format='gray')
        if detect_scale >= 1.0:
            return {'time': time, 'corners': detect_tag_corners(gray, aruco_dict, tag_ids, param)}
        return {'time': time, 'corners': detect_tag_corners_scaled(gray, aruco_dict, tag_ids, detect_scale, param)}
    return detect


def detect_video_tag_corners(
        video_path: str,
        aruco_dict: cv2.aruco.Dictionary,
        tag_ids: Optional[Set[int]] = None,
        num_workers: Optional[int] = None,
        detect_scale: float = 1.0,
        executor=None,
        chunks_per_worker: int = 4
        ) -> list:
    """
    Tag corners for every frame of a video, on raw decoded frames
    (no rotation metadata applied, matching the camera calibration).
    Frames are processed in parallel time chunks on num_workers processes,
    default all cores (umi.common.video_chunk_util).
    Returns per frame {'frame_idx', 'time', 'corners'}.
    """
    video_path = os.path.expanduser(video_path)
    return process_video_chunked(video_path, make_corner_detector,
        (aruco_dict.bytesList, aruco_dict.markerSize, aruco_dict.maxCorrectionBits, tag_ids, detect_scale),
        num_workers=num_workers, desc=os.path.basename(os.path.dirname(os.path.abspath(video_path))),
        executor=executor, chunks_per_worker=chunks_per_worker)


def submit_video_tag_corners(executor, video_path: str, aruco_dict, tag_ids=None, detect_scale: float = 1.0,
        chunks_per_worker: int = 4) -> dict:
    """Submit the detection of one video to a shared pool; collect with tt2.video_chunk.gather_chunked."""
    from tt2.video_chunk import submit_chunked
    video_path = os.path.expanduser(video_path)
    return submit_chunked(executor, video_path, make_corner_detector,
        (aruco_dict.bytesList, aruco_dict.markerSize, aruco_dict.maxCorrectionBits, tag_ids, detect_scale),
        desc=os.path.basename(os.path.dirname(os.path.abspath(video_path))), chunks_per_worker=chunks_per_worker)


def tag_inventory(detections: Sequence[Dict[int, np.ndarray]], image_size: Sequence[int]) -> Dict[int, dict]:
    """
    Which tags a video shows, from per-frame detections (detect_tag_corners of
    sampled frames): per tag id the share of frames it is in, its median side
    length (px) and its median center in the image (0..1, x right, y down).
    Finger tags sit at a fixed spot near the bottom of a wrist image, cube and
    environment tags move around.
    """
    w, h = image_size
    seen = dict()
    for corners in detections:
        for tag_id, c in corners.items():
            side = float(np.mean(np.linalg.norm(c - np.roll(c, 1, axis=0), axis=1)))
            center = c.mean(axis=0) / np.array([w, h])
            seen.setdefault(int(tag_id), list()).append((side, center[0], center[1]))
    out = dict()
    for tag_id in sorted(seen):
        x = np.array(seen[tag_id])
        out[tag_id] = {'share': len(x) / max(len(detections), 1), 'side_px': float(np.median(x[:, 0])),
            'center': (float(np.median(x[:, 1])), float(np.median(x[:, 2])))}
    return out


def sample_detections(path: str, predefined: str, every_sec: float, max_sec: Optional[float] = None) -> dict:
    """
    Tag corners (detect_tag_corners) of one frame every every_sec seconds of a
    video, up to max_sec. Returns {'duration': s, 'size': (w, h), 'detections': [...]},
    detections[i] at i * every_sec.
    """
    import av
    import av.logging
    av.logging.set_level(av.logging.ERROR)   # swscaler 'deprecated pixel format' per frame
    cv2.setNumThreads(1)
    aruco_dict = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, predefined))
    detections = list()
    # URLs (presigned S3): reconnect when the connection drops mid-read
    options = {'reconnect': '1', 'reconnect_on_network_error': '1', 'reconnect_delay_max': '10'} \
        if str(path).startswith('http') else None
    with av.open(str(path), options=options) as container:
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'
        duration = float(stream.frames / stream.average_rate)
        size = (stream.codec_context.width, stream.codec_context.height)
        end = duration if max_sec is None else min(duration, max_sec)
        for t in np.arange(0.0, end, every_sec):
            container.seek(int(t / stream.time_base), stream=stream)
            for frame in container.decode(stream):
                if float(frame.pts * stream.time_base) >= t - 0.5 / float(stream.average_rate):
                    detections.append(detect_tag_corners(frame.to_ndarray(format='gray'), aruco_dict))
                    break
    return {'duration': duration, 'size': size, 'detections': detections}
