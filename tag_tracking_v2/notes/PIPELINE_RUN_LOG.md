# Pipeline run log: station1 / task01 (validation, not delivery)

Commands from README_tag_tracking.md "End to end example", in the order they ran.
Session: `data/station1/industrial_data/task01` (S3 source `s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/station1/industrial_data/task01/raw_videos/`, read with the `prod` profile, all processing local).
Config: `example/tag_tracking/tag_tracking_station1.yaml` (setup calibration `setup_station1`). Env: `.venv` (Python 3.10), Docker image `chicheng/openicc:latest` under Colima + Rosetta.
All times are local, 2026-11-21 / 2026-11-22. Step start/end come from the step log's file creation and last-write times, so they are accurate to about 1 s. Times for the setup stage (download, environment) were not recorded; see section 1.

## 1. Setup (times not recorded)

| Order | Command | Result |
|---|---|---|
| a | `aws s3 ls` / `aws s3 sync ... --profile prod` into `data/station1/industrial_data/task01/raw_videos/` | 21 take videos, 2 gripper calibration clips, 1 head mapping clip, `pairs.csv`. SSO token expired once mid-download (5 of 21 takes done); after re-login `sync` resumed and finished. |
| b | `python3.10 -m venv .venv` + pip installs | gtsam 4.2, opencv-contrib-python 4.7.0.72, av 12.x, numcodecs unpinned (pinned versions had no Mac wheel or failed to build). |
| c | Colima + docker install, `docker pull chicheng/openicc:latest`, `DOCKER_DEFAULT_PLATFORM=linux/amd64` | Image runs under Rosetta. |

Earlier trial on `station1_tool_handling` (2026-11-21 about 20:50): `sort_videos` and `imu` ran, then stopped. Its right-wrist calibration clip was recorded by camera `C3501325427851`, which is in no config. Not continued.

## 2. Pipeline (run through `scripts_tag_tracking/process_station.py`, one local session)

`process_station.py` ran this chain. Log of the whole run: `process_station.out` (total **153 min**, 2026-11-21 23:02:36 to 2026-11-22 01:35:24).

Main command, as printed in `process_station.out`:
`python run_tag_tracking_pipeline.py -c example/tag_tracking/tag_tracking_station1.yaml -nr data/station1/industrial_data/task01`

| # | Step | Script and key args | Start | End | Duration | Result |
|---|---|---|---|---|---|---|
| 00 | sort_videos | `scripts_slam_pipeline/00_process_videos.py <session> --strict` | 11-21 23:02:36 | 23:02:37 | 1 s | 24 MP4 found, sorted into `demos/`. `raw_videos/*.MP4` are now symlinks. No `mapping.mp4` (expected with `--strict`). |
| 01 | imu | `01_extract_gopro_imu.py <session>` (Docker) | 23:02:38 | 23:13:19 | 10 min 41 s | 24 of 24 videos, IMU extracted. |
| 02 | wrist_tags | `04_detect_aruco.py --wrist_only ...` | 23:13:19 | 23:50:36 | 37 min 17 s | 16 videos have `tag_detection.pkl`. |
| 03 | gripper_range | `05_run_calibrations.py --skip_slam_tag` | 23:50:36 | 23:50:37 | 1 s | Finger midpoint -1.75 mm (right) and +1.06 mm (left); width measured in 100% of frames. |
| 04 | audio_sync | `06a_estimate_audio_sync.py` | 23:50:37 | 23:51:33 | 56 s | Offsets found, e.g. -399.9 ms, -420.2 ms, +35.5 ms for the 3 head videos. Saved `audio_sync_offsets.json`. |
| 05 | head_tags | `scripts_tag_tracking/00_detect_tag_corners.py` | 23:51:34 | 00:11:45 | 20 min 11 s | `tag_corners.pkl` for head videos and head_mapping. |
| 06 | segment_episodes | `00b_segment_episodes.py` | 00:11:45 | 00:12:40 | 55 s | `tag_tracking/episodes.json` written. |
| 07 | use_setup | `00c_use_setup.py` | 00:12:40 | 00:12:41 | 1 s | Copied `setup_station1/bodies.json` and `gripper_tcp.json`. |
| 09 | track_bodies | `03_track_bodies.py` | 00:12:41 | 00:55:35 | 42 min 54 s | Cubes seen in 99 to 100% of frames in the last demo; head valid in world 86% (tags only). |
| 10 | fuse_head_imu | `03b_fuse_head_imu.py` | 00:55:35 | 01:08:08 | 12 min 33 s | Head valid 86% (tags only) to 100% (fused), median std 0.6 mm, 0.04 deg (last demo). |
| 11 | trim_docking | `03t_trim_docking.py` | 01:08:08 | 01:08:10 | 2 s | Docking removed. Last demo: 10 of 10 episodes with a task, 13.4 to 45.6 s. 1 episode flagged for review (removing more than 7.0 s). |
| 13 | sync_wrists | `03s_sync_wrists.py` | 01:08:10 | 01:09:17 | 1 min 7 s | Wrist offsets about +12.7 to +15.6 ms per episode (last demo). Accuracy: head to right 1.48 ms, head to left 1.61 ms, right to left 0.35 ms. |
| 14 | fuse_grippers | `03c_fuse_gripper_imu.py` | 01:09:17 | 01:33:44 | 24 min 27 s | 0 failed chunks; fused valid 100% (last demo). |
| 16 | export_plan | `06_export_dataset_plan.py` | 01:33:46 | 01:34:08 | 22 s | First plan: 24 episodes, 838.4 s of 1828.1 s used, 0% interpolated steps. |

Skipped by the pipeline itself: `render` (`-nr`), `calibrate_bodies` and `gripper_tcp` (replaced by `setup_calibration`). That is why logs 08, 12 and 15 do not exist.

