# Processing log: station1 / tool_handling

Run of the tag-tracking pipeline (README_tag_tracking.md, "End to end example") on the
station1 `tool_handling` recording. Local only, not tracked in git.

- Source: `s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/station1/tool_handling/raw_videos/` (AWS profile `prod`)
- Local session: `data/station1_tool_handling/` (git-ignored)
- Config: `example/tag_tracking/tag_tracking_station1.yaml` (setup calibration `setup_station1`)
- Code: branch `odyssey-delivery` at `2320cb8` (fast-forwarded from `26d8fdd`)

## 1. Input
7 videos, 6.6 GB: 2 head takes (GX010328, GX010329), right wrist take (GX019217), left wrist take
(GX019261), 2 gripper calibration clips, 1 head mapping clip. The data is already one sorted
session, so the sort step of the example (`sort_recordings.py`) is skipped.

## 2. Access and download
- No `prod` AWS profile existed; it was created with `aws configure sso` (SSO session HLStagePowerUserAccess) and `aws sso login --profile prod`.
- `aws s3 sync` of the `raw_videos/` prefix into `data/station1_tool_handling/raw_videos/`; sizes match S3.

## 3. Environment (macOS arm64, no conda)
- `.venv` (Python 3.10, uv): gtsam 4.2, mcap 1.6, opencv-contrib 4.7, numpy 1.24, av 12, zarr 2.18; exiftool via Homebrew.
- Pins differ from `conda_environment.yaml` where the exact version has no Mac wheel (av, numcodecs, zarr). OpenCV 4.7 is needed for `cv2.aruco.detectMarkers`.
- Tests: 80/81 tag-tracking tests pass; the one error is a missing `executor` fixture in `tests/test_setup_calibration.py` (test bug, not the environment).

## 4. Data check (camera serials, exiftool)
| Video | Serial | Role in station1 config |
|---|---|---|
| head take/mapping | C3501326502664 | head |
| GX019217 | C3501326500348 | right wrist |
| GX019261, calibration GX019254 | C3501326029433 | left wrist |
| calibration GX019211 | **C3501325427851** | not in any config |

Finding: the right wrist has no gripper calibration clip of its own: GX019211 was recorded by a
different camera. Effect on step `gripper_range` is still to be seen.
GX010328 is a real take (head restarted at 05:12:56 UTC; wrists recorded throughout).

## 5. Pipeline run (`process_station.py data -c ...station1.yaml --tasks station1_tool_handling --mcap`)
- `sort_videos`: OK, 7 `demos/` folders created (4 takes, 2 gripper calibration, 1 head mapping).
- `imu`: **FAILED**, `docker` not found. The step extracts the GoPro IMU with a Node script inside the image `chicheng/openicc:latest`. Nothing downstream can run without `imu_data.json`.

## 6. Docker for the `imu` step
- Installed Colima + Docker CLI (Homebrew), VM with Rosetta (`colima start --vm-type vz --vz-rosetta`, 6 CPU, 12 GB).
- `chicheng/openicc:latest` is amd64 only; it runs emulated, so set `DOCKER_DEFAULT_PLATFORM=linux/amd64` before running the pipeline.
- `imu` step re-run alone: OK, `imu_data.json` for all 7 demos in about 6 min.
- README install list is now complete (conda-equivalent venv, gtsam 4.2, mcap 1.6.0, openicc image). The configurable-board OpenICC image is only for camera calibration, not installed.

## 7. Second session: `station1/industrial_data/task01` (the one processed end to end)
- Source: `s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/station1/industrial_data/task01/raw_videos/` (prod profile), downloaded to `data/station1/industrial_data/task01/` (11 GB, git-ignored). The SSO token expired once mid-download; re-login and `aws s3 sync` resumed it.
- Input: 24 videos + `pairs.csv`: 7 takes, each head + left wrist + right wrist (recordings 3, 4, 9-12, 14; 76 s to 9.5 min each), 2 gripper calibration clips, 1 head mapping clip.
- Serial check: head C3501326502664, right wrist C3501326500348, left wrist C3501326029433. Both calibration clips come from the right cameras (no repeat of the mismatch seen in `tool_handling`). Take 11: right wrist stopped after 1.7 min of 4.7.
- Command: `process_station.py data/station1/industrial_data -c example/tag_tracking/tag_tracking_station1.yaml --tasks task01 --mcap` with `DOCKER_DEFAULT_PLATFORM=linux/amd64`; no upload, no cleanup.

### Steps and time (Mac, 8 cores, total 153 min)
sort_videos 23:02 | imu 11 min | wrist_tags 37 min | gripper_range + audio_sync 1 min | head_tags 20 min | segment_episodes + use_setup 1 min | track_bodies 43 min | fuse_head_imu 13 min | trim_docking, sync_wrists 1 min | fuse_grippers about 20 min | export_plan, `--keep_gaps` plan, MCAP export. The CPU was saturated throughout (every step already uses all cores), so extra workers would not have helped.

