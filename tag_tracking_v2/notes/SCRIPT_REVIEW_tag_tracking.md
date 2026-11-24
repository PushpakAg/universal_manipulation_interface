# Review: tag tracking scripts (README_tag_tracking.md)

Read-only review. No script was changed and none was run. Everything below comes from
reading the code. Performance figures are estimates, not measurements. Verify them
with a profile before acting.

Scope read in full: `process_station.py`, `run_tag_tracking_pipeline.py`,
`07_export_mcap.py`, `parallel.py`, `tag_detection.py`, `03_track_bodies.py`,
and the main flows of `sort_recordings.py`, `13_export_delivery.py`, `06_export_dataset_plan.py`.
Not read in depth: `calibrate_setup.py`, `check_*`, `propose_station_config.py`, `08`/`09`, the OpenICC scripts.

## Verdict: engineered core, scripted glue

Not a throwaway hack. It is also not production-grade for throughput or latency.

**Engineering done well**
- The tracking core is chunked in `parallel.py`. Each chunk is overlapped by 1 frame so results are identical to a serial run. Workers are spawned (not forked), because GTSAM objects can't be pickled, and the executor is reused.
- Video is not re-encoded in the MCAP export: HEVC packets are copied and repacked to Annex B.
- Parquet manifest written via tmp file + atomic `replace`.
- `cleanup()` verifies S3 sizes before deleting anything.
- Failures in one session don't stop the batch. The summary reports yield.
- A test file exists for many modules (26 files, including `test_process_station.py`, `test_sort_recordings.py`).

**Scripting-style traits**
- Orchestration is a sequence of `subprocess` calls to scripts. Each step re-imports cv2/gtsam/scipy and re-reads its pickles.
- Step handoff is by pickle files on disk (111 `pickle` references in `scripts_tag_tracking/`). There is no schema, no version, and no integrity check.
- 68 bare `assert`s serve as validation. They disappear under `python -O`, and the error messages go straight to the user.
- No `logging` module anywhere (0 uses). It is `print` plus tee'd log files.
- `sys.path.append` + `os.chdir(ROOT_DIR)` in the scripts. Importing them has side effects, so they can't be reused as libraries.
- Generic `except Exception` in `03b`, `03c`, `sort_recordings`, `12_review_viewer`.
- Tests cover helpers and pure logic. Nothing exercises the pipeline end to end, and nothing covers the S3 or MCAP write paths under load.

## Throughput weaknesses (ranked by likely impact)

1. **Sessions and stations run strictly one after another** (`process_station.process`).
   Per session the order is download, then pipeline, then plan, then MCAP, then upload,
   and each phase waits for the previous one. While CPU is busy the network is idle, and
   while it downloads the CPU is idle. Fix: a pipelined producer/consumer with a download
   queue for session N+1 and an upload queue for session N-1, overlapping with compute for N.
   For a day with several sessions this is probably the largest single win.

2. **MCAP video is base64 inside JSON** (`07_export_mcap.py`, `write_episode`).
   `base64.b64encode(data).decode()` followed by `json.dumps` inflates video by ~33%, adds
   CPU, and makes each message a large string copy. The schema forces this (`foxglove.CompressedVideo`
   with `contentEncoding: base64`, JSON encoding). The official Foxglove schema is protobuf with raw
   bytes. Switching message encoding to protobuf for video would cut size, CPU and upload time.
   Compatibility with consumers must be checked first.

3. **Per-sample Python loops with a `json.dumps` per message** (`write_episode`).
   IMU (hundreds of Hz, per wrist, per episode) and poses are written one message at a time with
   `list(map(float, ...))` and `Rotation.from_rotvec(...)` per row. Vectorise the rotation
   conversions (one `Rotation` call for the whole array) and build payloads from arrays.
   Likely a few-x speedup on the non-video part of the export.

4. **Pipeline step overhead and no step-level parallelism** (`run_tag_tracking_pipeline.py`).
   17 steps run serially as separate Python processes. Independent steps are serialised, for
   example `imu`, `wrist_tags` and `audio_sync` (all read raw videos and write separate outputs),
   and wrist work vs head work. Each step re-opens and re-decodes video. Every step except
   sort/imu/wrist_tags/head_tags always re-runs, so a retry or small config change repeats everything.
   There is no content hash or mtime-based skip.

