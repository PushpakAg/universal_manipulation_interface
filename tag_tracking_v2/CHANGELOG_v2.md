# CHANGELOG_v2 (2026-11-22)

Everything here was made in `tag_tracking_v2/` (untracked). No original script was modified.
Measurements: one head video of station1/task01 (`demo_C3501326502664_2026.11.20_13.18.11.927417`, 5472 frames, 2704x2028),
Mac with 8 cores. The machine was not always idle (load average 3 to 30 between runs), so only same-session A/B pairs are compared.

## Verified against the originals (scratch copies; the real session was not touched)

| Check | Result |
|---|---|
| `07_export_mcap.py` v2 vs original, episodes 3 and 7 | 34,541 and 38,737 messages, **0 differ** (topic, time, payload), metadata equal, file sizes equal to the byte. 7.6 s vs 6.5 s. |
| `00_detect_tag_corners.py` v2 vs the original run's `tag_corners.pkl` | 5472 frames, **0 frames differ, max corner difference 0.0 px**. 59.6 s (92 fps, 8 workers). Original run took 63 s for this video: no detection speedup at full resolution, as expected. |
| `03_track_bodies.py` v2 vs original on the same `tag_corners.pkl` | **max absolute difference over every field of `tag_tracking.pkl`: 0.0** (identical, NaN pattern identical). |
| 29 unit tests (`tests/test_tt2.py`) and the 2 original `test_process_station.py` tests | pass |

## Finding: BLAS / OpenMP oversubscription is real, and large

`03_track_bodies.py` on that one video, same machine, same input, back to back:

| Run | Wall | User CPU | System CPU |
|---|---|---|---|
| Original (pool workers start with default library threads) | **107 s** (again 107 s on a repeat) | 693 s | 113 s |
| Original with `OMP/OPENBLAS/MKL/VECLIB_NUM_THREADS=1` set | **14 s** | 82 s | 2 s |
| v2 (limits set in `tt2.parallel.make_executor`) | **17 s** | 89 s | 4 s |

Same results, 6 to 7x less wall time and 8x less CPU. The first-pass review listed this as "unproven"; it is proven for
tracking. `fuse_head_imu` and `fuse_grippers` use the same pool code (now also v2) and are expected to gain too, but that
is not measured yet. Scaled to the real run (track_bodies 43 min) this suggests a few minutes instead; the dry run will show.
It also means the earlier statement "CPU was saturated, extra workers would not have helped" hid wasted CPU, not useful work.

## Correction to the profile section of notes/SCRIPT_REVIEW_tag_tracking.md

The decode / detection profile was taken while the machine was loaded (load average about 126). Idle re-run, same video,
same 600 frames: decode 1 thread **16 ms** (was 57), decode with threads 3 ms (was 17), detection **27 ms** (was 94),
detection half resolution 9 ms (was 32). The ratio is about the same (detection about 63%, decode about 37% per worker), the
absolute times were about 3.5x too high.

## Detection at reduced resolution is not a free win (`compare_detection.py`, 100 frames, idle machine)

| Scale | Recall vs full | Extra detections | Corner error mean / p95 / max (px) |
|---|---|---|---|
| 0.75 | 97.9% | 71 | 0.17 / 0.10 / 27.2 |
| 0.50 | 96.7% | 143 | 0.25 / 0.14 / 34.0 |
| 0.35 | 89.8% | 206 | 0.39 / 1.41 / 43.8 |

It misses tags and finds different ones, so `--detect_scale` stays at 1.0 (original algorithm) and is an opt-in. (Timing in
that table is noisy and not used.)

## Files

- `tt2/`: `errors`, `log`, `runner`, `fsutil`, `s3`, `bootstrap`, `parallel` (copy + thread limits, all-bodies submit),
  `video_chunk` (copy + 4 chunks per worker, shared pool, named failures), `tag_detection` (copy + parameters once, optional
  coarse-to-fine).
