# Ingestion -> processed MP4 funnel

Ingestion `s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/`, processed `umi_data/industrial_data_mp4/` (deep check run v4). Hours of raw video are per camera file (head + left + right add up); take and episode hours are recording time (one view).

## Raw videos by status

| Status | Scope | Videos | Hours (all cameras) | Head videos | Head hours |
|---|---|---|---|---|---|
| take | both | 1062 | 139.59 | 350 | 46.74 |
| support | both | 203 | 1.10 | 70 | 0.56 |
| calibration | both | 22 | 0.30 | 0 | 0.00 |
| in_task_unlisted | both | 2 | 0.05 | 0 | 0.00 |
| left_out | both | 773 | 27.20 | 254 | 8.21 |
| pilot | all only | 85 | 21.84 | 0 | 0.00 |
| set | all only | 171 | 21.01 | 55 | 7.00 |
| **total production** | | **2062** | **168.23** | 674 | 55.51 |
| **total all** | | **2318** | **211.08** | 729 | 62.51 |

## Funnel (recording hours = head camera)

| Stage | Count | Hours | % of production head hours | % of all head hours |
|---|---|---|---|---|
| Ingested head videos, all (incl. pilot, Set_2/3) | 729 | 62.51 | 112.6% | 100.0% |
| Ingested head videos, production | 674 | 55.51 | 100.0% | 88.8% |
| Paired takes (head file length) | 342 | 46.74 | 84.2% | 74.8% |
| Paired takes, shared window of the 3 cameras | 342 | 45.08 | 81.2% | 72.1% |
| ... in task folders that were processed | 267 | 38.10 | 68.6% | 60.9% |
| Episodes cut (processed MP4s, excl. 15 loose copies) | 2310 | 23.10 | 41.6% | 37.0% |
| Deliverable episodes (data checks PASS) | 1772 | 20.26 | 36.5% | 32.4% |
| Deliverable + repetition checks PASS (VLM) |  | 12.89 | 23.2% | 20.6% |

Loose recordings at the root of industrial_data_mp4 (copies, D6): 15, 0.10 h (not counted above).

## Deltas

- Head videos never paired (production): 324 files, 8.77 h (support clips, calibration and left-out; split in the table above).
- Camera length mismatch inside takes (longest camera minus shared window): 2.53 h over 77 takes with > 10 s; 67 takes carry a note (a camera stopped early, split files).
- Paired but not processed: 14 task folders, 75 takes, 6.99 h shared.
- Processed take time not in any episode (cut out between episodes): 14.99 h (39.4% of processed take time).
- Episodes failing the data checks: 538, 2.84 h.

## Yield by station and date (processed task folders)

| Station | Date | Task folders | Takes | Shared h | Episodes | Episode h | Episode yield | Deliverable h | Deliverable yield |
|---|---|---|---|---|---|---|---|---|---|
| station1 | 2026-11-20 | 3 | 12 | 1.49 | 145 | 0.92 | 62% | 0.91 | 61% |
| station1 | 2026-11-21 | 5 | 22 | 3.34 | 435 | 2.00 | 60% | 0.54 | 16% |
| station1 | 2026-11-22 | 7 | 24 | 3.24 | 229 | 1.76 | 54% | 1.51 | 47% |
| station1 | 2026-11-24 | 8 | 28 | 4.09 | 191 | 2.42 | 59% | 2.37 | 58% |
| station2 | 2026-11-22 | 6 | 20 | 2.60 | 155 | 1.50 | 58% | 0.48 | 18% |
| station2 | 2026-11-24 | 7 | 37 | 5.58 | 165 | 4.17 | 75% | 4.16 | 75% |
| station3 | 2026-11-20 | 2 | 7 | 0.91 | 57 | 0.69 | 76% | 0.69 | 76% |
| station3 | 2026-11-21 | 2 | 9 | 1.28 | 120 | 0.86 | 68% | 0.86 | 68% |
| station3 | 2026-11-22 | 2 | 18 | 2.17 | 122 | 1.08 | 50% | 1.08 | 50% |
| station3 | 2026-11-24 | 4 | 25 | 4.20 | 179 | 2.86 | 68% | 2.85 | 68% |
| station4 | 2026-11-21 | 4 | 14 | 2.13 | 180 | 0.93 | 44% | 0.91 | 43% |
| station4 | 2026-11-22 | 3 | 19 | 2.80 | 132 | 1.48 | 53% | 1.47 | 53% |
| station4 | 2026-11-24 | 4 | 21 | 2.95 | 142 | 1.53 | 52% | 1.53 | 52% |
| station5 | 2026-11-22 | 1 | 4 | 0.25 | 7 | 0.15 | 61% | 0.15 | 61% |
| station5 | 2026-11-24 | 2 | 7 | 1.07 | 51 | 0.74 | 70% | 0.74 | 70% |

## Paired task folders not processed

| Task folder | Date | Takes | Shared h |
|---|---|---|---|
| station1/industrial_data/task01/raw_videos | 2026-11-20 | 7 | 0.51 |
| station1/industrial_data/task02/raw_videos | 2026-11-20 | 2 | 0.24 |
| station2/industrial_data/task01/raw_videos | 2026-11-20 | 5 | 0.17 |
| station2/industrial_data/task02/raw_videos | 2026-11-20 | 1 | 0.03 |
| station2/industrial_data/task03/raw_videos | 2026-11-20 | 20 | 0.60 |
| station2/industrial_data/task04/raw_videos | 2026-11-20 | 5 | 0.53 |
| station2/industrial_data/task05/raw_videos | 2026-11-20 | 6 | 0.82 |
| station3/industrial_data/2026-11-21/task01/raw_videos | 2026-11-21 | 3 | 0.50 |
| station3/industrial_data/2026-11-21/task04/raw_videos | 2026-11-21 | 6 | 0.84 |
| station3/industrial_data/2026-11-22/task02/raw_videos | 2026-11-22 | 3 | 0.52 |
| station3/industrial_data/2026-11-22/task03/raw_videos | 2026-11-22 | 4 | 0.53 |
| station3/industrial_data/task01/raw_videos | 2026-11-20 | 5 | 0.51 |
| station3/industrial_data/task02/raw_videos | 2026-11-20 | 3 | 0.47 |
| station5/industrial_data/2026-11-22/task02/raw_videos | 2026-11-22 | 5 | 0.71 |

## Left-out raw videos by session (head / left / right files; length buckets over all three)