5. **Video decoded multiple times.** Tag detection decodes each video
   (`detect_video_tag_corners`), wrist tags decode again (`04_detect_aruco`), IMU extraction and
   audio read the files again, and the MCAP step re-demuxes. One decode pass feeding several
   consumers would cut I/O. Also `detect_tag_corners` builds `DetectorParameters` for every frame
   (cheap but avoidable) and converts every frame to gray via `to_ndarray`. Detection on the full
   2.7K frame is the dominant CPU cost. Downscale-then-refine, or ROI from the previous frame, would help.

6. **Pool oversubscription risk.** `-j` defaults to all cores in every step, and the
   MCAP step is capped to 4 only when called from `process_station`. Inside a worker, cv2 is limited
   to 1 thread in the detector (good), but GTSAM/numpy BLAS threads are not limited in
   `_track_chunk`/`_fuse_window`. Set `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS=1` in the workers.

7. **Memory: whole structures in RAM.** `07`/`13` load full `tag_tracking.pkl`, the full plan
   and all `exif` at once. All episode jobs (with full pose arrays, camera records) are pickled to
   workers. `03_track_bodies` builds `frames` for the entire video even when only windows
   are tracked. Fine for tens of episodes, a risk for long sessions.

8. **S3 handling shells out to the AWS CLI** (`process_station.py`, `sort_recordings.py`).
   - `s3_video_info` spawns two `aws s3api get-object` processes per video (a 64 KB range, then
     the moov range) plus a temp file for each. For hundreds of videos that is hundreds of
     process spawns (~0.5–1 s each) even with 16 threads. `boto3` with a shared client and
     `Range` GETs would be far cheaper and would reuse connections.
   - `s3_sizes` and `s3_sessions` use `list-objects-v2` through the CLI and rely on its
     auto-pagination via `--query`. This is correct but slow, and `s3_sessions` lists every key
     under the prefix just to find folder names. Use `Delimiter='/'`.
   - Downloads use `aws s3 sync` per session: no parallel-session transfer, no checksum verification of
     downloaded videos, no resume visibility.
   - Upload verification (`cleanup`) compares size only, not ETag or checksum.

9. **`run()` streams output line by line through Python** (`process_station.run`).
   The pipeline's progress bars use carriage returns, so `for line in p.stdout` blocks until a
   newline: progress appears in bursts, and `lines` keeps every output line in memory for
   the whole run. Low impact on throughput, a bit of lag in feedback.

## Latency weaknesses

- **Batch only.** There is no incremental path: a recording needs the full download, then
  every pipeline step, before any episode is available. Time to first episode equals time to last.
  Process per episode or per video and emit as they finish.
- **Sequential per-episode work in the main process before workers start** in `07`/`13`
  (exif for all videos, head tracking load, IMU offset). The ExifTool subprocess is started once
  per phase and metadata is read serially. `head_extras` starts a fresh `ExifTool()` and opens
  the video per head video.
- **`verify()` re-reads each finished MCAP** and decodes the first video message, serially in the parent
  as futures complete. Decode is done in the main process, which stalls collection of other
  results. Run it in the worker.
- **Startup cost per step**: each `python script.py` pays interpreter + cv2 + gtsam + scipy
  import time (seconds), 17 times per session, times sessions.
- **MCAP written with ZSTD over already-compressed H.265 base64 text.** Compression gains little
  on video and burns CPU. Use no compression for the video channel (separate chunking per
  channel, or `CompressionType.NONE` / LZ4).

## Correctness / robustness risks (affect trust in the output)

- `run_tag_tracking_pipeline.run` calls `python` from PATH, while `process_station` uses
  `sys.executable`. The two can run in different environments (the CLAUDE.md warns about venv leaks).
  Use `sys.executable` in both.
- `process_station.cleanup` deletes local videos and MCAP after a size-only check. Size equality
  is weak evidence for a media file. `videos` are only deleted if "downloaded from S3", but that is
  inferred from flags, not verified per file against the S3 object.
- `process_station.process` renames the existing `dataset_mcap` before running. If the later MCAP
  step fails, the folder is left empty and the older export sits in a dated directory. Nothing restores it.
- `upload` uses `aws s3 sync` without `--delete`, so stale MCAPs from an earlier export remain on
  S3 and the cleanup check (which only compares local files) won't notice them.
