# HITL delivery status, 26 Nov 2026

**Bottom line:** 3.24 h (406 episodes) can be delivered now from phase 1 HITL.

- Reviewers accepted 4.99 h in total.
- 1.74 h (173 episodes) of that cannot ship until the left and right camera views are swapped (check V9).
- 14.38 h (1,084 episodes) have not been through HITL yet. About 8.9–9.9 h of it is expected to be deliverable.

Hours are recording hours (head camera, one view). Every number is in `hitl_status_summary.csv`, and the same view is in `hitl_status.html`.

Sources:
- `hitl_mosaics-2.xlsx`, tab `hitl_data_day1`.
- `delivery_check.csv`, from deep check v4.
- `ingestion/funnel.md`.

**Deliverable now** means two things are both true:
- The episode passes the deep check data checks.
- HITL marked both grippers visible and the task completed, and the reviewer counted 3 or more repetitions.

## Funnel

| Stage | Episodes | Hours |
|---|---|---|
| Ingested head videos (production) | 674 files | 55.51 |
| Paired takes, 3-camera shared window | 342 takes | 45.08 |
| Paired takes in processed task folders | 267 takes | 38.10 |
| Episodes cut | 2,310 | 23.10 |
| Data checks pass | 1,772 | 20.26 |
| Data fails only V9 left/right swap (fixable) | 294 | 2.45 |
| Data fails other checks (mostly C3, under 9 s) | 244 | 0.39 |
| **HITL phase 1 reviewed** | **1,226** | **8.73** |
| **HITL pending** | **1,084** | **14.38** |

## Phase 1 HITL (1,226 episodes, 8.73 h)

| Outcome | Episodes | Hours |
|---|---|---|
| **Accepted, data pass: deliverable now** | **406** | **3.24** |
| Accepted, needs left/right swap first | 173 | 1.74 |
| Accepted, fails another check | 4 | 0.01 |
| Rejected: under 3 repetitions | 461 | 2.22 |
| Rejected: task not completed | 61 | 0.66 |
| Rejected: grippers not visible | 1 | 0.01 |
| Not answered or partly answered | 120 | 0.85 |
| **Total** | **1,226** | **8.73** |

**HITL yield:**
- 57% of reviewed hours were accepted (4.99 h).
- 37% of reviewed hours can be delivered now (3.24 h).
- Of hours that passed the data checks, 62% were accepted.

### Why the sheet shows 4.33 h

The sheet's Duration column is out of date for 53 episodes, in station2/2026-11-22/task05 and station1/2026-11-22/task06. Those episodes were re-cut longer. All 53 are left/right-swap episodes, so the deliverable-now figure is the same with either duration column.

| HITL accepted (583 episodes) | Sheet durations | Actual durations |
|---|---|---|
| Deliverable now (406) | 3.24 | 3.24 |
| Needs left/right swap (173) | 1.08 | 1.74 |
| Fails another check (4) | 0.01 | 0.01 |
| **Total** | **4.33** | **4.99** |

### Before and after HITL, same episodes

| | Episodes | Hours |
|---|---|---|
| Before: data checks pass | 778 | 5.99 |
| Before: data pass + VLM 3+ repetitions | 415 | 3.28 |
| After: HITL accept + data pass (deliverable now) | 406 | 3.24 |
| After: HITL accept, needs left/right swap | 173 | 1.74 |

The two gates land on almost the same hours, but on different episodes.

## HITL parameters

| Parameter | Rule | Phase 1 answers |
|---|---|---|
| Both gripper visible | Reject if No | 1,111 Yes, 1 No, 114 blank |
| Task completed | Reject if No | 1,046 Yes, 64 No, 116 blank |
| Number of repetitions | Reject if under 3 (PRD R2) | 626 with 3+, 139 with 2, 341 with 1, 5 with 0, 115 blank |
| Task match | Relabel, not a rejection | 639 Yes, 513 No (202 are the `#N/A` lookup), 74 blank |
| Write task if wrong | Becomes the new label | Filled on 511 of 513 "No" rows |
| Comment | Not used in the rule | 41 rows |

## Why episodes were rejected

### Under 3 repetitions: 461 episodes, 2.22 h

329 episodes have 1 repetition and 132 have 2. Rejected clips average 17 s; accepted ones average 31 s.