| Station | Date | Takes paired that day | Head files | Head h | All files | All h | < 30 s | 30 s-2 min | 2-8 min | >= 8 min |
|---|---|---|---|---|---|---|---|---|---|---|
| station1 | 2026-11-20 | 21 | 10 | 0.05 | 32 | 0.18 | 28 | 4 | 0 | 0 |
| station1 | 2026-11-21 | 22 | 11 | 0.07 | 37 | 0.23 | 29 | 8 | 0 | 0 |
| station1 | 2026-11-22 | 24 | 19 | 0.09 | 58 | 0.30 | 56 | 2 | 0 | 0 |
| station1 | 2026-11-24 | 28 | 15 | 0.07 | 55 | 1.12 | 39 | 10 | 2 | 4 |
| station2 | 2026-11-19 | 0 (none) | 1 | 0.01 | 3 | 0.04 | 0 | 3 | 0 | 0 |
| station2 | 2026-11-20 | 37 | 13 | 0.13 | 32 | 0.32 | 15 | 16 | 1 | 0 |
| station2 | 2026-11-21 | 0 (none) | 55 | 3.84 | 163 | 11.49 | 70 | 15 | 18 | 60 |
| station2 | 2026-11-22 | 20 | 9 | 0.19 | 27 | 1.29 | 19 | 1 | 0 | 7 |
| station2 | 2026-11-24 | 37 | 18 | 0.19 | 49 | 0.54 | 39 | 7 | 3 | 0 |
| station3 | 2026-11-19 | 0 (none) | 1 | 0.02 | 3 | 0.04 | 0 | 3 | 0 | 0 |
| station3 | 2026-11-20 | 15 | 4 | 0.02 | 14 | 0.13 | 10 | 4 | 0 | 0 |
| station3 | 2026-11-21 | 18 | 11 | 0.05 | 31 | 0.15 | 27 | 4 | 0 | 0 |
| station3 | 2026-11-22 | 25 | 6 | 0.03 | 18 | 0.12 | 15 | 3 | 0 | 0 |
| station3 | 2026-11-24 | 25 | 12 | 0.07 | 38 | 0.20 | 32 | 6 | 0 | 0 |
| station4 | 2026-11-21 | 14 | 12 | 0.52 | 41 | 1.39 | 21 | 12 | 3 | 5 |
| station4 | 2026-11-22 | 19 | 11 | 0.20 | 37 | 1.22 | 26 | 2 | 4 | 5 |
| station4 | 2026-11-24 | 21 | 16 | 0.11 | 43 | 0.96 | 27 | 13 | 2 | 1 |
| station5 | 2026-11-21 | 0 (none) | 23 | 2.32 | 71 | 6.93 | 21 | 7 | 9 | 34 |
| station5 | 2026-11-22 | 9 | 4 | 0.02 | 16 | 0.06 | 16 | 0 | 0 | 0 |
| station5 | 2026-11-24 | 7 | 3 | 0.19 | 7 | 0.55 | 4 | 0 | 0 | 3 |

## Left-out raw videos (775: in a production dump, in no pairs.csv)