- Yield is parsed from stdout with a regex (`\d+ episodes, `) and the failure reason by
  searching for `'failed, see'`. Any message change silently breaks reporting. Structured output
  (a JSON result file per step) would be sturdier.
- `07 write_episode`: the `assert index <= start_frame` first-keyframe check will raise inside a
  worker and abort that episode's MCAP. A partially written file is left on disk (no tmp file +
  rename, unlike the parquet).
- `sort_recordings`: serial number found by regex `C\d{13}` in the first 64 KB; mvhd
  position guessed when moov is after mdat. Both are heuristics and fail without a clear error
  on some files. The mvhd read assumes a 4 KB window.
- No timeouts on any `subprocess.run` / `Popen`. A hung AWS call or hung step blocks the batch forever.
- No retries on S3 operations except `sample_or_none` (3 attempts).
- Pickle files are loaded without validation. A file from another source can execute code,
  and a format change breaks old sessions silently.

## Suggested improvements, by effort

| Effort | Change | Gain |
|---|---|---|
| Low | `sys.executable` in `run_tag_tracking_pipeline.run`; timeouts on subprocess calls | Safety |
| Low | Limit BLAS/OMP threads in worker initializer | Removes oversubscription |
| Low | Vectorise rotation conversion and payload building in `07` | CPU in export |
| Low | Write MCAP to `*.tmp`, rename when done; restore the old folder on failure | Atomicity |
| Low | Skip video channel compression | Export CPU |
| Medium | `boto3` client with `Delimiter` listing and ranged GETs instead of CLI spawns | S3 scan time |
| Medium | Overlap download / compute / upload across sessions | Wall time per day |
| Medium | Skip steps whose outputs are newer than inputs (+ config hash) | Re-run cost |
| Medium | Replace `assert` validation with explicit exceptions; use `logging` | Reliability, diagnostics |
| High | One decode pass shared by tag detection, wrist tags and IMU | Decode I/O |
| High | Run steps in-process as functions (not subprocess), with typed result files instead of pickles | Startup, safety |
| High | Protobuf video messages in MCAP | Size, CPU, upload |
| High | Add an end-to-end test on a tiny synthetic session | Regression safety |

## Not verified

- No timing or profiling was done. Where a step dominates wall time is unknown.
  Profile one session first (`/usr/bin/time -l` per step log is enough) before optimising.
- Algorithm correctness of tracking, fusion and sync was not evaluated.
- Scripts not listed under "Scope read in full" were only skimmed or counted with grep.

---

# Update: evidence from the real run (station1 / task01)

Source: `PIPELINE_RUN_LOG.md`, `PROCESSING_LOG.md`, and the step logs and `process_station.out` in
`data/station1/industrial_data/task01`. Machine: Mac, 8 cores, 16 GB, Docker under Rosetta for `imu`.
Still read-only. This section **corrects the ranking above**, which was based on code reading alone.

## What the run shows

Input: 7 takes x 3 cameras (about 123k head frames), 1828 s of synchronised recording.
Output: 28 episodes, 1261 s (69%), 7.8 GB of MCAP. Total **153 min** (about 5x real time of the
recording, about 7 s of compute per delivered second). No step errors in any log
(the "failed" hits in the logs are only "0 failed" chunk counts).

| Step | Min | Share of 153 |
|---|---|---|
| track_bodies | 42.9 | 28% |
| wrist_tags | 37.3 | 24% |
| fuse_grippers | 24.5 | 16% |
| head_tags | 20.2 | 13% |
| fuse_head_imu | 12.6 | 8% |
| imu (Docker, emulated) | 10.7 | 7% |
| everything else (audio_sync, segment, sync_wrists, plan, MCAP...) | ~5 | 3% |

Four steps are 81% of the time: tag detection (wrist + head, 37%) and GTSAM tracking/fusion (track + both fuses, 52%).

## Corrections to my earlier ranking

- **MCAP export is not a bottleneck.** 28 files, 7.8 GB, about 31 s with 4 workers
  (01:34:43 to 01:35:14). The base64/JSON video, per-sample `json.dumps` and ZSTD points are real
  inefficiencies (size +33%) but worth about 1% of run time. Demote to "later". Upload size is
  the only place the +33% matters (7.8 GB vs about 5.9 GB raw video).
- **Step-by-step process overhead and repeated imports are small** here (seconds per step, 17 steps).
  Not worth restructuring for latency on a session this size.
