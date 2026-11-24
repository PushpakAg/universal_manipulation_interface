# Tag tracking pipeline: how it works, what it needs, what delivery needs

Summary of the repo walkthrough and the station1 / task01 validation run (2026-11-21 to 2026-11-23).
Sources: `README_tag_tracking.md`, `run_tag_tracking_pipeline.py`, `scripts_tag_tracking/*`, and the run itself.
The step-by-step record of that run (commands, times, results) is in `PIPELINE_RUN_LOG.md`.

## 1. What the pipeline does

UMI (Universal Manipulation Interface) records a person using handheld grippers. The original UMI gets gripper poses from wrist camera SLAM. This fork replaces that with **tag tracking**:

- A **head GoPro** watches one **ArUco cube** (4 tags, 70 mm cube, 60 mm tags) on each gripper.
- **Environment tags** on the table and walls give a fixed world frame (one is the origin, `anchor_tag`). Two **dock tags** mark where the grippers rest between episodes.
- **Wrist GoPros** (one per gripper) supply the gripper camera video, an IMU, and a view of the environment tags.
- **GTSAM** fuses head-tracked cube poses, the head IMU, and each wrist IMU plus wrist-seen environment tags into one gripper pose per frame (`visual_inertial.py`, `gripper_fusion.py`).
- A continuous take is cut into **episodes** between dock periods. Docking and the "bang" ritual at each end are trimmed. Wrist clocks are synchronized to the head camera from motion.

**Input:** original GoPro MP4 files (head, left wrist, right wrist), unedited, because serial number, timecode and GPMF IMU data live in the file metadata.
**Output:** `dataset_plan.pkl` (same format as the SLAM pipeline), one **MCAP** file per episode, and optionally an Odyssey delivery package.

## 2. Inputs, exactly

Session layout (a "session" is one task):

```
<session>/raw_videos/*.MP4                      head and wrist take videos
<session>/raw_videos/gripper_calibration/*.MP4  one open/close clip per wrist camera
<session>/raw_videos/head_mapping/*.MP4         head camera walking past all environment tags
<session>/raw_videos/pairs.csv                  which videos were recorded together
```

Also needed:

| Item | Why |
|---|---|
| Tag tracking config, e.g. `example/tag_tracking/tag_tracking_station1.yaml` | camera roles by serial (head, right wrist = robot 0, left wrist = robot 1), dock tags, episode boundary rule, IMU settings, `setup_calibration` |
| Setup calibration, e.g. `example/tag_tracking/setup_station1/` | tag map, cube geometry, gripper TCP. Valid only while tags, cubes and camera mounts are unchanged |
| Camera intrinsics and camera-IMU calibration per GoPro | in `example/tag_tracking/` |
| Tag corner noise model | once per camera model |
| Docker image `chicheng/openicc:latest` | IMU extraction step. amd64 only, so Apple silicon needs Colima + Rosetta with `DOCKER_DEFAULT_PLATFORM=linux/amd64` |
| Python env: gtsam 4.2, mcap 1.6, opencv-contrib 4.7 (needs `cv2.aruco`), av, zarr, pyarrow | |

`gripper_calibration/` is required by `--strict`. `head_mapping/` is only needed when there is no stored setup calibration. `mapping.mp4` is not used.

## 3. Pipeline steps

`run_tag_tracking_pipeline.py -c <config> -nr <session>` runs these in order. Each step writes `<session>/logs/<nn>_<name>.log`.

| Step | Script | Output |
|---|---|---|
| sort_videos | `scripts_slam_pipeline/00_process_videos.py --strict` | `demos/*/raw_video.mp4` (raw_videos become symlinks) |
| imu | `01_extract_gopro_imu.py` (Docker) | `demos/*/imu_data.json` |
| wrist_tags | `04_detect_aruco.py --wrist_only` | wrist `tag_detection.pkl` |
| gripper_range | `05_run_calibrations.py --skip_slam_tag` | `gripper_range.json` (finger width range) |
| audio_sync | `06a_estimate_audio_sync.py` | `audio_sync_offsets.json` (coarse head to wrist offset) |
| head_tags | `scripts_tag_tracking/00_detect_tag_corners.py` | head `tag_corners.pkl` |
| segment_episodes | `00b_segment_episodes.py` | `tag_tracking/episodes.json` |
| use_setup | `00c_use_setup.py` | `bodies.json`, `gripper_tcp.json` copied from the setup calibration |
| track_bodies | `03_track_bodies.py` | head `tag_tracking.pkl` (head and cube poses) |
| fuse_head_imu | `03b_fuse_head_imu.py` | head pose refined with the head IMU |
| trim_docking | `03t_trim_docking.py` | task start / end without docking |
| sync_wrists | `03s_sync_wrists.py` | `wrist_sync.json` (fine wrist clock correction from motion) |
| fuse_grippers | `03c_fuse_gripper_imu.py` | final gripper poses |
| render | `04_render_tracking.py` | review video (skipped with `-nr`) |
| export_plan | `06_export_dataset_plan.py` | `dataset_plan.pkl` |