- Scripts: `run_tag_tracking_pipeline.py`, `scripts_tag_tracking/` `process_station`, `00_detect_tag_corners`, `03_track_bodies`,
  `03b_fuse_head_imu`, `03c_fuse_gripper_imu`, `06_export_dataset_plan`, `07_export_mcap`, `13_export_delivery`,
  `sort_recordings`, plus new `compare_detection` and `compare_runs`.
- `README_v2.md`: layout, change table, what was not changed and why. `tests/test_tt2.py`.

## Not verified yet

- `process_station.py`, the v2 pipeline (`--resume`, imu || wrist_tags overlap), prefetch / upload overlap, `06`, `13`,
  `sort_recordings` against real data or real S3: unit-tested (logic, failure paths) but not run end to end. The dry run
  is the end-to-end test. Upload and S3 paths in particular were only tested with a fake client.
- `13_export_delivery.py` and `06_export_dataset_plan.py` were changed mechanically (asserts to `require`, atomic plan); their
  parse check passed, no run.
- Whether imu overlapping wrist_tags helps (they compete for 8 cores) is untested.

---

# Dry run on a subset (2026-11-22)

Input: station1/task01 recordings 3 and 4 (head + both wrists each, 77 s and 91 s), both gripper calibration clips, the head
mapping clip: 9 videos, hard-linked (the real session was not touched). Same config, `process_station.py --mcap`, no upload, 8-core Mac,
original and v2 run one after the other on the same input (`data/subset_check/orig_r2`, `v2_r2`).
Not run on S3: download, upload and cleanup were not exercised.

## Outputs: identical

`tag_tracking.pkl` of both head videos: max difference 0.0. `dataset_plan.pkl`: 0.0. 3 MCAP files: 32,646 / 31,709 / 66,462 messages, **0 differ**,
file sizes equal to the byte. Yield 3 episodes, 109 s used in both (original: "109.3s of 159.6s used (68%)").

## Time (wall, whole `process_station.py` run)

| | Original | v2 |
|---|---|---|
| Whole run | **758 s** | **595 s** (-21%) |

| Step | Original (min) | v2 (min) | |
|---|---|---|---|
| track_bodies | 3.2 | 0.3 | **-90%** |
| imu | 0.3 | 0.7 | overlapped with wrist_tags |
| wrist_tags | 3.7 | 4.2 | +11% (imu ran at the same time) |
| head_tags | 2.1 | 2.3 | +10% |
| fuse_head_imu | 0.9 | 0.9 | -5% |
| fuse_grippers | 1.8 | 1.8 | -2% |
| other steps | about 0.5 | about 0.5 | |

## What the dry run says

- **Confirmed:** the thread limit in `tt2.parallel` removes the `track_bodies` oversubscription (3.2 min -> 0.3 min here, same as the
  isolated test). That one step is the whole gain on this input. Scaled to the full run's 43 min `track_bodies` it points to roughly 4 to 5 min, a saving of about 38 min of 153; this is an estimate until the full session is run.
- **Not confirmed (hypothesis was wrong):** `fuse_head_imu` and `fuse_grippers` did not speed up (-5%, -2%, within noise). The thread limit
  does not matter for them (their cost is the GTSAM solve itself), so the earlier expectation "the fusion steps should gain too" is wrong. They remain
  the main target (together 2.7 of 10.4 min here, 40 of 153 min in the full run).
- **No gain, slightly worse:** overlapping `imu` with `wrist_tags` (imu 0.3 + wrist_tags 3.7 = 4.0 min in series, 4.2 min overlapped): they share the 8 cores. `--overlap_imu` is now **off by default**.
- **No gain:** the shared pool with 4 chunks per worker for head tag detection (`head_tags` +10%, 2.3 vs 2.1 min; may be noise on one run, but there is no gain). More chunks add seeks. The original
  chunking is as good on this input; kept as is, but not a win.
- Prefetch / upload overlap, `--resume`, boto3 paths: not exercised (local session, single run).