| Station | Date | Camera | File | Length | Status |
|---|---|---|---|---|---|
| station1 | 2026-11-20 | head | GX010365.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | head | GX010366.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | head | GX010371.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | head | GX010378.MP4 | 0.0 min | left_out |
| station1 | 2026-11-20 | head | GX010384.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | head | GX010388.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | head | GX010389.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | head | GX010390.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | head | GX010396.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | head | GX010402.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | left | GX019297.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | left | GX019299.MP4 | 0.6 min | left_out |
| station1 | 2026-11-20 | left | GX019300.MP4 | 0.1 min | left_out |
| station1 | 2026-11-20 | left | GX019303.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | left | GX019304.MP4 | 0.6 min | left_out |
| station1 | 2026-11-20 | left | GX019311.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | left | GX019314.MP4 | 0.0 min | left_out |
| station1 | 2026-11-20 | left | GX019317.MP4 | 0.0 min | left_out |
| station1 | 2026-11-20 | left | GX019319.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | left | GX019325.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | left | GX019331.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | right | GX019253.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | right | GX019255.MP4 | 0.6 min | left_out |
| station1 | 2026-11-20 | right | GX019256.MP4 | 0.1 min | left_out |
| station1 | 2026-11-20 | right | GX019259.MP4 | 0.0 min | left_out |
| station1 | 2026-11-20 | right | GX019260.MP4 | 0.6 min | left_out |
| station1 | 2026-11-20 | right | GX019267.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | right | GX019270.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | right | GX019271.MP4 | 0.3 min | left_out |
| station1 | 2026-11-20 | right | GX019273.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | right | GX019279.MP4 | 0.4 min | left_out |
| station1 | 2026-11-20 | right | GX019285.MP4 | 0.4 min | left_out |
| station1 | 2026-11-21 | head | GX010408.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | head | GX010409.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | head | GX010414.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | head | GX010418.MP4 | 0.2 min | left_out |
| station1 | 2026-11-21 | head | GX010420.MP4 | 0.8 min | left_out |
| station1 | 2026-11-21 | head | GX010427.MP4 | 0.2 min | left_out |
| station1 | 2026-11-21 | head | GX010429.MP4 | 0.4 min | left_out |
| station1 | 2026-11-21 | head | GX010433.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | head | GX010436.MP4 | 0.2 min | left_out |
| station1 | 2026-11-21 | head | GX010438.MP4 | 0.7 min | left_out |
| station1 | 2026-11-21 | head | GX010444.MP4 | 0.6 min | left_out |
| station1 | 2026-11-21 | left | GX019290.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | left | GX019292.MP4 | 0.5 min | left_out |
| station1 | 2026-11-21 | left | GX019296.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | left | GX019301.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | left | GX019302.MP4 | 0.7 min | left_out |
| station1 | 2026-11-21 | left | GX019310.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | left | GX019311.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | left | GX019315.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | left | GX019319.MP4 | 0.4 min | left_out |
| station1 | 2026-11-21 | left | GX019320.MP4 | 0.6 min | left_out |
| station1 | 2026-11-21 | left | GX019325.MP4 | 0.5 min | left_out |
| station1 | 2026-11-21 | left | GX019326.MP4 | 0.5 min | left_out |
| station1 | 2026-11-21 | right | GX019336.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | right | GX019338.MP4 | 0.5 min | left_out |
| station1 | 2026-11-21 | right | GX019342.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | right | GX019346.MP4 | 0.2 min | left_out |
| station1 | 2026-11-21 | right | GX019347.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | right | GX019356.MP4 | 0.3 min | left_out |
| station1 | 2026-11-21 | right | GX019357.MP4 | 0.4 min | left_out |
| station1 | 2026-11-21 | right | GX019358.MP4 | 0.1 min | left_out |
| station1 | 2026-11-21 | right | GX019362.MP4 | 0.2 min | left_out |
| station1 | 2026-11-21 | right | GX019366.MP4 | 0.4 min | left_out |
| station1 | 2026-11-21 | right | GX019367.MP4 | 0.6 min | left_out |
| station1 | 2026-11-21 | right | GX019372.MP4 | 0.0 min | left_out |
| station1 | 2026-11-21 | right | GX019373.MP4 | 0.5 min | left_out |
| station1 | 2026-11-21 | right | GX019374.MP4 | 0.5 min | left_out |
| station1 | 2026-11-22 | head | GX010446.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010452.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | head | GX010453.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | head | GX010454.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010455.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010456.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010457.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010458.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010459.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010460.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | head | GX010461.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010462.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010463.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | head | GX010465.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | head | GX010471.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | head | GX010472.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | head | GX010480.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | head | GX010486.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | head | GX010489.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | left | GX019329.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | left | GX019334.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019335.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019336.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019337.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | left | GX019338.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | left | GX019339.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | left | GX019340.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019341.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019342.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019343.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019344.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019345.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019346.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019351.MP4 | 0.6 min | left_out |
| station1 | 2026-11-22 | left | GX019354.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019355.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | left | GX019363.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019372.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | left | GX019376.MP4 | 0.0 min | left_out |
| station1 | 2026-11-22 | right | GX019377.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | right | GX019382.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019383.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019384.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019385.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | right | GX019386.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | right | GX019387.MP4 | 0.2 min | left_out |
| station1 | 2026-11-22 | right | GX019388.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | right | GX019389.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019390.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019391.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019392.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019394.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019395.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | right | GX019399.MP4 | 0.9 min | left_out |
| station1 | 2026-11-22 | right | GX019402.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019403.MP4 | 0.4 min | left_out |
| station1 | 2026-11-22 | right | GX019411.MP4 | 0.3 min | left_out |
| station1 | 2026-11-22 | right | GX019420.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | head | GX010495.MP4 | 0.4 min | left_out |
| station1 | 2026-11-24 | head | GX010496.MP4 | 1.1 min | left_out |
| station1 | 2026-11-24 | head | GX010500.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | head | GX010503.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | head | GX010504.MP4 | 0.1 min | left_out |
| station1 | 2026-11-24 | head | GX010506.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | head | GX010510.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | head | GX010513.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | head | GX010516.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | head | GX010523.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | head | GX010531.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | head | GX010536.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | head | GX010540.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | head | GX010542.MP4 | 0.8 min | left_out |
| station1 | 2026-11-24 | head | GX010544.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | left | GX019378.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | left | GX019380.MP4 | 1.1 min | left_out |
| station1 | 2026-11-24 | left | GX019381.MP4 | 0.7 min | left_out |
| station1 | 2026-11-24 | left | GX019383.MP4 | 0.8 min | left_out |
| station1 | 2026-11-24 | left | GX019384.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | left | GX019389.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | left | GX019390.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | left | GX019394.MP4 | 0.4 min | left_out |
| station1 | 2026-11-24 | left | GX019396.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | left | GX019397.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | left | GX019401.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | left | GX019403.MP4 | 4.9 min | left_out |
| station1 | 2026-11-24 | left | GX019404.MP4 | 10.1 min | left_out |
| station1 | 2026-11-24 | left | GX019405.MP4 | 10.1 min | left_out |
| station1 | 2026-11-24 | left | GX019411.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | left | GX019419.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | left | GX019424.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | left | GX019430.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | left | GX019431.MP4 | 0.7 min | left_out |
| station1 | 2026-11-24 | right | GX019425.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | right | GX019427.MP4 | 1.1 min | left_out |
| station1 | 2026-11-24 | right | GX019428.MP4 | 0.7 min | left_out |
| station1 | 2026-11-24 | right | GX019430.MP4 | 0.8 min | left_out |
| station1 | 2026-11-24 | right | GX019431.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | right | GX019434.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | right | GX019435.MP4 | 0.1 min | left_out |
| station1 | 2026-11-24 | right | GX019438.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | right | GX019442.MP4 | 0.4 min | left_out |
| station1 | 2026-11-24 | right | GX019444.MP4 | 0.0 min | left_out |
| station1 | 2026-11-24 | right | GX019448.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | right | GX019450.MP4 | 4.8 min | left_out |
| station1 | 2026-11-24 | right | GX019451.MP4 | 10.1 min | left_out |
| station1 | 2026-11-24 | right | GX019452.MP4 | 10.0 min | left_out |
| station1 | 2026-11-24 | right | GX019456.MP4 | 1.4 min | left_out |
| station1 | 2026-11-24 | right | GX019457.MP4 | 0.1 min | left_out |
| station1 | 2026-11-24 | right | GX019460.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | right | GX019468.MP4 | 0.3 min | left_out |
| station1 | 2026-11-24 | right | GX019472.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | right | GX019476.MP4 | 0.2 min | left_out |
| station1 | 2026-11-24 | right | GX019477.MP4 | 0.3 min | left_out |
| station2 | 2026-11-19 | head | GX019309.MP4 | 0.9 min | left_out |
| station2 | 2026-11-19 | left | GX010345.MP4 | 0.8 min | left_out |
| station2 | 2026-11-19 | right | GX010218.MP4 | 0.9 min | left_out |
| station2 | 2026-11-20 | head | GX019310.MP4 | 0.4 min | left_out |
| station2 | 2026-11-20 | head | GX019314.MP4 | 0.5 min | left_out |
| station2 | 2026-11-20 | head | GX019318.MP4 | 0.2 min | left_out |
| station2 | 2026-11-20 | head | GX019321.MP4 | 0.2 min | left_out |
| station2 | 2026-11-20 | head | GX019330.MP4 | 1.3 min | left_out |
| station2 | 2026-11-20 | head | GX019344.MP4 | 0.3 min | left_out |
| station2 | 2026-11-20 | head | GX019351.MP4 | 0.3 min | left_out |
| station2 | 2026-11-20 | head | GX019352.MP4 | 0.4 min | left_out |
| station2 | 2026-11-20 | head | GX019354.MP4 | 0.0 min | left_out |
| station2 | 2026-11-20 | head | GX019358.MP4 | 0.7 min | left_out |
| station2 | 2026-11-20 | head | GX019361.MP4 | 2.8 min | left_out |
| station2 | 2026-11-20 | head | GX019363.MP4 | 0.1 min | left_out |
| station2 | 2026-11-20 | head | GX019364.MP4 | 0.8 min | left_out |
| station2 | 2026-11-20 | left | GX010347.MP4 | 0.7 min | left_out |
| station2 | 2026-11-20 | left | GX010350.MP4 | 0.6 min | left_out |
| station2 | 2026-11-20 | left | GX010355.MP4 | 0.3 min | left_out |
| station2 | 2026-11-20 | left | GX010358.MP4 | 0.3 min | left_out |
| station2 | 2026-11-20 | left | GX010366.MP4 | 0.0 min | left_out |
| station2 | 2026-11-20 | left | GX010381.MP4 | 0.5 min | left_out |
| station2 | 2026-11-20 | left | GX010387.MP4 | 0.3 min | left_out |
| station2 | 2026-11-20 | left | GX010389.MP4 | 0.9 min | left_out |
| station2 | 2026-11-20 | left | GX010393.MP4 | 0.6 min | left_out |
| station2 | 2026-11-20 | right | GX010220.MP4 | 0.7 min | left_out |
| station2 | 2026-11-20 | right | GX010223.MP4 | 0.6 min | left_out |
| station2 | 2026-11-20 | right | GX010228.MP4 | 0.8 min | left_out |
| station2 | 2026-11-20 | right | GX010231.MP4 | 0.6 min | left_out |
| station2 | 2026-11-20 | right | GX010239.MP4 | 1.3 min | left_out |
| station2 | 2026-11-20 | right | GX010254.MP4 | 0.5 min | left_out |
| station2 | 2026-11-20 | right | GX010260.MP4 | 0.3 min | left_out |
| station2 | 2026-11-20 | right | GX010262.MP4 | 0.9 min | left_out |
| station2 | 2026-11-20 | right | GX010266.MP4 | 0.6 min | left_out |
| station2 | 2026-11-20 | right | GX010270.MP4 | 0.8 min | left_out |
| station2 | 2026-11-21 | head | GX019365.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019366.MP4 | 0.6 min | left_out |
| station2 | 2026-11-21 | head | GX019367.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | head | GX019368.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | head | GX019369.MP4 | 9.3 min | left_out |
| station2 | 2026-11-21 | head | GX019370.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019371.MP4 | 10.2 min | left_out |
| station2 | 2026-11-21 | head | GX019372.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | head | GX019373.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019374.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | head | GX019375.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019376.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019377.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | head | GX019378.MP4 | 1.5 min | left_out |
| station2 | 2026-11-21 | head | GX019379.MP4 | 10.6 min | left_out |
| station2 | 2026-11-21 | head | GX019380.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | head | GX019381.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | head | GX019382.MP4 | 8.7 min | left_out |
| station2 | 2026-11-21 | head | GX019383.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019384.MP4 | 0.8 min | left_out |
| station2 | 2026-11-21 | head | GX019385.MP4 | 10.3 min | left_out |
| station2 | 2026-11-21 | head | GX019386.MP4 | 0.0 min | left_out |
| station2 | 2026-11-21 | head | GX019387.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | head | GX019388.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019389.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019390.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | head | GX019391.MP4 | 0.6 min | left_out |
| station2 | 2026-11-21 | head | GX019392.MP4 | 10.2 min | left_out |
| station2 | 2026-11-21 | head | GX019393.MP4 | 9.2 min | left_out |
| station2 | 2026-11-21 | head | GX019394.MP4 | 9.9 min | left_out |
| station2 | 2026-11-21 | head | GX019395.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019396.MP4 | 3.0 min | left_out |
| station2 | 2026-11-21 | head | GX019397.MP4 | 10.2 min | left_out |
| station2 | 2026-11-21 | head | GX019398.MP4 | 4.7 min | left_out |
| station2 | 2026-11-21 | head | GX019399.MP4 | 3.2 min | left_out |
| station2 | 2026-11-21 | head | GX019400.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019401.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019402.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | head | GX019403.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | head | GX019404.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | head | GX019405.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | head | GX019406.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019407.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019408.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | head | GX019409.MP4 | 9.9 min | left_out |
| station2 | 2026-11-21 | head | GX019410.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019411.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | head | GX019412.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019413.MP4 | 7.7 min | left_out |
| station2 | 2026-11-21 | head | GX019414.MP4 | 2.8 min | left_out |
| station2 | 2026-11-21 | head | GX019415.MP4 | 0.1 min | left_out |
| station2 | 2026-11-21 | head | GX019416.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | head | GX019417.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | head | GX019418.MP4 | 2.8 min | left_out |
| station2 | 2026-11-21 | head | GX019419.MP4 | 1.2 min | left_out |
| station2 | 2026-11-21 | left | GX010397.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010398.MP4 | 0.5 min | left_out |
| station2 | 2026-11-21 | left | GX010399.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | left | GX010400.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | left | GX010401.MP4 | 9.3 min | left_out |
| station2 | 2026-11-21 | left | GX010402.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010403.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | left | GX010404.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | left | GX010405.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010406.MP4 | 9.9 min | left_out |
| station2 | 2026-11-21 | left | GX010407.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010408.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010409.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010410.MP4 | 1.5 min | left_out |
| station2 | 2026-11-21 | left | GX010411.MP4 | 10.4 min | left_out |
| station2 | 2026-11-21 | left | GX010412.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | left | GX010413.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | left | GX010414.MP4 | 8.4 min | left_out |
| station2 | 2026-11-21 | left | GX010415.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010416.MP4 | 0.7 min | left_out |
| station2 | 2026-11-21 | left | GX010417.MP4 | 10.3 min | left_out |
| station2 | 2026-11-21 | left | GX010418.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | left | GX010419.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010420.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010421.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | left | GX010422.MP4 | 0.6 min | left_out |
| station2 | 2026-11-21 | left | GX010423.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | left | GX010424.MP4 | 9.2 min | left_out |
| station2 | 2026-11-21 | left | GX010425.MP4 | 9.9 min | left_out |
| station2 | 2026-11-21 | left | GX010426.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010427.MP4 | 3.0 min | left_out |
| station2 | 2026-11-21 | left | GX010428.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | left | GX010429.MP4 | 5.4 min | left_out |
| station2 | 2026-11-21 | left | GX010430.MP4 | 3.3 min | left_out |
| station2 | 2026-11-21 | left | GX010431.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010432.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010433.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010434.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | left | GX010435.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | left | GX010436.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | left | GX010437.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010438.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010439.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010440.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | left | GX010441.MP4 | 0.1 min | left_out |
| station2 | 2026-11-21 | left | GX010442.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | left | GX010443.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010444.MP4 | 7.7 min | left_out |
| station2 | 2026-11-21 | left | GX010445.MP4 | 2.7 min | left_out |
| station2 | 2026-11-21 | left | GX010446.MP4 | 0.1 min | left_out |
| station2 | 2026-11-21 | left | GX010447.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | left | GX010448.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | left | GX010449.MP4 | 2.8 min | left_out |
| station2 | 2026-11-21 | left | GX010450.MP4 | 1.2 min | left_out |
| station2 | 2026-11-21 | right | GX010271.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010272.MP4 | 0.5 min | left_out |
| station2 | 2026-11-21 | right | GX010273.MP4 | 9.6 min | left_out |
| station2 | 2026-11-21 | right | GX010274.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | right | GX010275.MP4 | 9.3 min | left_out |
| station2 | 2026-11-21 | right | GX010276.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010277.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | right | GX010278.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | right | GX010279.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010280.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | right | GX010281.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010282.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010283.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010284.MP4 | 1.5 min | left_out |
| station2 | 2026-11-21 | right | GX010285.MP4 | 10.4 min | left_out |
| station2 | 2026-11-21 | right | GX010286.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | right | GX010287.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | right | GX010288.MP4 | 8.7 min | left_out |
| station2 | 2026-11-21 | right | GX010289.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010290.MP4 | 0.7 min | left_out |
| station2 | 2026-11-21 | right | GX010291.MP4 | 10.3 min | left_out |
| station2 | 2026-11-21 | right | GX010292.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | right | GX010293.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010294.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010295.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | right | GX010296.MP4 | 0.6 min | left_out |
| station2 | 2026-11-21 | right | GX010297.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | right | GX010298.MP4 | 9.2 min | left_out |
| station2 | 2026-11-21 | right | GX010299.MP4 | 9.9 min | left_out |
| station2 | 2026-11-21 | right | GX010300.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010301.MP4 | 3.1 min | left_out |
| station2 | 2026-11-21 | right | GX010302.MP4 | 10.1 min | left_out |
| station2 | 2026-11-21 | right | GX010303.MP4 | 5.4 min | left_out |
| station2 | 2026-11-21 | right | GX010304.MP4 | 3.3 min | left_out |
| station2 | 2026-11-21 | right | GX010305.MP4 | 0.1 min | left_out |
| station2 | 2026-11-21 | right | GX010306.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010307.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010308.MP4 | 9.7 min | left_out |
| station2 | 2026-11-21 | right | GX010309.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | right | GX010310.MP4 | 9.5 min | left_out |
| station2 | 2026-11-21 | right | GX010311.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010312.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010313.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010314.MP4 | 9.8 min | left_out |
| station2 | 2026-11-21 | right | GX010315.MP4 | 0.1 min | left_out |
| station2 | 2026-11-21 | right | GX010316.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | right | GX010317.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010318.MP4 | 7.7 min | left_out |
| station2 | 2026-11-21 | right | GX010319.MP4 | 2.7 min | left_out |
| station2 | 2026-11-21 | right | GX010320.MP4 | 0.4 min | left_out |
| station2 | 2026-11-21 | right | GX010321.MP4 | 0.2 min | left_out |
| station2 | 2026-11-21 | right | GX010322.MP4 | 0.3 min | left_out |
| station2 | 2026-11-21 | right | GX010323.MP4 | 2.8 min | left_out |
| station2 | 2026-11-21 | right | GX010324.MP4 | 1.2 min | left_out |
| station2 | 2026-11-22 | head | GX019420.MP4 | 0.3 min | left_out |
| station2 | 2026-11-22 | head | GX019427.MP4 | 0.0 min | left_out |
| station2 | 2026-11-22 | head | GX019429.MP4 | 10.2 min | left_out |
| station2 | 2026-11-22 | head | GX019432.MP4 | 0.2 min | left_out |
| station2 | 2026-11-22 | head | GX019434.MP4 | 0.0 min | left_out |
| station2 | 2026-11-22 | head | GX019435.MP4 | 0.1 min | left_out |
| station2 | 2026-11-22 | head | GX019440.MP4 | 0.2 min | left_out |
| station2 | 2026-11-22 | head | GX019447.MP4 | 0.2 min | left_out |
| station2 | 2026-11-22 | head | GX019448.MP4 | 0.2 min | left_out |
| station2 | 2026-11-22 | left | GX010458.MP4 | 10.2 min | left_out |
| station2 | 2026-11-22 | left | GX010462.MP4 | 0.3 min | left_out |
| station2 | 2026-11-22 | left | GX010463.MP4 | 10.1 min | left_out |
| station2 | 2026-11-22 | left | GX010470.MP4 | 0.3 min | left_out |
| station2 | 2026-11-22 | left | GX010476.MP4 | 10.2 min | left_out |
| station2 | 2026-11-22 | left | GX010478.MP4 | 0.4 min | left_out |
| station2 | 2026-11-22 | right | GX010326.MP4 | 0.5 min | left_out |
| station2 | 2026-11-22 | right | GX010329.MP4 | 0.8 min | left_out |
| station2 | 2026-11-22 | right | GX010332.MP4 | 0.3 min | left_out |
| station2 | 2026-11-22 | right | GX010333.MP4 | 10.2 min | left_out |
| station2 | 2026-11-22 | right | GX010337.MP4 | 0.3 min | left_out |
| station2 | 2026-11-22 | right | GX010338.MP4 | 10.1 min | left_out |
| station2 | 2026-11-22 | right | GX010344.MP4 | 0.2 min | left_out |
| station2 | 2026-11-22 | right | GX010345.MP4 | 0.3 min | left_out |
| station2 | 2026-11-22 | right | GX010351.MP4 | 10.2 min | left_out |
| station2 | 2026-11-22 | right | GX010353.MP4 | 0.4 min | left_out |
| station2 | 2026-11-22 | right | GX010452.MP4 | 0.5 min | left_out |
| station2 | 2026-11-22 | right | GX010457.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019455.MP4 | 0.5 min | left_out |
| station2 | 2026-11-24 | head | GX019456.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019457.MP4 | 0.6 min | left_out |
| station2 | 2026-11-24 | head | GX019459.MP4 | 5.6 min | left_out |
| station2 | 2026-11-24 | head | GX019461.MP4 | 1.9 min | left_out |
| station2 | 2026-11-24 | head | GX019466.MP4 | 0.0 min | left_out |
| station2 | 2026-11-24 | head | GX019467.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019470.MP4 | 0.1 min | left_out |
| station2 | 2026-11-24 | head | GX019476.MP4 | 0.2 min | left_out |
| station2 | 2026-11-24 | head | GX019481.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019485.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019490.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019494.MP4 | 0.2 min | left_out |
| station2 | 2026-11-24 | head | GX019499.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019501.MP4 | 0.0 min | left_out |
| station2 | 2026-11-24 | head | GX019504.MP4 | 0.2 min | left_out |
| station2 | 2026-11-24 | head | GX019510.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | head | GX019514.MP4 | 0.2 min | left_out |
| station2 | 2026-11-24 | left | GX010359.MP4 | 0.5 min | left_out |
| station2 | 2026-11-24 | left | GX010360.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010361.MP4 | 0.6 min | left_out |
| station2 | 2026-11-24 | left | GX010363.MP4 | 5.6 min | left_out |
| station2 | 2026-11-24 | left | GX010369.MP4 | 0.5 min | left_out |
| station2 | 2026-11-24 | left | GX010376.MP4 | 0.0 min | left_out |
| station2 | 2026-11-24 | left | GX010378.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010382.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010388.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010392.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010397.MP4 | 0.4 min | left_out |
| station2 | 2026-11-24 | left | GX010401.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010406.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010410.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | left | GX010415.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010484.MP4 | 0.5 min | left_out |
| station2 | 2026-11-24 | right | GX010485.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010486.MP4 | 0.6 min | left_out |
| station2 | 2026-11-24 | right | GX010488.MP4 | 5.6 min | left_out |
| station2 | 2026-11-24 | right | GX010490.MP4 | 0.1 min | left_out |
| station2 | 2026-11-24 | right | GX010494.MP4 | 0.0 min | left_out |
| station2 | 2026-11-24 | right | GX010496.MP4 | 0.5 min | left_out |
| station2 | 2026-11-24 | right | GX010504.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010508.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010513.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010517.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010522.MP4 | 0.4 min | left_out |
| station2 | 2026-11-24 | right | GX010526.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010531.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010535.MP4 | 0.3 min | left_out |
| station2 | 2026-11-24 | right | GX010540.MP4 | 0.3 min | left_out |
| station3 | 2026-11-19 | head | GX010160.MP4 | 0.9 min | left_out |
| station3 | 2026-11-19 | left | GX010135.MP4 | 0.7 min | left_out |
| station3 | 2026-11-19 | right | GX019305.MP4 | 0.7 min | left_out |
| station3 | 2026-11-20 | head | GX010166.MP4 | 0.1 min | left_out |
| station3 | 2026-11-20 | head | GX010170.MP4 | 0.3 min | left_out |
| station3 | 2026-11-20 | head | GX010175.MP4 | 0.4 min | left_out |
| station3 | 2026-11-20 | head | GX010181.MP4 | 0.3 min | left_out |
| station3 | 2026-11-20 | left | GX019307.MP4 | 0.5 min | left_out |
| station3 | 2026-11-20 | left | GX019314.MP4 | 0.4 min | left_out |
| station3 | 2026-11-20 | left | GX019315.MP4 | 1.5 min | in_task_unlisted |
| station3 | 2026-11-20 | left | GX019320.MP4 | 0.5 min | left_out |
| station3 | 2026-11-20 | left | GX019326.MP4 | 0.5 min | left_out |
| station3 | 2026-11-20 | right | GX010137.MP4 | 0.5 min | left_out |
| station3 | 2026-11-20 | right | GX010144.MP4 | 0.4 min | left_out |
| station3 | 2026-11-20 | right | GX010145.MP4 | 1.5 min | in_task_unlisted |
| station3 | 2026-11-20 | right | GX010150.MP4 | 0.4 min | left_out |
| station3 | 2026-11-20 | right | GX010156.MP4 | 0.5 min | left_out |
| station3 | 2026-11-21 | head | GX010161.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | head | GX010163.MP4 | 0.0 min | left_out |
| station3 | 2026-11-21 | head | GX010186.MP4 | 0.4 min | left_out |
| station3 | 2026-11-21 | head | GX010188.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | head | GX010193.MP4 | 0.4 min | left_out |
| station3 | 2026-11-21 | head | GX010197.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | head | GX010202.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | head | GX010206.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | head | GX010207.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | head | GX010213.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | head | GX010216.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | left | GX019331.MP4 | 0.6 min | left_out |
| station3 | 2026-11-21 | left | GX019332.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | left | GX019333.MP4 | 0.0 min | left_out |
| station3 | 2026-11-21 | left | GX019337.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | left | GX019343.MP4 | 0.6 min | left_out |
| station3 | 2026-11-21 | left | GX019347.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | left | GX019351.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | left | GX019353.MP4 | 0.4 min | left_out |
| station3 | 2026-11-21 | left | GX019358.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | left | GX019361.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | right | GX010161.MP4 | 0.6 min | left_out |
| station3 | 2026-11-21 | right | GX010162.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | right | GX010163.MP4 | 0.0 min | left_out |
| station3 | 2026-11-21 | right | GX010167.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | right | GX010173.MP4 | 0.5 min | left_out |
| station3 | 2026-11-21 | right | GX010177.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | right | GX010181.MP4 | 0.2 min | left_out |
| station3 | 2026-11-21 | right | GX010183.MP4 | 0.4 min | left_out |
| station3 | 2026-11-21 | right | GX010188.MP4 | 0.3 min | left_out |
| station3 | 2026-11-21 | right | GX010191.MP4 | 0.2 min | left_out |
| station3 | 2026-11-22 | head | GX010217.MP4 | 0.2 min | left_out |
| station3 | 2026-11-22 | head | GX010218.MP4 | 0.5 min | left_out |
| station3 | 2026-11-22 | head | GX010231.MP4 | 0.9 min | left_out |
| station3 | 2026-11-22 | head | GX010233.MP4 | 0.2 min | left_out |
| station3 | 2026-11-22 | head | GX010241.MP4 | 0.1 min | left_out |
| station3 | 2026-11-22 | head | GX010244.MP4 | 0.2 min | left_out |
| station3 | 2026-11-22 | left | GX019363.MP4 | 0.4 min | left_out |
| station3 | 2026-11-22 | left | GX019364.MP4 | 0.4 min | left_out |
| station3 | 2026-11-22 | left | GX019377.MP4 | 0.9 min | left_out |
| station3 | 2026-11-22 | left | GX019380.MP4 | 0.3 min | left_out |
| station3 | 2026-11-22 | left | GX019384.MP4 | 0.3 min | left_out |
| station3 | 2026-11-22 | left | GX019390.MP4 | 0.3 min | left_out |
| station3 | 2026-11-22 | right | GX010193.MP4 | 0.4 min | left_out |
| station3 | 2026-11-22 | right | GX010194.MP4 | 0.5 min | left_out |
| station3 | 2026-11-22 | right | GX010206.MP4 | 0.9 min | left_out |
| station3 | 2026-11-22 | right | GX010209.MP4 | 0.3 min | left_out |
| station3 | 2026-11-22 | right | GX010213.MP4 | 0.3 min | left_out |
| station3 | 2026-11-22 | right | GX010219.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | head | GX010252.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | head | GX010254.MP4 | 0.9 min | left_out |
| station3 | 2026-11-24 | head | GX010259.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | head | GX010263.MP4 | 0.4 min | left_out |
| station3 | 2026-11-24 | head | GX010265.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | head | GX010266.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | head | GX010271.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | head | GX010275.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | head | GX010280.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | head | GX010284.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | head | GX010289.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | head | GX010291.MP4 | 0.5 min | left_out |
| station3 | 2026-11-24 | left | GX019398.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | left | GX019399.MP4 | 0.8 min | left_out |
| station3 | 2026-11-24 | left | GX019406.MP4 | 0.0 min | left_out |
| station3 | 2026-11-24 | left | GX019408.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | left | GX019414.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | left | GX019415.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | left | GX019416.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | left | GX019420.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | left | GX019425.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | left | GX019429.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | left | GX019434.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | left | GX019438.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | left | GX019440.MP4 | 0.6 min | left_out |
| station3 | 2026-11-24 | right | GX010227.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | right | GX010228.MP4 | 0.8 min | left_out |
| station3 | 2026-11-24 | right | GX010234.MP4 | 0.0 min | left_out |
| station3 | 2026-11-24 | right | GX010236.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | right | GX010242.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | right | GX010243.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | right | GX010244.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | right | GX010248.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | right | GX010253.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | right | GX010257.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | right | GX010262.MP4 | 0.3 min | left_out |
| station3 | 2026-11-24 | right | GX010266.MP4 | 0.2 min | left_out |
| station3 | 2026-11-24 | right | GX010268.MP4 | 0.6 min | left_out |
| station4 | 2026-11-21 | head | GX010931.MP4 | 0.8 min | left_out |
| station4 | 2026-11-21 | head | GX010934.MP4 | 10.4 min | left_out |
| station4 | 2026-11-21 | head | GX010935.MP4 | 0.9 min | left_out |
| station4 | 2026-11-21 | head | GX010936.MP4 | 1.4 min | left_out |
| station4 | 2026-11-21 | head | GX010937.MP4 | 11.2 min | left_out |
| station4 | 2026-11-21 | head | GX010938.MP4 | 4.7 min | left_out |
| station4 | 2026-11-21 | head | GX010944.MP4 | 0.2 min | left_out |
| station4 | 2026-11-21 | head | GX010945.MP4 | 0.4 min | left_out |
| station4 | 2026-11-21 | head | GX010951.MP4 | 0.5 min | left_out |
| station4 | 2026-11-21 | head | GX010952.MP4 | 0.2 min | left_out |
| station4 | 2026-11-21 | head | GX010957.MP4 | 0.3 min | left_out |
| station4 | 2026-11-21 | head | GX010960.MP4 | 0.3 min | left_out |
| station4 | 2026-11-21 | left | GX011220.MP4 | 0.4 min | left_out |
| station4 | 2026-11-21 | left | GX011221.MP4 | 0.6 min | left_out |
| station4 | 2026-11-21 | left | GX011222.MP4 | 0.7 min | left_out |
| station4 | 2026-11-21 | left | GX011225.MP4 | 10.3 min | left_out |
| station4 | 2026-11-21 | left | GX011226.MP4 | 0.1 min | left_out |
| station4 | 2026-11-21 | left | GX011227.MP4 | 0.1 min | left_out |
| station4 | 2026-11-21 | left | GX011228.MP4 | 1.2 min | left_out |
| station4 | 2026-11-21 | left | GX011229.MP4 | 11.2 min | left_out |
| station4 | 2026-11-21 | left | GX011230.MP4 | 4.6 min | left_out |
| station4 | 2026-11-21 | left | GX011235.MP4 | 0.3 min | left_out |
| station4 | 2026-11-21 | left | GX011236.MP4 | 0.5 min | left_out |
| station4 | 2026-11-21 | left | GX011241.MP4 | 0.1 min | left_out |
| station4 | 2026-11-21 | left | GX011242.MP4 | 0.5 min | left_out |
| station4 | 2026-11-21 | left | GX011246.MP4 | 0.4 min | left_out |
| station4 | 2026-11-21 | left | GX011249.MP4 | 0.6 min | left_out |
| station4 | 2026-11-21 | left | GX011251.MP4 | 0.3 min | left_out |
| station4 | 2026-11-21 | right | GX010905.MP4 | 0.4 min | left_out |
| station4 | 2026-11-21 | right | GX010906.MP4 | 0.6 min | left_out |
| station4 | 2026-11-21 | right | GX010907.MP4 | 0.7 min | left_out |
| station4 | 2026-11-21 | right | GX010913.MP4 | 0.0 min | left_out |
| station4 | 2026-11-21 | right | GX010914.MP4 | 11.2 min | left_out |
| station4 | 2026-11-21 | right | GX010915.MP4 | 4.6 min | left_out |
| station4 | 2026-11-21 | right | GX010920.MP4 | 0.3 min | left_out |
| station4 | 2026-11-21 | right | GX010921.MP4 | 0.5 min | left_out |
| station4 | 2026-11-21 | right | GX010926.MP4 | 0.1 min | left_out |
| station4 | 2026-11-21 | right | GX010927.MP4 | 0.5 min | left_out |
| station4 | 2026-11-21 | right | GX010931.MP4 | 0.4 min | left_out |
| station4 | 2026-11-21 | right | GX010934.MP4 | 0.6 min | left_out |
| station4 | 2026-11-21 | right | GX010936.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | head | GX010962.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | head | GX010963.MP4 | 0.4 min | left_out |
| station4 | 2026-11-22 | head | GX010966.MP4 | 0.0 min | left_out |
| station4 | 2026-11-22 | head | GX010968.MP4 | 0.0 min | left_out |
| station4 | 2026-11-22 | head | GX010971.MP4 | 0.4 min | left_out |
| station4 | 2026-11-22 | head | GX010975.MP4 | 0.1 min | left_out |
| station4 | 2026-11-22 | head | GX010976.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | head | GX010981.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | head | GX010985.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | head | GX010989.MP4 | 10.2 min | left_out |
| station4 | 2026-11-22 | head | GX010991.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | left | GX011254.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | left | GX011255.MP4 | 0.6 min | left_out |
| station4 | 2026-11-22 | left | GX011258.MP4 | 10.4 min | left_out |
| station4 | 2026-11-22 | left | GX011261.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | left | GX011265.MP4 | 0.1 min | left_out |
| station4 | 2026-11-22 | left | GX011267.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | left | GX011268.MP4 | 2.2 min | left_out |
| station4 | 2026-11-22 | left | GX011270.MP4 | 5.1 min | left_out |
| station4 | 2026-11-22 | left | GX011273.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | left | GX011278.MP4 | 0.4 min | left_out |
| station4 | 2026-11-22 | left | GX011281.MP4 | 10.2 min | left_out |
| station4 | 2026-11-22 | left | GX011283.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | left | GX011286.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | right | GX010939.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | right | GX010940.MP4 | 0.6 min | left_out |
| station4 | 2026-11-22 | right | GX010943.MP4 | 10.4 min | left_out |
| station4 | 2026-11-22 | right | GX010946.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | right | GX010950.MP4 | 0.0 min | left_out |
| station4 | 2026-11-22 | right | GX010952.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | right | GX010953.MP4 | 2.2 min | left_out |
| station4 | 2026-11-22 | right | GX010955.MP4 | 5.1 min | left_out |
| station4 | 2026-11-22 | right | GX010958.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | right | GX010963.MP4 | 0.3 min | left_out |
| station4 | 2026-11-22 | right | GX010966.MP4 | 10.2 min | left_out |
| station4 | 2026-11-22 | right | GX010968.MP4 | 0.2 min | left_out |
| station4 | 2026-11-22 | right | GX010971.MP4 | 0.2 min | left_out |
| station4 | 2026-11-24 | head | GX010996.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | head | GX010998.MP4 | 0.6 min | left_out |
| station4 | 2026-11-24 | head | GX010999.MP4 | 0.1 min | left_out |
| station4 | 2026-11-24 | head | GX011000.MP4 | 0.1 min | left_out |
| station4 | 2026-11-24 | head | GX011001.MP4 | 0.1 min | left_out |
| station4 | 2026-11-24 | head | GX011002.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | head | GX011006.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | head | GX011008.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | head | GX011013.MP4 | 0.2 min | left_out |
| station4 | 2026-11-24 | head | GX011020.MP4 | 0.9 min | left_out |
| station4 | 2026-11-24 | head | GX011021.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | head | GX011023.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | head | GX011025.MP4 | 0.2 min | left_out |
| station4 | 2026-11-24 | head | GX011026.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | head | GX011029.MP4 | 0.1 min | left_out |
| station4 | 2026-11-24 | head | GX011030.MP4 | 1.6 min | left_out |
| station4 | 2026-11-24 | left | GX011289.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | left | GX011290.MP4 | 0.5 min | left_out |
| station4 | 2026-11-24 | left | GX011291.MP4 | 0.6 min | left_out |
| station4 | 2026-11-24 | left | GX011292.MP4 | 0.8 min | left_out |
| station4 | 2026-11-24 | left | GX011293.MP4 | 6.3 min | left_out |
| station4 | 2026-11-24 | left | GX011297.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | left | GX011300.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | left | GX011306.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | left | GX011312.MP4 | 0.8 min | left_out |
| station4 | 2026-11-24 | left | GX011313.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | left | GX011315.MP4 | 0.2 min | left_out |
| station4 | 2026-11-24 | left | GX011318.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | left | GX011319.MP4 | 0.7 min | left_out |
| station4 | 2026-11-24 | right | GX010974.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | right | GX010975.MP4 | 0.5 min | left_out |
| station4 | 2026-11-24 | right | GX010976.MP4 | 0.6 min | left_out |
| station4 | 2026-11-24 | right | GX010977.MP4 | 25.2 min | left_out |
| station4 | 2026-11-24 | right | GX010978.MP4 | 7.5 min | left_out |
| station4 | 2026-11-24 | right | GX010982.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | right | GX010985.MP4 | 0.4 min | left_out |
| station4 | 2026-11-24 | right | GX010991.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | right | GX010997.MP4 | 0.8 min | left_out |
| station4 | 2026-11-24 | right | GX010998.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | right | GX011002.MP4 | 0.2 min | left_out |
| station4 | 2026-11-24 | right | GX011003.MP4 | 0.3 min | left_out |
| station4 | 2026-11-24 | right | GX011004.MP4 | 0.7 min | left_out |
| station4 | 2026-11-24 | right | GX011006.MP4 | 1.6 min | left_out |
| station5 | 2026-11-21 | head | GX010581.MP4 | 0.3 min | left_out |
| station5 | 2026-11-21 | head | GX010582.MP4 | 0.5 min | left_out |
| station5 | 2026-11-21 | head | GX010583.MP4 | 1.2 min | left_out |
| station5 | 2026-11-21 | head | GX010584.MP4 | 10.4 min | left_out |
| station5 | 2026-11-21 | head | GX010585.MP4 | 10.0 min | left_out |
| station5 | 2026-11-21 | head | GX010586.MP4 | 7.1 min | left_out |
| station5 | 2026-11-21 | head | GX010587.MP4 | 9.9 min | left_out |
| station5 | 2026-11-21 | head | GX010588.MP4 | 0.4 min | left_out |
| station5 | 2026-11-21 | head | GX010589.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010590.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010591.MP4 | 0.2 min | left_out |
| station5 | 2026-11-21 | head | GX010592.MP4 | 7.5 min | left_out |
| station5 | 2026-11-21 | head | GX010593.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010594.MP4 | 0.1 min | left_out |
| station5 | 2026-11-21 | head | GX010595.MP4 | 0.2 min | left_out |
| station5 | 2026-11-21 | head | GX010596.MP4 | 0.6 min | left_out |
| station5 | 2026-11-21 | head | GX010597.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010598.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010599.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010600.MP4 | 0.4 min | left_out |
| station5 | 2026-11-21 | head | GX010601.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | head | GX010602.MP4 | 10.0 min | left_out |
| station5 | 2026-11-21 | head | GX010603.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010323.MP4 | 0.4 min | left_out |
| station5 | 2026-11-21 | left | GX010324.MP4 | 0.5 min | left_out |
| station5 | 2026-11-21 | left | GX010325.MP4 | 1.2 min | left_out |
| station5 | 2026-11-21 | left | GX010326.MP4 | 10.4 min | left_out |
| station5 | 2026-11-21 | left | GX010327.MP4 | 10.0 min | left_out |
| station5 | 2026-11-21 | left | GX010328.MP4 | 6.8 min | left_out |
| station5 | 2026-11-21 | left | GX010329.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010330.MP4 | 0.4 min | left_out |
| station5 | 2026-11-21 | left | GX010331.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010332.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010333.MP4 | 0.2 min | left_out |
| station5 | 2026-11-21 | left | GX010334.MP4 | 6.5 min | left_out |
| station5 | 2026-11-21 | left | GX010335.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010336.MP4 | 0.0 min | left_out |
| station5 | 2026-11-21 | left | GX010337.MP4 | 0.2 min | left_out |
| station5 | 2026-11-21 | left | GX010338.MP4 | 0.6 min | left_out |
| station5 | 2026-11-21 | left | GX010339.MP4 | 6.8 min | left_out |
| station5 | 2026-11-21 | left | GX010340.MP4 | 2.4 min | left_out |
| station5 | 2026-11-21 | left | GX010341.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010342.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010343.MP4 | 0.3 min | left_out |
| station5 | 2026-11-21 | left | GX010344.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010345.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | left | GX010346.MP4 | 7.3 min | left_out |
| station5 | 2026-11-21 | left | GX010347.MP4 | 2.0 min | left_out |
| station5 | 2026-11-21 | right | GX010265.MP4 | 0.3 min | left_out |
| station5 | 2026-11-21 | right | GX010266.MP4 | 0.5 min | left_out |
| station5 | 2026-11-21 | right | GX010267.MP4 | 1.1 min | left_out |
| station5 | 2026-11-21 | right | GX010268.MP4 | 10.4 min | left_out |
| station5 | 2026-11-21 | right | GX010269.MP4 | 10.0 min | left_out |
| station5 | 2026-11-21 | right | GX010270.MP4 | 7.1 min | left_out |
| station5 | 2026-11-21 | right | GX010271.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010272.MP4 | 0.4 min | left_out |
| station5 | 2026-11-21 | right | GX010273.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010274.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010275.MP4 | 0.2 min | left_out |
| station5 | 2026-11-21 | right | GX010276.MP4 | 7.4 min | left_out |
| station5 | 2026-11-21 | right | GX010277.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010278.MP4 | 0.0 min | left_out |
| station5 | 2026-11-21 | right | GX010279.MP4 | 0.2 min | left_out |
| station5 | 2026-11-21 | right | GX010280.MP4 | 0.5 min | left_out |
| station5 | 2026-11-21 | right | GX010281.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010282.MP4 | 10.0 min | left_out |
| station5 | 2026-11-21 | right | GX010283.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010284.MP4 | 0.3 min | left_out |
| station5 | 2026-11-21 | right | GX010285.MP4 | 10.1 min | left_out |
| station5 | 2026-11-21 | right | GX010286.MP4 | 10.0 min | left_out |
| station5 | 2026-11-21 | right | GX010287.MP4 | 10.0 min | left_out |
| station5 | 2026-11-22 | head | GX010604.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | head | GX010605.MP4 | 0.4 min | left_out |
| station5 | 2026-11-22 | head | GX010606.MP4 | 0.2 min | left_out |
| station5 | 2026-11-22 | head | GX010613.MP4 | 0.2 min | left_out |
| station5 | 2026-11-22 | left | GX010348.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | left | GX010349.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | left | GX010351.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | left | GX010357.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | right | GX010172.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | right | GX010173.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | right | GX010175.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | right | GX010187.MP4 | 0.3 min | left_out |
| station5 | 2026-11-22 | right | GX010195.MP4 | 0.0 min | left_out |
| station5 | 2026-11-22 | right | GX010196.MP4 | 0.0 min | left_out |
| station5 | 2026-11-22 | right | GX010197.MP4 | 0.1 min | left_out |
| station5 | 2026-11-22 | right | GX010198.MP4 | 0.0 min | left_out |
| station5 | 2026-11-24 | head | GX010620.MP4 | 0.4 min | left_out |
| station5 | 2026-11-24 | head | GX010622.MP4 | 10.5 min | left_out |
| station5 | 2026-11-24 | head | GX010627.MP4 | 0.3 min | left_out |
| station5 | 2026-11-24 | left | GX010364.MP4 | 0.4 min | left_out |
| station5 | 2026-11-24 | left | GX010365.MP4 | 10.4 min | left_out |
| station5 | 2026-11-24 | right | GX010201.MP4 | 0.4 min | left_out |
| station5 | 2026-11-24 | right | GX010202.MP4 | 10.4 min | left_out |

## Pairing problems (4)

- station2/industrial_data_2026-11-22/task01/raw_videos: take 2 left = GX010453.MP4, but that file is in the right dump (2026-11-22)
- station2/industrial_data_2026-11-22/task01/raw_videos: take 3 left = GX010454.MP4, but that file is in the right dump (2026-11-22)
- station2/industrial_data_2026-11-22/task02/raw_videos: take 5 left = GX010455.MP4, but that file is in the right dump (2026-11-22)
- station2/industrial_data_2026-11-22/task02/raw_videos: take 6 left = GX010456.MP4, but that file is in the right dump (2026-11-22)

Files: `videos.csv` (every raw video with its status and use), `takes.csv` (every take: files, lengths, shared window, mismatch, note), `tasks.csv` (per task folder: takes, hours, episodes, yield).
