"""
Per frame tag detection of wrist camera videos (the detector of scripts/detect_aruco.py, same output).

The original builds the mirror mask by drawing polygons into every frame (cv2.fillPoly on a 2704x2028x3 image,
about 7 ms of a 53 ms frame). Here the polygons are drawn once per worker into a one-channel mask and applied with
cv2.bitwise_and, which gives exactly the same pixels (fillPoly rasterises the same pixels whatever the colour or
channel count; the masked pixels are black in both). Everything else (rgb24 conversion, detectMarkers with sub-pixel
refinement, undistortion, single-marker pose) is the original code path (umi.common.cv_util.detect_localize_aruco_tags).
"""
import json
import cv2
import numpy as np
import yaml


def build_keep_mask(shape_hw, mirror=True, gripper=False, finger=False) -> np.ndarray:
    """uint8 mask, 0 where draw_predefined_mask would paint, 255 elsewhere."""
    from umi.common.cv_util import (get_mirror_canonical_polygon, get_gripper_canonical_polygon,
        get_finger_canonical_polygon, canonical_to_pixel_coords)
    polygons = []
    if mirror:
        polygons.extend(get_mirror_canonical_polygon())
    if gripper:
        polygons.extend(get_gripper_canonical_polygon())
    if finger:
        polygons.extend(get_finger_canonical_polygon())
    painted = np.zeros(tuple(shape_hw), dtype=np.uint8)
    for coords in polygons:
        pts = np.round(canonical_to_pixel_coords(coords, tuple(shape_hw))).astype(np.int32)
        cv2.fillPoly(painted, [pts], color=255, lineType=cv2.LINE_8)
    return cv2.bitwise_not(painted)


def apply_mask(img: np.ndarray, keep: np.ndarray) -> np.ndarray:
    return cv2.bitwise_and(img, img, mask=keep)


def make_wrist_detector(intrinsics_json, aruco_yaml, resolution):
    """Per frame detector built in each worker (OpenCV objects are not picklable)."""
    from umi.common.cv_util import (parse_aruco_config, parse_fisheye_intrinsics,
        convert_fisheye_intrinsics_resolution, detect_localize_aruco_tags)
    cv2.setNumThreads(1)
    aruco_config = parse_aruco_config(yaml.safe_load(open(aruco_yaml, 'r')))
    aruco_dict = aruco_config['aruco_dict']
    marker_size_map = aruco_config['marker_size_map']
    fisheye_intr = convert_fisheye_intrinsics_resolution(
        opencv_intr_dict=parse_fisheye_intrinsics(json.load(open(intrinsics_json, 'r'))),
        target_resolution=resolution)
    keep = build_keep_mask((int(resolution[1]), int(resolution[0])))

    def detect(frame, time):
        img = apply_mask(frame.to_ndarray(format='rgb24'), keep)
        tag_dict = detect_localize_aruco_tags(
            img=img,
            aruco_dict=aruco_dict,
            marker_size_map=marker_size_map,
            fisheye_intr_dict=fisheye_intr,
            refine_subpix=True
        )
        return {'time': time, 'tag_dict': tag_dict}
    return detect