- **The `process_station` overlap idea (download / compute / upload) was not exercised**: this run
  was a local session (no `--upload`, no `--cleanup`; the download was done by hand, with an SSO
  token expiry mid-download). Its value is real but unproven by this run. Download time was not recorded.
- **"Oversubscription from BLAS threads" is unproven.** The log notes CPU was saturated throughout.
  Measure (`top`, or per-step `/usr/bin/time -l`) before changing thread settings.

## Real bottlenecks, from the logs

1. **Tag detection is slow per core.** `head_tags`: 4595 frames in 43 s on 8 workers is about 107 fps
   total, about 13 fps per core. A 77 s head take costs 43 s; a 5 min take costs 3 min 20 s.
   `wrist_tags` is the single biggest detector cost: 16 videos (14 takes + 2 calibration clips) in 37 min.
   Causes visible in `tag_detection.py`: full 2.7K frame, `CORNER_REFINE_SUBPIX` on every tag,
   gray conversion of every frame, every frame decoded. Options: detect on a downscaled frame and
   refine sub-pixel only on the found tags' windows; track tags frame to frame (ROI) instead of
   searching the whole image; skip frames outside the episode windows (wrist cameras record
   dock time and idle time that `trim_docking` throws away later).
2. **Detection runs on frames that are later discarded.** `03_track_bodies` tracked 120,954 of
   123,143 frames (98%), so the episode windows barely save anything, because the takes are mostly
   episodes. But 31% of the recorded time is not used (1261 s of 1828 s), and dock/idle segments are
   detected, tracked and fused first, then trimmed. Running segmentation and docking trim first,
   then detection and fusion only on kept windows, could save a large part of the 81%. Needs care:
   `trim_docking` currently depends on tracking output, so this is a design change, not a flag.
3. **Fusion and tracking cost scales with frames, not with value.** `track_bodies` 43 min is
   about 47 head frames/s counted over two cubes (a rough figure). `fuse_grippers` splits into
   chunks (7 to 37 per video), but the last take shows uneven work (left 16,866 frames vs right
   5,750 in the same video). Chunk sizes are by count, not cost, so a long video's tail
   can leave cores idle. More, smaller chunks, or a work queue over all videos (not per video),
   would balance load. In `03_track_bodies` each video, then each body, waits for its result before the
   next starts (`gather_track` inside the body loop), so only one body's chunks occupy the pool at a time.
   `submit_track` exists to avoid this but is not used here.
4. **Steps are serial although inputs are independent.** `wrist_tags` (CPU), `imu` (Docker, emulated amd64,
   about 11 min), and `audio_sync` do not depend on each other. Running `imu` concurrently with
   `wrist_tags` would hide most of the 11 min if cores allow (it competes for the same 8 cores, so the
   gain is limited; a native arm64 IMU extractor would be better than emulation).
5. **Results are always recomputed.** Re-running after a config change repeats the 4 big steps (about
   2 h). The log shows the steps that skip existing outputs are only the cheap or first ones;
   `track_bodies` and both fuses always rerun. There is no input hash, so cache invalidation is
   manual (`--start_from`).
6. **Validation checks are slow relative to what they do.** `check_frame_sync.py` took 23 min for
   28 episodes (about 50 s each). `check_tcp_frame.py` took 3 min 22 s for 28 images.
   Fine as a one-off, too slow to run on every session without parallelism.

## Quality and engineering observations from the run

- The first `check_tcp_frame.py -e ...` call failed because the episode list arrived empty
  (`int('')`). The script accepted an empty `-e` and failed late with a `ValueError`; the log notes
  it as a shell mistake, but input validation with a clear message is the engineering fix.
- Review flags (episode 16 right wrist +10.2 ms; episode 20 with 0 usable wrist tag poses; one
  episode with a 13 s task after 35 s + 48 s trimmed) were found only by manual checks run after the
  pipeline. They are not gates: `process_station` reports "ok" without any quality threshold.
  A session can finish "ok" while having a weak episode. Add pass/fail gates (sync error over half a
  frame, no wrist poses, large trim) to the summary.
- Systematic +3 to +4 ms wrist offset (median right +3.7, left +3.4) was measured but not applied.
  Either correct it in `03s_sync_wrists` or document it as a known bias in the delivered metadata.