After the pipeline, `process_station.py` ran:

| Step | Command | Result |
|---|---|---|
| Plan with gaps kept | `06_export_dataset_plan.py -i <session> -c <config> --keep_gaps` | **28 episodes, 1261.4 s of 1828.1 s used (69%)**. Replaced the 24-episode plan. |
| MCAP export | `07_export_mcap.py -i <session> -c <config> -j 4` (about 01:34:43 to 01:35:14) | 28 MCAP files in `dataset_mcap/`, 7.8 GB total. |
| Summary | | `station1 task01: ok (153 min)`. No `--upload`, no `--cleanup`. |

## 3. Validation checks (after the run)

Run from the repo root with `.venv`, `-i data/station1/industrial_data/task01 -c example/tag_tracking/tag_tracking_station1.yaml`.

| Order | Command | Start | End | Duration | Result |
|---|---|---|---|---|---|
| 1 | `check_frame_sync.py` on one MCAP episode (episode 3) | not recorded | | | Passed (see `PROCESSING_LOG.md`). |
| 2 | `check_frame_sync.py` (all episodes) | 11-22 06:41:48 | 07:04:48 | 23 min | 27 of 28 episodes measured. Right wrist median +3.7 ms (+0.5 to +10.2), left +3.4 ms (+1.0 to +6.2), wrist to wrist 0.0 ms. Only episode 16 right wrist is over half a frame (+10.2 ms). Episode 20 had 0 usable wrist tag poses, so unmeasured. Log: `logs/check_frame_sync_all.log`. |
| 3 | `check_frame_table.py` | 08:37:53 | 08:38:03 | 10 s | 7 head videos, 14 robot rows. 0 structure errors. Position median <= 5.2 mm (worst 95%: 16.0 mm), rotation median <= 1.58 deg, 0 widths out of range. Flags: right gripper aligned pose only 20.6% of rows in demo 13.49.46; one left row with lowest TCP -8.5 cm (first percentile +0.5 cm). Log: `logs/check_frame_table.log`. |
| 4 | `check_tcp_frame.py --random 4 --seed 0` (episodes 7, 13, 16, 21) | 08:38:03 | 08:38:31 | 28 s | Lowest TCP z 2.0 to 6.1 cm. TCP dot at the fingertips in head and wrist views. |
| 5 | `check_tcp_frame.py -e 0,1,...,27` (first try) | 08:43:34 | 08:43:36 | 2 s | **Failed**, my shell mistake: the episode list reached the script empty (`ValueError: invalid literal for int()`). Nothing produced. |
| 6 | `check_tcp_frame.py -e 0,1,...,27` (rerun) | 08:43:50 | 08:47:12 | 3 min 22 s | 28 of 28 images saved, `tag_tracking/tcp_check_ep<N>_robots01_<t>s.png`. Lowest TCP z per episode 0.8 to 12.2 cm. TCP dot z per cube -0.5 to 11.9 cm; 4 of 56 values outside 0 to 10 cm (-0.2 and -0.5 cm in episodes 3 and 25, 11.6 and 11.9 cm in episode 20). Reviewed images of episodes 20 and 25 (episode 3 not viewed): episode 20 shows both grippers standing at the dock, wrist cameras facing the wall, so 11.6 and 11.9 cm is the docked pose (this is also why the sync check found no wrist env tags in episode 20). Episode 25 right gripper has its fingertip at the table in the box, so -0.5 cm is table contact within measurement noise. No tracking fault seen. Log: `logs/check_tcp_frame_all.log`. |
| 7 | `11_check_quality.py -i <session> -c <config> -j 4` | 11-22 09:12:50 | 09:33:16 | 20 min 26 s | **Crashed** after the image statistics of all 21 videos were done and cached, so a rerun skips the decoding. No `tag_tracking/quality.json` written. `TypeError` in `umi/tag_tracking/quality.py:266` (`sync_check`): `abs(residual) <= accuracy_ms` with `accuracy_ms = None`. Cause: `wrist_sync.json` has `accuracy_ms: null` for the wrist videos of 4 of the 7 head videos (13.13.17, 13.18.11, 13.46.02, 13.49.46), while the episode has its own sync fit, so the code reaches the comparison. Repo code not changed. Log: `logs/11_check_quality.log`. Warnings printed before the crash: every video is 59.9401 Hz ("not an integer rate", warn); right wrist `13.49.41` also fails dropped frames (camera minus decoded -14). |
| 8 | `08_annotate_episodes.py -i <session> -c <config> --dry_run` | 11-22 09:12:53 | 09:55:01 | 42 min 8 s (ran at the same time as check 7 for the first 20 min) | Completed, **no API call**. 29 episodes got a frame sheet (`*_frames.jpg`) and request text (`*_request.txt`) in `tag_tracking/annotations/` (26 MB, 58 files): 22 to 28 frames, 9 to 15 spans and 10 to 16 gripper events per episode in the last demo. 29 episodes with a task interval versus 28 in the dataset plan: not checked why. No `annotations.json`; the words need the API run. Log: `logs/08_annotate_dry_run.log`. |

## 4. Not run

`check_tcp_frame.py` images exist for all 28 episodes; viewed by eye: episodes 16, 20, 25. Not run: `render` step, `11_check_quality.py` (crashed, see check 7; no quality.json), `08_annotate_episodes.py` without `--dry_run` and `09_normalize_labels.py` (annotations; need the `anthropic` package and `ANTHROPIC_API_KEY`, neither present, and send frames to the Anthropic API), `10_coverage_report.py`, `13_export_delivery.py` (delivery, not requested), `--upload`, `--cleanup`.
