# tag_tracking_v2

Hardened copies of the tag tracking batch scripts, made from the findings in `notes/SCRIPT_REVIEW_tag_tracking.md`
(read that first). This folder was untracked until 2026-11-24; it is tracked on branch `tag-tracking-v2`. The original scripts are unchanged and
still run from the repository; v2 takes everything it does not replace (the `umi/` library, the SLAM-pipeline steps
`00_process_videos`, `01_extract_gopro_imu`, `04_detect_aruco`, `05_run_calibrations`, `06a_estimate_audio_sync`, and tag
tracking steps `00b`, `00c`, `03t`, `03s`, ...) from the original repository.

## Layout

```
tag_tracking_v2/
  run_tag_tracking_pipeline.py        v2 pipeline (steps via sys.executable, timeouts, resume, imu || wrist_tags, timings json)
  scripts_slam_pipeline/
    04_detect_aruco.py                in-process, shared pool for all videos (was a subprocess + pool per video), precomputed mask
  scripts_tag_tracking/
    process_station.py                v2 batch: overlapped download / compute / upload, boto3, atomic MCAP swap, quality gates
    00_detect_tag_corners.py          shared process pool for all videos, atomic output, --detect_scale
    03_track_bodies.py                all bodies of a video submitted at once, next video submitted ahead
    03b_fuse_head_imu.py, 03c_fuse_gripper_imu.py   worker thread limits, next video submitted ahead, atomic output, failed chunks logged
    06_export_dataset_plan.py         atomic plan, require() instead of assert
    07_export_mcap.py                 atomic files, vectorised messages, verify in worker, error per episode
    13_export_delivery.py             uses the v2 07, require() instead of assert
    sort_recordings.py                boto3 instead of aws-cli processes
    compare_detection.py              NEW: recall / corner error / time of reduced-resolution detection on real frames
    compare_runs.py                   NEW: step times of a baseline run vs a v2 run
  tt2/                                shared code
    errors.py log.py runner.py fsutil.py s3.py bootstrap.py parallel.py video_chunk.py tag_detection.py
  tests/test_tt2.py                   29 tests, no network, no real data
```

Run the scripts as the originals (same options, same outputs, same folder layout, same log names):

```
python tag_tracking_v2/scripts_tag_tracking/process_station.py <sessions> -c <config> [-w <workdir>] --mcap [--upload s3://...] [--cleanup]
python tag_tracking_v2/run_tag_tracking_pipeline.py -c <config> [--resume] <session>
```

Tests: `.venv/bin/python -m pytest tag_tracking_v2/tests -q`

## What changed, and why

| Weakness found | Change | Where |
|---|---|---|
| `python` from PATH vs `sys.executable` | every step runs with the same interpreter | pipeline, runner |
| No timeouts on any subprocess / S3 call | per-step limit (`--step_timeout_min`, default 480), terminate then kill; boto3 connect/read timeouts and adaptive retries (8) | runner, s3 |
| 68 bare `assert`s on external input | `require()` raising `InputError` / `ConfigError` / `PipelineError` with the fix; typed errors | all scripts, errors |
| No logging | `logging` everywhere (console + file); each step has start/end/duration/exit in the log and in `logs/pipeline_timings.json` | log, runner, scripts |
| Half-written outputs on a crash | every pickle / json / MCAP written to a hidden temp file and renamed | fsutil, 00, 03, 03b, 03c, 06, 07 |
| Failed MCAP export left the folder empty, old export moved aside | export into `dataset_mcap.tmp`, swap only when all episodes were written, old export kept aside and restored on failure | process_station, fsutil |
| Yield parsed from stdout, failure reason from text | yield read from `dataset_plan.pkl`; failure from the step result | process_station |
| "ok" hid review flags | quality gates: no episodes, yield below `--min_yield`, MCAP count != plan, wrist sync accuracy above `--max_sync_ms`; summary says "ok, flagged"; `--fail_on_flags` | process_station |
| Cleanup after a size-only check | upload verified by size and MD5 / multipart ETag (size only for KMS buckets, reported as such), then cleanup | s3, process_station |
| aws-cli process per S3 call (2 per video in `sort_recordings`) | one boto3 client, ranged GETs, paginated listing with `Delimiter` | s3, sort_recordings, process_station |
| Sessions strictly in series | download of session N+1 and upload of N-1 run during processing of N (`--no_prefetch` to disable) | process_station |
| `imu` (Docker) ran alone | optional `--overlap_imu` (imu and wrist_tags at the same time); **off by default**, no gain measured | pipeline |
| Reruns repeat 2 h of work | `--resume`: leading steps with unchanged script, arguments, config files and raw videos are skipped; the first step that runs makes all later ones run | pipeline |
| `03_track_bodies` gathered one body at a time; main process post-processing left the pool idle | all bodies of a video submitted together; the next video submitted before post-processing the current | 03_track_bodies, parallel |
| Pool rebuilt per video (wrist: a new python + pool per video); cores idle while the slowest chunk of a video ends | one pool for all videos, two videos ahead; chunks per worker is an option (default 1: 4 chunks were slower, see CHANGELOG round 2) | video_chunk, 00_detect_tag_corners, 04_detect_aruco |
| BLAS threads not limited in workers | `OMP/OPENBLAS/MKL/VECLIB/NUMEXPR_NUM_THREADS=1` for the pool | parallel |
| Per-frame detector parameters, per-sample Python loops in MCAP | parameters built once; poses / IMU converted with array operations; verify runs in the worker | tag_detection, 07 |