- `head valid in world` is only 75 to 86% from tags and reaches 100% only after IMU fusion;
  `valid 100%` after fusion is a statement about the fused filter, not a measurement. Treat the
  100% figures with care, and prefer the std/consistency checks (frame table, TCP image) as the evidence.
- Environment is not reproducible: the venv uses unpinned numcodecs and different pins than
  `conda_environment.yaml`; `imu` depends on an amd64 Docker image under Rosetta; the log
  records the Python 3.10 venv by hand. A lockfile and a native IMU path would be the fix.
- 80 of 81 tests passed; the failing one is a test bug (missing fixture), still unfixed. Tests
  do not cover any of the four dominant steps at session scale.
- Record keeping is manual: setup/download times were not recorded; the two logs disagree on
  `fuse_grippers` (24 min 27 s vs "about 20 min"). A per-step timing line written by the pipeline
  itself would remove this.

## Revised priority

| Priority | Change | Why (evidence) |
|---|---|---|
| 1 | Cut detection cost (downscale + local refine, or ROI tracking) | 37% of time in two steps, about 13 fps per core |
| 2 | Skip dock/idle and unused time before detection and fusion | 31% of recorded time is dropped at the end |
| 3 | Submit all bodies/videos to the pool together; balance chunks by cost | `gather_track` per body leaves workers idle; uneven chunks |
| 4 | Input-hash caching so reruns skip finished big steps | a rerun costs about 2 h |
| 5 | Native `imu` extractor, run alongside detection | 11 min under emulation |
| 6 | Quality gates in `process_station` summary | "ok" hid 3 review flags |
| 7 | Overlap download / compute / upload across sessions | untested here, multi-session days |
| 8 | MCAP: vectorise, protobuf video, no ZSTD on video | about 1% of time, but size and upload |

## Not verified

- Per-core and per-step figures are derived from log progress bars and timestamps, not profiled.
- Whether detection or decode dominates `head_tags` is not known. Profile one video first.
- Gains from the changes above are estimates; none was implemented or tested.

---

# Summary (first pass, from code reading only)

Logged as given. Where the real run (section "Update" above) changed the picture, the
item is marked **[revised]**; the Update section and its priority table take precedence.

Read in full: `process_station.py`, `run_tag_tracking_pipeline.py`, `07_export_mcap.py`, `parallel.py`,
`tag_detection.py`, `03_track_bodies.py`. Main flows of `sort_recordings.py`, `13_export_delivery.py`,
`06_export_dataset_plan.py`. Only skimmed: the `check_*` scripts, the OpenICC scripts.

## Engineering or fast scripting: a solid core with scripted glue around it

- Solid core: the parallel tracking is chunked correctly. Video is copied into the MCAP rather than
  re-encoded. The cleanup step checks S3 sizes before deleting anything. A failed session doesn't stop
  the batch. There are 26 test files.
- Scripted glue:
  - The pipeline runs 17 steps as separate subprocesses that pass data through pickle files.
  - Validation is about 68 bare asserts.
  - There is no logging.
  - Scripts modify `sys.path` and change directory on import.
  - Some `except Exception` blocks are too broad.
  - There is no end-to-end test.

## Biggest throughput and latency weaknesses

1. Sessions run strictly in series (download, pipeline, MCAP, upload), so network and CPU alternate idle.
   Overlapping them is probably the biggest win. **[revised]** Not exercised by the real run (local
   session, no upload); unproven, kept as priority 7.
2. Video in the MCAP is base64 inside JSON: about 33% more size and CPU, and Zstd on already-compressed
   video wastes CPU. **[revised]** The real export took about 31 s of 153 min (about 1%); matters for upload size only.
3. The MCAP export builds each IMU and pose message in a Python loop (`json.dumps` and a rotation
   conversion per sample). **[revised]** Same: about 1% of run time.
4. Steps run serially and the video is decoded several times. Most steps rerun every time, with no skip
   when outputs are up to date. **[revised]** Confirmed as a cost: a rerun repeats about 2 h.
5. S3 access shells out to the AWS CLI; `sort_recordings.py` spawns two `aws` processes per video.
   `boto3` would be far cheaper. **[revised]** Not exercised by the real run.
6. Worker processes don't limit BLAS threads, risking CPU oversubscription. **[revised]** Unproven;
   measure first.
7. There is no incremental path: the first episode isn't available until the whole batch is done.

**Added by the real run:** the dominant costs are tag detection (37% of time, about 13 fps per core) and
GTSAM tracking/fusion (52%), neither of which was in the first-pass list.