## First attempts, for the record

The first two runs failed within seconds: the original pipeline (and the unchanged `04_detect_aruco.py` that v2 still calls) start steps with a bare `python`, and I
had started them with `.venv/bin/python` without the venv on PATH. v2 now puts its own interpreter's folder first on every child's PATH (`tt2/runner.py`, test added),
and the v2 run succeeded without the venv on PATH. The original needs the venv activated, as it always did. A second try failed because of my shell quoting of PATH (spaces).

---

# Round 2: the steps that did not improve in the dry run (2026-11-22)

All changes keep the output identical; each was checked against the original's files, not assumed.
Same 2-take subset of station1/task01, 8-core Mac. Times are wall seconds of the step alone.

| Step | Original | Round 1 v2 | Round 2 v2 | Change in round 2 | Output vs original |
|---|---|---|---|---|---|
| wrist_tags (6 videos) | 222 s | 229 s (4 chunks/worker) | **200 s** (1 chunk/worker) | `04_detect_aruco.py` rewritten in-process: one shared pool for all videos, 2 videos ahead, no `python` subprocess + pool per video, mirror mask precomputed (`tt2/wrist_detection.py`) | 6 of 6 `tag_detection.pkl` identical (rvec, tvec, corners) |
| head_tags (3 videos) | 126 s | 131 s (4 chunks) | **113 s** (1 chunk) | videos pipelined in the shared pool; chunks per worker is an option, default 1 (4: 131 s, 2: 121 s, 1: 113 s) | 3 of 3 `tag_corners.pkl` identical |
| fuse_head_imu | 54 s (55.7 s rerun) | 55.7 s, 545% CPU | **48.7 s**, 626% CPU | next video's chunks submitted before the current one is post-processed | `tag_tracking.pkl` max difference 0.0 |
| fuse_grippers | 105 s | 105 s | **99 s**, 668% CPU | same | max difference 0.0 |

What this shows
- Gains are 6 to 13% per step, not the 10x of `track_bodies`. These steps are compute bound: the CPU time is the same (653 s user for
  `fuse_grippers`), the pipelining only fills idle cores (545% -> 626% of 800% for `fuse_head_imu`).
- Fewer, bigger chunks were faster for detection (each chunk pays a keyframe seek and start-up), so the round-1 default of 4 chunks per worker was wrong;
  now 1 for both detection steps, as the original.
- Per frame cost of wrist detection (idle machine, one core): decode 12 ms, rgb24 conversion 8, mirror mask 7 (now about 1), detectMarkers 26.
  Mask change saves about 5 ms of 53 ms per frame.

What was NOT changed, and why (each would change results, so it needs a validation decision, not a silent switch)
- **Fusion chunk length** (`--chunk_sec 12`, `--context_sec 1`): every chunk also solves 1 s of context on each side (about 17% extra work). Longer chunks
  would cut that, but move the chunk boundaries and so change the fused poses a little. Tunable by the user; not applied.
- **Detection at reduced resolution**: still not safe (recall 97%, extra detections), see the table above.
- **Wrist detection on gray instead of rgb24** (saves the 8 ms conversion): `detectMarkers` converts RGB with its own weights; pyav's gray
  differs in rounding, so corners could move by a fraction of a pixel. Not applied.
- **imu / wrist_tags overlap** stays off (no gain on 8 cores).
- **Native (non-Docker) IMU extraction** and **one shared decode pass** remain not done: both are larger changes than a measured 6 to 13% justifies.

Expected effect on the full 28-episode session (estimate, not measured): `track_bodies` about 38 min saved (round 1) plus about 10% of the
other compute steps (detection 57 min, fusion 37 min), so roughly 9 to 10 min more. Total roughly 153 min -> about 100 min.

# Unit checks added in round 2
Mask identity against `draw_predefined_mask` on three image sizes, `run_pipelined` ordering / look-ahead / failure handling (32 tests pass).
