# Station4 2026-11-21: re-anchoring the world on tag 28 — full local re-run

**To:** PushpakAg
**Date:** 2026-11-26
**Status:** Results only. Nothing is committed, nothing is written to S3, and no delivery has been changed. Decisions below are yours.

---

## TL;DR

- **Correction to my earlier message:** the 2026-11-21 station4 deliveries were made with `--videos_only`
  (mp4s + gripper widths + metadata, **no poses**). Nothing on S3 is "in the tag-17 frame", so there is
  no world-frame mismatch to fix by redelivering. The anchor affects these deliveries only
  **indirectly**, through how many frames the wrist sync (03s) and the docking trim (03t) can use.
- I re-ran all four sessions (task00–task03) end to end, locally, with the environment map re-anchored on
  table tag **28** instead of the vertical-board tag **17**. The geometry is unchanged; every tag pose is
  only expressed relative to tag 28.
- Result: head IMU fusion goes from failing on roughly half of every video to **96–100% fused, 0 GTSAM
  errors, gravity alignment 0.3–0.6°** (was 90.7–94.1°). Cube world coverage goes from **45–70% to
  89–96%**.
- Effect on what would be delivered for task01–03: **+13 episodes, 18 episodes longer by a median
  12–18 s, 130 unchanged, none lost; about +450 s (+15%) of usable task time.** task00 (never delivered,
  its tag-17 run crashed) now yields **54 episodes**.
- Separate station4 problem, present with **either** anchor: the docking trim's distance rule cuts some
  real tasks to under 1 s, because the dock tags sit in the operator's work area. Plus a small 03t bug
  (task start after task end).

**Asks:** (1) OK to re-anchor station4 on tag 28 (second PR on `rhoda-delivery`)? (2) Redeliver
task01–03 for the extra/longer episodes, or leave them? (3) Deliver task00 from the tag-28 run? (4) How
to handle the station4 docking trim (options in section 6).

---

## 1. Background

`example/tag_tracking/setup_station4/bodies.json` (setup calibration from task01 2026-11-24) anchors the
environment body, i.e. the world frame, on **tag 17**, which is mounted on the vertical board. World z is
therefore horizontal.

The head visual-inertial smoother (`umi/tag_tracking/visual_inertial.py`, `fuse_camera_trajectory`) puts a
gauge prior on G = T_nav_world that fixes rotation about world z. That is only right when world z is
roughly vertical. With tag 17:

- `world-gravity alignment` comes out at ~91° (the angle between world z and gravity),
- GTSAM throws `IndeterminantLinearSystemException` on many windows,
- only part of each head video gets a fused pose, so cube poses in world are missing for large stretches.

Downstream, two steps of the videos-only pipeline use **cube poses in world** and their validity:

| Step | What it uses | Effect of missing world poses |
| --- | --- | --- |
| `03s_sync_wrists.py` (wrist clock sync) | cube rotation rates from `T_world_body` where `is_valid_world` | fewer frames to sync on |
| `03t_trim_docking.py` (task interval) | cube positions in world vs the dock tags, where `is_valid_world` | a cube "keeps its last known state" → task boundaries shift, some episodes lose their task |

The exported files themselves (`15_export_episode_videos.py`) contain no poses.

---

## 2. What I ran, and how it was isolated

### 2.1 Code and config