## Correctness risks

- `run_tag_tracking_pipeline.py` calls `python` from PATH, while `process_station.py` uses
  `sys.executable`, so the two can run in different environments.
- The cleanup step deletes local files after a size-only check.
- A failed MCAP step leaves the `dataset_mcap` folder empty with the old export moved aside, and
  nothing restores it.
- MCAP files are not written to a temp file and renamed, so a failure leaves a partial file.
- There are no timeouts or retries on subprocess and S3 calls.
- Yield and failure reasons are parsed from stdout text, which breaks silently if a message changes.

---

# Summary (second pass, with the real run: station1 / task01)

Corrects the first-pass ranking using the run logs. No scripts were changed; the figures come from
the run logs, not from profiling.

**What the run showed:** 153 minutes for 1828 s of recording (about 5x real time). It produced 28
episodes (1261 s kept, 7.8 GB of MCAP). Nothing failed in any log; the "failed" hits are only
"0 failed" chunk counts.

| Step | Share of the 153 min |
|---|---|
| track_bodies | 28% |
| wrist_tags | 24% |
| fuse_grippers | 16% |
| head_tags | 13% |
| fuse_head_imu | 8% |
| imu (Docker, emulated) | 7% |
| everything else | about 3% |

Four steps are 81% of the time: tag detection (37%) and the GTSAM tracking and fusion steps (52%).

**What the first pass got wrong:** the MCAP export is not a bottleneck. It wrote 7.8 GB in about 31 s,
roughly 1% of the run. The base64 video encoding is still wasteful, but it only matters for upload
size. The per-step process overhead is also small. Overlapping download, compute and upload is
untested, because this run was local with no upload.

## Real bottlenecks

1. Tag detection is slow. `head_tags` ran at about 13 frames/s per core.
2. Unused footage is processed first. `03_track_bodies` tracked 98% of frames. About 31% of the
   recorded time is trimmed away only afterwards.
3. Idle workers. `03_track_bodies` waits for one body's result before starting the next, and fusion
   chunks are uneven. In the last take, one wrist had 16,866 frames and the other 5,750.
4. Reruns repeat everything. A rerun redoes about 2 hours of the four big steps.
5. The IMU step is emulated. Under Docker on Rosetta it takes about 11 minutes.
6. The checks are slow. `check_frame_sync.py` took 23 minutes for 28 episodes.

## Quality issues the run exposed

- `process_station.py` reports "ok" with no quality gate. It missed three review flags that only
  manual checks found: episode 16 right wrist +10.2 ms out of sync, episode 20 with no usable wrist
  poses, and one episode with a very large trim.
- A consistent +3 to +4 ms wrist offset was measured but not applied.
- `check_tcp_frame.py` failed late on an empty `-e` list.
- The two logs disagree on the `fuse_grippers` time (24 min vs "about 20 min").
- One test still fails because of a missing fixture.
- The environment pins differ from `conda_environment.yaml`.

---

# Profile: decode vs detection on one head video (estimate)

Video: `demo_C3501326502664_2026.11.20_13.18.11.927417/raw_video.mp4` (2704x2028 HEVC, 5472 frames), first 600 frames,
one process, `.venv` Python. Uses the project's `detect_tag_corners` and the same dictionary (`DICT_4X4_50`).
The profiling script is in the session scratchpad; no project script was changed.

**Caveat:** the machine was busy during the run (load average about 126; a `08_annotate_episodes.py` job with 4 worker
processes at about 180% CPU each). Absolute times are inflated and noisy. Treat the ratios as indicative and
re-run on an idle machine before acting.

| Measurement | ms/frame | fps |
|---|---|---|
| Decode, 1 thread (what a worker effectively gets) | 57 | 18 |
| Decode, FFmpeg threads AUTO | 17 | 60 |
| Gray conversion (`to_ndarray('gray')`) | about 0 | |
| Detection, project settings (SUBPIX) | 94 | 11 |
| Detection, no sub-pixel refinement | 97 | 10 |
| Detection, half resolution, no refinement | 32 | 31 |

## Reading

- **Per worker, detection is about 60% and decode about 40%** (94 vs 57 ms). Detection is the larger share,
  decode is not negligible.