### Result
- Plan without gaps: 24 episodes, 838 s of 1828 s used (46%).
- Plan with `--keep_gaps` (episodes with short tracking gaps kept, pose marked not available there): **28 episodes, 1261 s of 1828 s used (69%), 28 MCAP files, 7.8 GB** in `dataset_mcap/`.
- Each MCAP has 3 video topics (2704x2028 H.265), TCP pose and state, head pose, head and wrist IMU. Camera frame counts and pose counts agree within a few frames.
- Pose tracking: head and cubes valid in 92-100% of frames per take; wrist-clock corrections small (about 9 ms); head-to-wrist audio lag about 35 ms.
- Why time was not used: bang/dock trimming removes the dock pick-up and put-back (typically 4-5 s each side); one episode of take 11 is partly outside the right wrist recording; others dropped for tracking gaps over 0.25 s (longest 11.9 s in one episode of take 12), kept by `--keep_gaps` where short.
- Review flags: one episode with a large dock trim (13 s task after 35 s + 48 s removed).

### Not done
- Delivery package (`13_export_delivery.py`): needs a filled `delivery.yaml` (task text, operator/station ids, outcome).
- Checks (`check_tcp_frame.py`, `check_frame_sync.py`), annotations, quality report.
- Nothing uploaded; local videos kept.

## 8. Frame sync check (one episode)
`check_frame_sync.py -i data/station1/industrial_data/task01 -c example/tag_tracking/tag_tracking_station1.yaml -e 3` (plan episode 3 = `dataset_mcap/episode_000003.mcap`, 29 s, 24 s run time). Compares each wrist camera's orientation from its own environment tags with the head video's cube-based orientation; no IMU involved.
| Wrist | Frames used | Median rotation | Video sync error | Mismatch at best shift | IMU vs wrist video |
|---|---|---|---|---|---|
| right (C3501326500348) | 235 | 48 deg/s | +3.5 ms (+0.21 frame) | 0.43 deg | +4.2 ms |
| left (C3501326029433) | 436 | 37 deg/s | +2.4 ms (+0.14 frame) | 0.39 deg | +3.8 ms |
Wrist to wrist: +1.1 ms. One frame is 16.7 ms; the mismatch at +-1 frame is 0.73-0.95 deg, about double the best, so the shift is resolved. Result: exported wrist frames are in sync with the head video within about 4 ms (under a quarter frame) for this episode. Single episode only; the other 27 are not checked.

### Frame sync check, all episodes
`check_frame_sync.py` on the whole session (log: `data/station1/industrial_data/task01/logs/check_frame_sync_all.log`): 27 of 28 episodes measured (54 wrist-episode pairs); episode 20 (the shortest, 801 frames) gave no result.
- Video sync error (+ = wrist frames stamped too early): right wrist median +3.7 ms (range +0.5..+10.2), left wrist median +3.4 ms (+1.0..+6.2). One frame = 16.7 ms.
- Only episode 16, right wrist, exceeds half a frame (+10.2 ms, 0.6 frame); everything else is under 8 ms.
- Wrist to wrist: median 0.0 ms (-3.7..+5.9, 23 episodes).
- IMU vs wrist video: median +4.2 ms (-10.0..+8.1).
- Only 3 of 54 pairs had low rotation (<10 deg/s), where the shift is less well determined.
- Result: exported wrist frames are in sync with the head video within about 4 ms typically, always within one frame. The consistent +3-4 ms bias (wrist stamped slightly early) is a possible small constant correction, not applied.

## Frame table and TCP frame checks (task01)
- `check_frame_table.py` (log `logs/check_frame_table.log`): 7 head videos, 14 robot rows. Structure OK in all (0 interval mismatches, 0 null-pattern mismatches, unit quaternions). Gripper pose vs head cube: position median <= 5.2 mm (worst 95% 16.0 mm), rotation median <= 1.58 deg. 0 widths outside calibrated range. Native pose valid >= 97.2% of wrist frames.
- Flags: one demo (13.49.46) right gripper has aligned pose in only 20.6% of rows (right cube tracked in 2791 of 13833 frames; likely right gripper idle or out of head view). One left row has lowest TCP -8.5 cm (1st percentile 0.5 cm, so a short outlier, not systematic).
- `check_tcp_frame.py --random 4 --seed 0` (episodes 7, 13, 16, 21): images in `tag_tracking/tcp_check_ep*.png`. Lowest TCP z 2.0 to 6.1 cm above the table, TCP dot at the fingertips in head and wrist views (ep 16 viewed).