`calibrate_bodies` and `gripper_tcp` run only when there is no `setup_calibration`.
After the pipeline: `06_export_dataset_plan.py --keep_gaps` (keep episodes with tracking gaps, frames without a pose marked invalid), then `07_export_mcap.py -j 4`.

`scripts_tag_tracking/process_station.py` wraps all of this per station: download, pipeline, `--keep_gaps` plan, MCAP, and optionally `--upload` and `--cleanup`. `--cleanup` deletes local videos and MCAP only after a size-verified S3 upload. Do not use `--upload` or `--cleanup` without deciding to.

## 4. How the time synchronization works

1. **Audio sync (06a):** coarse head to wrist offset from audio.
2. **Motion sync (03s):** each wrist IMU is fitted to the rotation of its cube as tracked by the head camera. This gives a per-episode clock correction plus a drift line, with an accuracy figure in `wrist_sync.json`.
3. The wrist video is placed using that `imu_time_offset`.
4. **Check:** `check_frame_sync.py` compares each wrist camera's orientation from its own environment tags against the head cube orientation, with no IMU. One frame is 16.7 ms.

MCAP `sync` metadata holds `camera{c}_sync_frame`, `camera{c}_offset_ms` and `camera{c}_sync_sigma_ms`.

## 5. Output formats

**MCAP** (`dataset_mcap/episode_NNNNNN.mcap`, `robot0` right, `robot1` left, `camera0` robot0 wrist, `camera1` robot1 wrist, `camera2` head):

| Topic | Content |
|---|---|
| `robot{i}/eef/state`, `robot{i}/eef/pose` | TCP pose (axis-angle / quaternion), world frame |
| `robot{i}/gripper/state` | gripper width (m) |
| `robot{i}/eef_demo_start/state`, `..._end/state` | first / last TCP pose |
| `robot{i}/imu`, `/head/imu` | camera IMUs |
| `/cameras/camera{j}/video` | H.265 straight from the GoPro files, not re-encoded |
| `/head/pose` | head camera pose in the world |

Each camera's video starts at its own keyframe before the episode, so the three can start up to 1 s apart.

**Limitations (from the README):** with `--keep_gaps` the plan is not usable for the replay buffer. A task ends when the first gripper returns to the dock.

## 6. Checks available

| Script | What it tells you |
|---|---|
| `check_frame_sync.py` | wrist video sync error against the head, per episode |
| `check_frame_table.py` | structure of the exported tables, gripper pose vs head cube measurement, width range, coverage |
| `check_tcp_frame.py` (`--random N`, `-e list`) | image per episode: head frame and both wrist frames with the TCP drawn, to see by eye that the TCP sits at the fingertips |
| `11_check_quality.py` | per-episode pass / warn / fail (media, tracking, sync, annotations) into `tag_tracking/quality.json` |

## 7. What the Odyssey delivery needs

Odyssey Robotics Data Capture Spec v0.6, container `mcap`. Built by `13_export_delivery.py -i <session> -c <config> -d <delivery.yaml> -o <delivery_dir> -j 16` (needs `pyarrow`).

**Inputs**

1. A processed session with `dataset_plan.pkl` (use the `--keep_gaps` plan).
2. The session's tag tracking config.
3. A copy of `example/tag_tracking/delivery.yaml`, filled in. Anything left null is exported as null.
4. Optionally annotations (`08_annotate_episodes.py`, then `09_normalize_labels.py`). Both call the Anthropic API and need the `anthropic` package and `ANTHROPIC_API_KEY`. Without annotations there is no `annotations.json`, outcome is `unknown` and success is null.

**What only the recording team can supply (`delivery.yaml`)**

| Level | Fields |
|---|---|
| `delivery:` | vendor_name, dataset_name, delivery_id, robot_model, gripper_type, source_uri_prefix, license_reference, anonymization_state (`faces_blurred`, `not_required`, `pending`, `other`), consent_reference, schema_version `0.6` |
| per session (directory name) | task_text, task_family, object_tags, collection_mode (`scripted`, `freeform`, `adversarial`, `in_the_wild`), scene_tags, environment_id, operator_id, station_id, consent_reference |