- **Sub-pixel refinement costs nothing measurable** (94 vs 97 ms, within noise, about 8.8 tags per frame).
  The cost is in the marker search over the full 2.7K image. The earlier suggestion to "refine only near found tags" would
  not help; the search resolution is what matters.
- **Half resolution cuts detection about 3x** (94 to 32 ms). With 2.7K images and tags of this size, a coarse
  search at half or quarter resolution followed by refinement at full resolution on the found tags is the most promising change.
  Whether detection quality (recall at distance, corner accuracy) holds must be tested on tracked data, not assumed.
- **Decode is cheap with threads (17 ms) but the chunked workers decode single-threaded** (57 ms), because each worker
  is one process. If detection drops to about 32 ms, decode becomes the larger part of the cost, so cutting detection
  alone gives a bounded gain (about 150 ms to about 90 ms per frame, 1.7x). Hardware decoding (VideoToolbox) or
  decoding once for several steps would be the next step.
- Cross-check with the real run: log says `head_tags` reached about 75 ms of core time per frame (107 fps on 8 workers),
  against about 150 ms here. This is consistent with the machine being loaded now, about 2x, which supports the caveat above.

## Not verified

- Not measured on an idle machine, not over a whole video, not with the 8-process pool.
- Detection accuracy at reduced resolution not tested.
- Only the first 600 frames (up to 200 for detection) were used.

---

# Summary (profile: decode vs detection)

Profiled one head video with Python only; no project script was changed. First 600 frames of a
2704x2028 HEVC head video, detection timed on 200 of them, single process, using the project's
`detect_tag_corners`.

**Caveat:** the machine was busy (load average about 126, from a `08_annotate_episodes.py` job with 4
workers at about 180% CPU each; left alone). Absolute times are inflated, so treat the ratios as the
useful part and rerun on an idle machine before acting.

| Measurement | ms/frame |
|---|---|
| Decode, 1 thread (what a pool worker gets) | 57 |
| Decode, FFmpeg threads | 17 |
| Detection, project settings | 94 |
| Detection, no sub-pixel refinement | 97 |
| Detection, half resolution | 32 |

- **Detection vs decode:** detection is about 60% of each worker's time, single-threaded decode about 40%.
- **Sub-pixel refinement:** it costs nothing measurable (94 vs 97 ms, within noise). The cost is the marker
  search over the full 2.7K image, so refining only near found tags would not help.
- **Half resolution:** it cuts detection about 3x. A coarse search at half resolution followed by
  refinement at full resolution on the found tags looks most promising. Tag recall and corner accuracy at
  that resolution are untested.
- **Bounded gain:** if detection drops to about 32 ms, decode becomes the larger part. Per-frame cost would
  fall from about 150 ms to about 90 ms (about 1.7x). Going further needs hardware decode or decoding the
  video once for several steps.
- **Cross-check:** the real run's log implies about 75 ms of core time per frame, about half of the 150 ms
  measured now. That fits the loaded machine.

---

# Corrections after building tag_tracking_v2 (2026-11-22)

Details and measurements: `tag_tracking_v2/CHANGELOG_v2.md`.

- **BLAS/OpenMP oversubscription is proven, not just a risk.** `03_track_bodies.py` on one head video: original 107 s
  (693 s user CPU, 113 s system), the same script with library threads set to 1: 14 s, v2: 17 s. Results identical
  (max difference 0.0). This is far larger than any other item in this review.
- **The decode / detection profile above was taken on a loaded machine** (load average about 126). Idle re-run: decode 16 ms
  (1 thread), detection 27 ms, half-resolution detection 9 ms per frame. The ratio (about 63% detection, 37% decode) holds, the absolute times were about 3.5x too high.
- **Reduced-resolution detection is not safe as a drop-in** (recall 97% at 0.75 and 97% at 0.5, with 71 / 143 extra detections and
  corner differences up to 34 px), so the "half resolution" suggestion above needs validation per setup before use.

# Dry run result (subset, 2026-11-22)

Original vs v2 on recordings 3 and 4 of station1/task01, identical input: outputs identical (tag tracking, plan, 3 MCAP files, 0 messages differ),
758 s -> 595 s. The gain is `track_bodies` (-90%, the BLAS/OpenMP oversubscription). `fuse_head_imu` and `fuse_grippers` did not improve, and
overlapping `imu` with `wrist_tags` and the shared detection pool gave no gain. Details: `tag_tracking_v2/CHANGELOG_v2.md`.