| Task folder | Episodes | Hours | Average length |
|---|---|---|---|
| station1/2026-11-21/task02 | 139 | 0.54 | 13.9 s |
| station1/2026-11-21/task03 | 144 | 0.37 | 9.1 s |
| station3/task03 (20 Nov) | 16 | 0.22 | 50.2 s |
| station3/task04 (20 Nov) | 25 | 0.20 | 29.1 s |
| station3/2026-11-21/task02 | 28 | 0.20 | 25.7 s |

- **Station 1, 21 Nov:** the clips are very short (9–14 s). This points to wrong episode cut points.
- **Station 3:** the clips are long, but the cycles are slow, so fewer than 3 fit.

### Task not completed: 61 episodes, 0.66 h

Most are in station3 on 22 Nov: task01 (29) and task04 (8). Reviewer comments mention incorrect placing, technical issues, and objects not placed in the bin.

### Grippers not visible: 1 episode

station2/2026-11-22/task01, episode 1. The comment says a third person's hands are visible.

### Accepted but flagged in comments: 10 episodes

These passed the rule, but the comments say otherwise:
- "Two episodes merged into one" (5)
- "Need to reject task, handling very poor" (1)
- "Last cycle needs to be discarded" (1)
- "Incorrect object interaction" (1)
- "Clipped mid-cycle" (1)
- "Bare hands visible" (1)

Check them before delivery. They are still counted in the 3.24 h.

## Human vs VLM repetition count (1,111 episodes)

| | VLM 3+ | VLM under 3 |
|---|---|---|
| Human 3+ | 441 | 185 |
| Human under 3 | 35 | 450 |

- On the 3+ threshold, the human and the VLM agree on 80% of episodes. The exact count matches on 55%.
- When the VLM is wrong, it mostly undercounts.
- Of data-pass hours where the VLM counted 3+, reviewers accepted 84%. Where the VLM counted under 3, they accepted 39%.

## Pending HITL today (1,084 episodes, 14.38 h)

| Station | Date | Episodes | Hours | Data pass | VLM also 3+ |
|---|---|---|---|---|---|
| station1 | 24 Nov | 191 | 2.42 | 2.37 | 1.74 |
| station2 | 24 Nov | 165 | 4.17 | 4.16 | 3.21 |
| station3 | 24 Nov | 179 | 2.86 | 2.85 | 2.12 |
| station4 | 21 Nov | 180 | 0.93 | 0.91 | 0.14 |
| station4 | 22 Nov | 132 | 1.48 | 1.47 | 0.85 |
| station4 | 24 Nov | 142 | 1.53 | 1.53 | 0.92 |
| station5 | 22 Nov | 7 | 0.15 | 0.15 | 0.08 |
| station5 | 24 Nov | 51 | 0.74 | 0.74 | 0.52 |
| stations 1–3 | 20–22 Nov leftovers | 37 | 0.09 | 0.08 | 0.03 |
| **Total** | | **1,084** | **14.38** | **14.27** | **9.61** |

What to review today:
- Review the 994 episodes that pass the data checks (14.27 h).
- Skip the 89 episodes that fail C3 for being under 9 s (0.09 h).
- Also finish the 120 phase 1 rows left blank (0.85 h).
- Review episodes where the VLM counted 3+ first; reviewers accepted 84% of those hours in phase 1.

**Expected deliverable from today:**
- About **8.9 h** if 62% of data-pass hours are accepted, as in phase 1.
- About **9.9 h** if the phase 1 rates are applied separately by VLM verdict.

Pending episodes average 48 s against 26 s in phase 1, so more of them should reach 3 repetitions.

## Sheet issues

- **Out-of-date durations.** 53 episodes have stale durations, so the sheet totals 7.91 h for phase 1 against 8.73 h measured.
- **202 task names show `#N/A`.** These are the undated 20 Nov folders, and every one of those rows was marked "Task match = No". 239 deliverable episodes (2.09 h) need the corrected task applied before delivery.
- **The `v4 status` column does not follow the deep check verdict.** 121 episodes marked "Ready" fail C3, and 32 marked "Drop (confirm)" pass every check.
- **The `hitl_mosaics.csv` tab in `hitl_mosaics-2.xlsx` is blank** (6 rows answered), so it is not used.
- **The `All (presigned)` tab** has all 2,310 episodes.
  - Its presigned links stop working on **3 Dec, 04:49 UTC**.
  - Its HITL columns are empty for every row: the phase 1 answers are only in `hitl_data_day1`.