**Output per episode** (`<delivery_dir>/<episode_id>/`)

| File | Content |
|---|---|
| `episode.mcap` | as above, message times in UTC |
| `episode.json` | ids, UTC start / end, frame rate, `clock_sync_accuracy_ns`, world frame, gripper range, task |
| `sensors.json` | per camera, IMU, TCP, gripper: topic, schema, units, clock offset, intrinsics, extrinsics |
| `frames.parquet` | one row per head frame: UTC time, TCP poses, `pose_valid`, gripper widths, head pose |
| `annotations.json` | event timeline (spec 2.7), only where annotated |
| `<delivery_dir>/manifest.parquet` | one row per episode with sizes and sha256, written last |

`episode_id` = head camera serial + UTC start of the head video + head frame of the episode start, so it is stable across re-exports. Only measured or declared values are written: lost tracking stays as null pose with `pose_valid` false.

`10_coverage_report.py` produces the hours / episodes / task-family coverage tables from annotations and the delivery yaml.

## 8. What was done on station1 / task01

Source: `s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/station1/industrial_data/task01/raw_videos/`, read with the `prod` profile into the git-ignored `data/` folder. 7 takes x 3 cameras, 2 gripper calibration clips, 1 head mapping clip.

| Stage | Result |
|---|---|
| Pipeline (153 min) | 14 steps ok. 24 episodes in the first plan, **28 episodes** with `--keep_gaps` (1261 s of 1828 s used) |
| MCAP export | 28 files, 7.8 GB |
| Frame sync check | 27 of 28 episodes measured. Right wrist median +3.7 ms, left +3.4 ms, wrist to wrist 0.0 ms. Only episode 16 right wrist is over half a frame (+10.2 ms). Episode 20 has no wrist environment-tag poses, so it is unmeasured |
| Frame table check | 0 structure errors. Position median at most 5.2 mm, rotation median at most 1.58 deg, 0 widths out of range |
| TCP frame check | all 28 images made, episodes 16, 20, 25 viewed. Odd heights are explained (episode 20 is the docked pose, episode 25 is table contact) |
| Quality report | **crashed**, see below |
| Annotations | `--dry_run` only: 29 frame sheets and request texts, no API call |

## 9. Open items and gotchas

- **Quality report crash.** `umi/tag_tracking/quality.py:266` compares against `accuracy_ms`, which is `null` in `wrist_sync.json` for 4 of the 7 head videos. Needs a decision on what status unknown accuracy gets. Image statistics are already cached. Warnings seen before the crash: every video is 59.94 Hz ("not an integer rate"), and the right wrist of the 13.49.41 recording shows 14 skipped frames.
- **Episode 20 and 16** sync: unmeasured and +10.2 ms respectively.
- **29 vs 28 episodes:** annotation dry run covers 29 episodes with a task interval, the plan has 28. Not explained yet.
- **Delivery not built:** needs the filled `delivery.yaml` and, ideally, annotations. `13_export_delivery.py` says `validation_status` is `not_run`; the docstring of `11_check_quality.py` says the delivery takes it from `quality.json`. Not verified which holds.
- **Annotations need an API key and send frames to the Anthropic API.** Review the dry-run frame sheets first.
- **tool_handling session** stopped at the `imu` step: its right-wrist calibration clip was recorded by camera `C3501325427851`, which is in no config.
- **Test bug:** `tests/test_setup_calibration.py` uses a missing `executor` fixture. Not an environment problem.
- **Environment lessons (macOS arm64):** `av==10` has no wheel (used 12.x); `numcodecs` pin fails to build (unpinned); only `opencv-contrib-python==4.7.0.72` has the aruco API this code uses; AWS SSO tokens expire mid-download, and `aws s3 sync` resumes.

## 10. Where things are

| What | Where |
|---|---|
| Run record (commands, times, results) | `PIPELINE_RUN_LOG.md` (git-ignored) |
| Earlier free-form log | `PROCESSING_LOG.md` (git-ignored) |
| Processed data | `data/station1/industrial_data/task01/` (git-ignored) |
| Logs of every step and check | `data/station1/industrial_data/task01/logs/` |
| Check images | `.../task01/tag_tracking/tcp_check_ep*.png` |
| Dry-run annotation sheets | `.../task01/tag_tracking/annotations/` |