- Separate git worktree **`~/umi_anchor28`**, detached at `9df290d` (tip of `fix/station4-crash-guards`,
  i.e. PR #1 plus the `single_tag_view` guard). Your/our main checkout and the PR branch are untouched.
- Two uncommitted changes in that worktree only:
  - `example/tag_tracking/tag_tracking_station4.yaml`: `anchor_tag: 28` under `bodies.environment`.
  - `example/tag_tracking/setup_station4/bodies.json`: the same map re-anchored,
    `T_new = inv(T_28) @ T_old` for every environment tag; `anchor_tag: 28`. Cubes, noise model, line
    delay and `gripper_tcp.json` unchanged.

### 2.2 Data

- The four sessions downloaded read-only from
  `s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/station4/industrial_data/2026-11-21/`
  to `~/umi_data/station4_anchor28/sessions/station4/industrial_data/2026-11-21/` (39.5 GB, file counts
  match S3).

| Session | Size on S3 | Objects |
| --- | --- | --- |
| task00 | 11.0 GB | 27 |
| task01 | 16.7 GB | 22 |
| task02 | 4.8 GB | 7 |
| task03 | 7.0 GB | 10 |

### 2.3 Command

Same as the production videos-only delivery, but with **local** sessions and a **local** `--mp4` output,
no `--upload` / `--cleanup`, and **all AWS credentials disabled** so any S3 call would fail:

```bash
cd ~/umi_anchor28
S=~/umi_data/station4_anchor28/sessions/station4/industrial_data/2026-11-21
env -u AWS_PROFILE -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_EC2_METADATA_DISABLED=true \
  python scripts_tag_tracking/process_station.py $S \
    -c example/tag_tracking/tag_tracking_station4.yaml \
    --videos_only --mp4 ~/umi_data/station4_anchor28/episodes --mosaic 1000
```

(run under `sg docker -c` for the IMU extraction container, in the `umi` env).

The only S3-related output is one harmless `logs not uploaded` line per task: the driver tries
`aws s3 sync` between two local paths.

### 2.4 Run time

| Session | Time | Result |
| --- | --- | --- |
| task00 | 40 min | ok |
| task01 | 57 min | ok |
| task02 | 11 min | ok |
| task03 | 20 min | ok |

c7a.8xlarge (32 vCPU), all cores.

---

## 3. Results: tag 17 vs tag 28

"Tag 17" = the production run's outputs still on this instance (`~/umi_data/station4/2026-11-21/`), i.e.
what was delivered for task01–03. task00 was never delivered (crashed at 03t); its tag-17 numbers come from
the partial earlier run.

### 3.1 Head IMU fusion (03b)

| | task00 | task01 | task02 | task03 |
| --- | --- | --- | --- | --- |
| Gravity alignment, median | 91.5° → **0.3°** | 94.1° → **0.4°** | 90.8° → **0.4°** | 90.7° → **0.6°** |
| Head fused valid (mean over head videos) | 52% → **100%** | 65% → **97%** | 51% → **96%** | 70% → **96%** |
| GTSAM `IndeterminantLinearSystem` lines | 178 → **0** | 330 → **0** | 46 → **0** | 81 → **0** |
| Cube valid in world (mean over videos × cubes) | 45% → **89%** | 63% → **94%** | 48% → **90%** | 70% → **96%** |

### 3.2 Episodes and yield

| | task00 | task01 | task02 | task03 |
| --- | --- | --- | --- | --- |
| Episodes exported | – (crash) → **54** | 109 → **114** | 16 → **22** | 22 → **24** |
| Task seconds used / recorded | – → 834 / 2208 s (38%) | 1924 → **2186** / 3551 s (54% → 62%) | 234 → **339** / 596 s (39% → 57%) | 772 → **847** / 1144 s (67% → 74%) |
| Export result (`report.json`) | 54 ok / 0 failed | 114 ok / 0 failed | 22 ok / 0 failed | 24 ok / 0 failed |

### 3.3 Wrist clock sync (03s), accuracy head–cube

| | task00 | task01 | task02 | task03 |
| --- | --- | --- | --- | --- |
| right / left | – → 2.23 / 2.18 ms | 1.39 / 1.43 → 1.32 / 1.36 ms | 1.32 / 1.70 → 1.07 / 1.40 ms | 1.42 / 1.42 → 1.88 / 1.86 ms |

Comparable either way (all within ~2 ms); slightly better on task01–02, slightly worse on task03.

### 3.4 Docking trim (03t) quality indicators

| | task00 | task01 | task02 | task03 |
| --- | --- | --- | --- | --- |
| Tasks under 3 s | 7 → 7 | 4 → **1** | 2 → **1** | 0 → 0 |
| Episodes flagged for review (dock boundary removes much more than usual) | 17 → 17 | 12 → **1** | 2 → **1** | 2 → **0** |

---

## 4. What would change in the deliveries already on S3 (task01–03)

Episodes matched by head video and episode start; "changed" = task start or end moved by more than 0.5 s.

| | Unchanged | Changed | Median change of changed | Total task length added | New episodes | Lost |
| --- | --- | --- | --- | --- | --- | --- |
| task01 | 96 | 14 | longer by 12.1 s | +159 s | 5 | 0 |
| task02 | 14 | 2 | longer by 14.5 s | +29 s | 6 | 0 |
| task03 | 20 | 2 | longer by 18.5 s | +37 s | 2 | 0 |
| **Total** | **130** | **18** | | **+225 s** | **13** | **0** |

Every changed episode got **longer**: with tag 17 the trim saw the cubes' world positions too rarely and
cut tasks short or dropped them. Total usable task time for task01–03: **2930 s → 3372 s (+15%)**.

So redelivery would **add** data (13 episodes, ~450 s) and **improve** 18 episodes; it would not fix
anything broken in the 130 that are already there.

---

## 5. Why tag 28 (environment-fit diagnosis)

I also looked at why `setup_station4`'s environment fit has variance factor 455.7 (station5 6.4,
station2 10.2), using the three 11-21 head-mapping walks (15:56, 18:00, 18:17), re-calibrating the
environment from each walk alone and comparing with the 11-24 setup map.