## Verified equivalence (not just claimed)

- `07_export_mcap.py` v2 vs original, episodes 3 and 7 of station1/task01: **identical** (every message topic, log time and
  payload; metadata records; file size to the byte). Time on an idle machine for the two episodes: 7.6 s original, 6.5 s v2.
- `00_detect_tag_corners.py` v2 vs the existing `tag_tracking` input of the real run and `03_track_bodies.py` v2 vs original on one
  head video: see `CHANGELOG_v2.md` (results of the smoke runs).

## Deliberately NOT changed (and why)

- **`--detect_scale` defaults to 1.0 (original algorithm).** Measured on 100 frames of a head video (`compare_detection.py`):
  at scale 0.5 recall is 96.7% with 143 extra detections and corner errors up to 34 px; at 0.75 recall 97.9%, 71 extra. A
  faster search that changes which tags are found would change the tracking, so it is an option to validate, not a default.
- **MCAP video stays base64 in JSON** (schema `foxglove.CompressedVideo` as before): a protobuf channel is a format change
  for the consumers. Cost is +33% size and about 1% of run time, so it matters for upload size only.
- **Pickle step handoff and the subprocess-per-step design are kept.** Moving steps in-process would save a few seconds of
  imports per step and change every script; the real bottleneck is elsewhere.
- Not implemented: one shared decode pass for detection / wrist tags / IMU; native (non-Docker) IMU extraction; moving the
  dock/idle trim before detection and fusion (needs a design change: `03t_trim_docking` depends on tracking output);
  a general end-to-end test on a synthetic session.

## Dry run

Done on a 2-take subset (round 2 results in the changelog: wrist/head detection and the fusion steps 6 to 13% faster, outputs identical) (recordings 3 and 4 + calibration clips) of station1/task01, original and v2 on identical input: outputs
identical, `track_bodies` 10x faster, total 758 s -> 595 s. Details and the steps that did NOT improve: `CHANGELOG_v2.md`.

## Notes and docs (moved here on 2026-11-24 from the repository root, where they were untracked)

```
notes/SCRIPT_REVIEW_tag_tracking.md      read-only review of the tag tracking scripts (basis of v2)
notes/TAG_TRACKING_UNDERSTANDING.md/.html  how the pipeline works, what it needs, what delivery needs
notes/PIPELINE_RUN_LOG.md                station1 / task01 validation run, commands in order
notes/PROCESSING_LOG.md                  station1 tool_handling run
notes/CALIBRATION_COMMANDS.md            calibration and video processing commands
docs/DataPRD1019.pdf                     data PRD
docs/DataPRD1019_mcap_delivery_checklist.md   MCAP delivery checked against the PRD
docs/mcap_comparison_s3_orig_v2.html     S3 vs original vs v2 MCAP comparison
../scripts_tag_tracking/14_trim_mcap_common_span.py   trim delivery MCAPs to the common time span (PRD U2)
```

