# Calibration and video processing commands (tag tracking)

Run from the repo root. Source: `README_tag_tracking.md`. Not yet run.

`example/tag_tracking/tag_tracking.yaml` already points at a calibration
(`setup_calibration: setup_20261116`). Recalibrate only if the physical setup changed
(tags moved, cube or camera re-mounted).

## Session layout

```
<session>/raw_videos/*.MP4                      head + wrist videos of the take(s)
<session>/raw_videos/gripper_calibration/*.MP4  one open/close video per wrist camera
<session>/raw_videos/head_mapping/*.MP4         head camera walk past all env tags
```

## A. Recalibrate on a new task recording

```bash
cd /Users/kgen/Projects/universal_manipulation_interface

# 1. Edit tag_tracking.yaml: remove (or comment out) the line
#      setup_calibration: setup_20261116

# 2. Sort videos, detect tags, split into episodes
python run_tag_tracking_pipeline.py -c example/tag_tracking/tag_tracking.yaml \
  --stop_after segment_episodes <session>

# 3. Check episode detection (plots in <session>/tag_tracking/wrist_events/)
python scripts_tag_tracking/check_wrist_events.py -i <session> \
  -c example/tag_tracking/tag_tracking.yaml

# 4. Run the calibration (tag map, cube shapes, cube -> wrist -> TCP)
python scripts_tag_tracking/calibrate_setup.py -i <session> \
  -c example/tag_tracking/tag_tracking.yaml \
  -o example/tag_tracking/setup_$(date +%Y%m%d) -j 24

# 5. Edit tag_tracking.yaml: setup_calibration: setup_<date>

# 6. Check the TCP
python scripts_tag_tracking/check_tcp_frame.py -i <session> \
  -c example/tag_tracking/tag_tracking.yaml
```

After changing only the TCP geometry in `gripper_config.yaml`:

```bash
python scripts_tag_tracking/calibrate_setup.py -c example/tag_tracking/tag_tracking.yaml \
  -o example/tag_tracking/setup_20261116 --tcp_only
```

Corner noise (once per camera model, static camera looking at static tags):

```bash
python scripts_tag_tracking/01_measure_corner_noise.py \
  -i <static_video.MP4> -c example/tag_tracking/tag_tracking.yaml
```

## B. Process task recordings with the existing calibration

```bash
python run_tag_tracking_pipeline.py -c example/tag_tracking/tag_tracking.yaml -j 16 -nr <session>
python scripts_tag_tracking/07_export_mcap.py -i <session> -j 4
python scripts_slam_pipeline/07_generate_replay_buffer.py --no_mirror -o <dataset.zarr.zip> <session>
```

- `-nr` skips rendering; `--start_from <step>` / `--stop_after <step>` run a range.
- Steps: `sort_videos imu wrist_tags gripper_range audio_sync head_tags segment_episodes
  use_setup calibrate_bodies track_bodies fuse_head_imu gripper_tcp fuse_grippers render export_plan`.
- Logs: `<session>/logs/`.

After a TCP change, without re-tracking:

```bash
python scripts_tag_tracking/00c_use_setup.py -i <session> -c example/tag_tracking/tag_tracking.yaml
python scripts_tag_tracking/06_export_dataset_plan.py -i <session> -c example/tag_tracking/tag_tracking.yaml
python scripts_tag_tracking/07_export_mcap.py -i <session> -j 4
```

## Notes

- If episodes are missed, tune the `episodes:` block in `tag_tracking.yaml`.
- Each episode needs a clear bang at its start and end, or it is rejected.
- Camera intrinsics and camera-IMU calibration use OpenICC (`docker pull chicheng/openicc:latest`).
- Original SLAM pipeline: `python run_slam_pipeline_synced.py <session_dir>`.