- **The table tags are rigid and stable across days.** Aligned on the table tags (26, 27, 28, 29, 32,
  34), they agree within **1–2.5 mm** in all three 11-21 walks and the 11-24 map.
- **Tag 17 is the least reliable tag in the map.** 1.7 / 3.2 mm off in the first two walks, **19 mm** off
  in the 18:17 walk (either the board moved or it was seen only obliquely: 62 detections). Measured
  relative to tag 17, the table appears to move 18–26 mm between walks; relative to the table, it doesn't.
- **The 455 is a few outliers, not a bad map.** Per walk: 5.4 (18:17), 12.5 (18:00), 157 (15:56). In 15:56,
  98% of the error is a handful of detections of dock tag 29 (likely partly covered by a docked cube). The
  variance factor is a plain mean of normalized errors, so a few such frames dominate it. (The 11-24 walk
  itself isn't on this instance, so this is by analogy.)
- **Tag 32 is probably not flat:** ~4.3° rotation offset against every 11-21 walk, ~4.5° tilt from the
  table plane, highest pixel error of the table tags (2.5–3.3 px).
- Far tags 20 and 22 are almost never seen; they don't matter.

Conclusion: re-anchoring the existing map on tag 28 is enough; no recalibration is needed for it.

---

## 6. Separate issue (either anchor): the docking trim at station4

### 6.1 What happens

03t keeps the task only while **every** cube is more than `dock_exit_distance` = **0.45 m** from the
nearest dock tag (28, 29). At station4 the dock tags are at the table's near edge, right in front of the
operator, so a hand working close to the body is "still docked".

The three worst cases in task00 (tag 28 run):

| Head video, episode | Episode | Task kept | Right cube away | Left cube away (median distance) | Exported |
| --- | --- | --- | --- | --- | --- |
| 14.50.24, ep 4 | 20.7 s | **−3.1 s** | 75% | 17% (0.39 m) | no (dropped downstream) |
| 15.37.18, ep 11 | 20.7 s | **0.9 s** | 74% | 8% (0.35 m) | yes, `episode_000048` (55 frames) |
| 15.37.18, ep 16 | 17.2 s | **0.5 s** | 71% | 4% (0.36 m) | yes, `episode_000051` (28 frames) |

Head-camera frames of 15.37.18 episode 11 (377, 382, 387, 392 s) show **both grippers in hand, actively
working** on the box and bag the whole time. About 15–20 s of real task becomes under 1 s.

Other short exports in task00: `episode_000008` (2.3 s), `000049` (2.2 s), `000050` (1.0 s),
`000053` (2.6 s), probably the same cause.

### 6.2 It's already in the delivered data

| Delivered (tag 17) | Tasks | Under 3 s | Flagged for review |
| --- | --- | --- | --- |
| task01 | 110 | 0.4, 0.5, 0.7, 2.3 s | 12 |
| task02 | 16 | 0.8, 2.0 s | 2 |
| task03 | 22 | – | 2 |

Tag 28 reduces it on task01–02 (more valid cube frames → fewer wrong "docked" states) but does not fix it.

### 6.3 The −3.1 s bug

`between_bangs` moved the task start to a bang at 94.3 s, but the "all cubes away" interval had already
ended at 91.2 s. 03t then writes `task_start > task_end`. It is only dropped later; 03t should drop or clamp
it itself. Also present in the tag-17 run.

### 6.4 Options (your call)

1. **Station4 trim rule.** With the dock inside the work area, a distance threshold can't separate docking
   from working. Possibilities:
   - lower `dock_exit_distance` for station4 (the left cube works at 0.35–0.39 m; `dock_distance` is 0.35 m,
     so there is little room),
   - task runs while **any** cube is away instead of **every** cube,
   - rely on the bangs for station4 boundaries.
2. **03t guard:** drop or clamp an interval whose start is after its end.
3. **Minimum task length** before export (e.g. 3 s), so 0.5 s episodes are not delivered.

---

## 7. Proposed next steps

1. **Re-anchor station4 on tag 28** as a second PR against `rhoda-delivery`: `anchor_tag: 28` in
   `tag_tracking_station4.yaml` + the re-anchored `setup_station4/bodies.json` (exactly the two files
   used here). Separate from PR #1.
2. **task00:** deliver from the merged code (it has never been delivered; tag 28 gives 54 episodes,
   tag 17 crashes).
3. **task01–03:** decide whether +13 episodes / +450 s justify a redelivery. Recommended if the trim fix
   (section 6) lands first, so the redelivery happens once.
4. **Docking trim:** pick an option from 6.4; I can implement it and re-run locally to compare.
5. **Physical checks at station4:** tag 32 flat? board with tags 17, 33, 35 firmly fixed?
6. **Optional:** a robust (median-based) variance factor in the setup calibration report, so a few occluded
   dock-tag detections don't make a good map look broken.

---

## 8. Where everything is (on the devbox)

| What | Path |
| --- | --- |
| This report | `~/umi_data/station4_anchor28/station4_anchor28_report.md` |
| Episodes + mosaics (tag 28) | `~/umi_data/station4_anchor28/episodes/station4/2026-11-21/<task>/episode_<NNNNNN>/` |
| Per-task export report | `~/umi_data/station4_anchor28/episodes/station4/2026-11-21/<task>/report.json` |
| Tracking, episodes, sync, quality (tag 28) | `~/umi_data/station4_anchor28/sessions/station4/industrial_data/2026-11-21/<task>/tag_tracking/` |
| Step logs (tag 28) | `~/umi_data/station4_anchor28/sessions/station4/industrial_data/2026-11-21/<task>/logs/` |
| Run log + summary | `~/umi_data/station4_anchor28/run.log` |
| Tag-17 outputs (as delivered) | `~/umi_data/station4/2026-11-21/<task>/` |
| Worktree with the tag-28 change | `~/umi_anchor28` (uncommitted) |

Each episode folder: `<rec>_head.mp4`, `<rec>_left.mp4`, `<rec>_right.mp4`, `<rec>_right_gripper.csv`,
`<rec>_left_gripper.csv`, `<rec>_meta.json`, `<rec>_mosaic.mp4` — same layout as the S3 delivery.

Disk: the downloaded raw sessions (~40 GB) can be deleted once reviewed; the originals stay on S3.
