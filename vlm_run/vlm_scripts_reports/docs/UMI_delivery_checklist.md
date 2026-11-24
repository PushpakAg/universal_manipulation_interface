# UMI delivery checklist: pass / fail

Source: **DataPRD1019 v1.1** (2026-10-19), section 6 "UMI data: head + two wrist cameras" (UMI R1–R8, U1–U6,
"Delivery and metadata"), and `tag_tracking_v2/docs/DataPRD1019_mcap_delivery_checklist.md` (branch tag-tracking-v2).
Checked by `scripts/check_delivery.py`; thresholds in `configs/delivery_check.json`.

One **recording** = one episode folder of the delivery (`14_export_rhoda.py` output):

```
<station>/[<date>/]<taskNN>/<episode>/
  <rec>_head.mp4  <rec>_left.mp4  <rec>_right.mp4      three original camera files (U1)
  <rec>_meta.json                                      cameras, sync, gripper-width files
  <rec>_right_gripper.csv  <rec>_left_gripper.csv      gripper width per frame (frame, width_m)
  <rec>_mosaic.mp4                                     optional review video, not a substitute (PRD)
  <rec>_vlm_result.json                                VLM answer (canonical task, task, count)
```

## Verdict

- **FAIL**: any HARD check fails. The recording is not delivered as UMI data.
- **REVIEW**: no HARD check fails, but a check could not be decided automatically (no cycle count yet, a model
  count below 3 with low confidence, a model task that names a setup activity). A person decides.
- **PASS**: every HARD check passes. The MANUAL rules below are still a reviewer's job (sample the videos).

The PRD's UMI examples fail on R2 alone (Bad U-1: one garment; Bad U-3: one cycle), so R2 is a hard rule.
The egocentric "at least five of eight rules" matrix (PRD section 3) is not used for UMI.

## HARD checks (machine-checked; any FAIL fails the recording)

| ID | PRD | Requirement | Measured from | Pass when |
|---|---|---|---|---|
| D1 | U1, Delivery | Three original views per recording | file names in the episode folder | `_head.mp4`, `_left.mp4`, `_right.mp4` all present and readable. Head-only is not UMI data. A mosaic does not replace them. |
| D2 | Delivery | Per camera: model, lens / field of view, resolution, frame rate, intrinsic calibration | `_meta.json` `cameras.head/left/right` | every camera has `model`, a lens or FOV value (`lens` or `fov_*_deg`), `resolution`, `frame_rate_hz`, `intrinsics_model`, `fx fy cx cy` (and `k1..k4` for Kannala-Brandt) |
| D3 | Delivery | Sync method and the frame index of the sync event in each file | `_meta.json` `sync.method`, `sync.frame_index` | method is a non-empty string; one integer frame index per file (head, left, right), each within the file's frame count |
| D4 | Delivery, U6 | Gripper width per frame (gripper opening measurable) | `_right_gripper.csv`, `_left_gripper.csv` | both present; one row per video frame (rows = frame count ± 1); every `width_m` a number in 0 … 0.15 m (0 = fully closed), no NaN |
| V1 | U2 | Same frame rate on all three views | ffprobe `r_frame_rate` | equal on head, left, right, and equal to `frame_rate_hz` in meta (± 0.01 fps); 59.94 fps expected for GoPro HERO12 |
| V2 | U2 | Same time span (full length, trimmed to what all three share) | ffprobe frame count and duration | frame counts differ by ≤ 1 frame; durations differ by ≤ 1 frame period (16.7 ms at 59.94 fps) |
| V3 | U2, Delivery | Video readable, resolution as declared | ffprobe codec, width × height | H.265 or H.264; width × height equals meta `resolution` for that camera |
| V4 | U2 | Synchronized within 1 frame | `sync.frame_index` of the three files | all three files start at the sync event: their frame indices are equal (the delivered files are cut so frame i is the same instant in all three) |
| C1 | R2 | At least 3 complete cycles of the same action | manual count (`reports/manual_counts.csv`, `n_repetitions_manual`), else the VLM count (`<rec>_vlm_result.json`) | count ≥ 3 (target 5 or more). Manual count < 3: FAIL. VLM count < 3: FAIL only when `n_repetitions_confidence` ≥ 0.8, else REVIEW (zero answers are often model misses). No count: REVIEW. |
| C2 | R3 | Each cycle 3–30 s (UMI) | recording duration / count | duration ≥ 3 s × count (otherwise at least one cycle is shorter than 3 s). duration / count > 30 s is WARN (long cycles or idle time: review). |
| C3 | R2, R3 | Recording long enough for 3 cycles | head duration | ≥ 9 s (3 cycles × 3 s) |

## WARN / INFO checks (reported, never fail a recording)

| ID | PRD | What | Rule |
|---|---|---|---|
| W1 | U5 | Both grippers in use | width range (max − min) of each gripper ≥ 0.02 m. A passive gripper (holding a basket, a tray) is allowed: WARN only. |
| W2 | R1 | One action type, repeated | VLM `canonical_task` / `task` present and not a setup activity (calibration, inspection, test, scan). Setup task: REVIEW. |
| W3 | R2 | Target 5 or more cycles | count 3–4: INFO |
| W4 | R3 | Cycles not much longer than 30 s | duration / count > 30 s: WARN |
| W5 | Delivery | Mosaic | present or not: INFO (optional, not a substitute) |

## MANUAL rules (not machine-checkable: sample the videos)

| ID | PRD | Rule | Fail example |
|---|---|---|---|
| R1 | R1 | One action type, repeated; objects may vary if the action is the same | mixed chores (Bad U-2) |
| R3 | R3 | Each cycle 3–30 s; cycles similar in length (none > ~2× the median) | one 55 s cycle (Bad U-1) |
| R4 | R4 | Any fixed spot (table, shelf, floor); no walking | walking to the sink and back (Bad U-2) |
| R5 | R5 | Hands / both grippers in the head view for most of the recording; every grasp and placement visible | work hidden in a bin |
| R6 | R6 | Head camera follows the grippers; brief task-driven turns only | looking around the room |
| R7 | R7 | Input already at the station; no fetching gaps > ~5 s | fetching materials |
| R8 | R8 | No side tasks | tidying, phone use, switching task |
| U3 | U3 | Wrist cameras rigidly fixed, same mount every recording, left and right mirrored | camera slips or rotates |
| U4 | U4 | Wrist view shows the gripper fingers (markers) and the object before and during the grasp; lens not blocked | sleeve or object blocks the lens |
| U5 | U5 | Both grippers held throughout | one gripper put down |
| U6 | U6 | Image quality: no strong backlight, textured workspace, blur only in fast transfers | bright window (Bad U-3) |

Up to ~5 s of setup at the very start is tolerated (R4); the delivered files are already trimmed to the shared span.
