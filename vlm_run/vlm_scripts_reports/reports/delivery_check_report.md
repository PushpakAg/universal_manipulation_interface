# UMI delivery check: s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/

Checked against DataPRD1019 v1.1 (docs/UMI_delivery_checklist.md); header + every frame timestamp.
Not checked in this run: corrupt frames (V8, run with --decode). Deliverable means: passes every check that ran.

Two separate verdicts per recording. **Data checks** (files, sync, frames, length, warnings: D1, D2, D3, D4, D5, D6, V1, V2, V3, V4, V5, V6, V7, V8, V9, C3, W1, W5, W6, W7, W8, W9, W10, W11) decide what is deliverable here. **Repetition checks** (C1, C2, W2, W3, W4) rest on the VLM cycle count until a person counts, so they are reported apart and do not change the data-check numbers.

**Data checks: deliverable 1772 of 2325 recordings, 20.26 h of 23.20 h** (76.2%). Review: 1 (0.02 h). Fail: 552 (2.92 h).

**Repetition checks (VLM count, guidance):** pass 852 (10.04 h), review 541 (6.96 h), fail 932 (6.20 h). Both pass: 720 (8.71 h).

## Data checks

| Level | Name | Recordings | Hours | Deliverable | Deliverable h | Review | Review h | Fail | Fail h | Fail checks |
|---|---|---|---|---|---|---|---|---|---|---|
| task | industrial_data_mp4 | 15 | 0.10 | 0 | 0.00 | 0 | 0.00 | 15 | 0.10 | D6 not a duplicate x15, C3 at least 9 s long x1 |
| task | station1/2026-11-21/task01 | 91 | 0.70 | 0 | 0.00 | 0 | 0.00 | 91 | 0.70 | V9 left / right views not swapped (--views) x90, C3 at least 9 s long x1 |
| task | station1/2026-11-21/task02 | 142 | 0.54 | 0 | 0.00 | 0 | 0.00 | 142 | 0.54 | V9 left / right views not swapped (--views) x140, C3 at least 9 s long x37 |
| task | station1/2026-11-21/task03 | 158 | 0.38 | 36 | 0.16 | 0 | 0.00 | 122 | 0.21 | C3 at least 9 s long x122, V9 left / right views not swapped (--views) x1 |
| task | station1/2026-11-21/task04 | 28 | 0.25 | 27 | 0.25 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-21/task05 | 16 | 0.12 | 16 | 0.12 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/2026-11-22/task01 | 31 | 0.23 | 31 | 0.23 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/2026-11-22/task02 | 41 | 0.24 | 40 | 0.24 | 0 | 0.00 | 1 | 0.00 | V9 left / right views not swapped (--views) x1, C3 at least 9 s long x1 |
| task | station1/2026-11-22/task03 | 10 | 0.06 | 10 | 0.06 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/2026-11-22/task04 | 56 | 0.58 | 56 | 0.58 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/2026-11-22/task05 | 49 | 0.28 | 47 | 0.27 | 0 | 0.00 | 2 | 0.01 | C3 at least 9 s long x2 |
| task | station1/2026-11-22/task06 | 10 | 0.24 | 0 | 0.00 | 0 | 0.00 | 10 | 0.24 | V9 left / right views not swapped (--views) x10 |
| task | station1/2026-11-22/task07 | 32 | 0.14 | 31 | 0.14 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-24/task01 | 14 | 0.10 | 12 | 0.08 | 1 | 0.02 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-24/task02 | 52 | 0.23 | 39 | 0.22 | 0 | 0.00 | 13 | 0.02 | C3 at least 9 s long x13 |
| task | station1/2026-11-24/task03 | 32 | 0.23 | 27 | 0.22 | 0 | 0.00 | 5 | 0.01 | C3 at least 9 s long x5, V9 left / right views not swapped (--views) x1 |
| task | station1/2026-11-24/task04 | 27 | 0.23 | 26 | 0.23 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-24/task05 | 23 | 0.35 | 23 | 0.35 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/2026-11-24/task06 | 11 | 0.47 | 10 | 0.46 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-24/task07 | 14 | 0.56 | 14 | 0.56 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/2026-11-24/task08 | 18 | 0.25 | 18 | 0.25 | 0 | 0.00 | 0 | 0.00 |  |
| task | station1/task03 | 46 | 0.31 | 44 | 0.30 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station1/task04 | 49 | 0.28 | 48 | 0.28 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/task05 | 50 | 0.33 | 48 | 0.32 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station2/2026-11-22/task01 | 15 | 0.10 | 14 | 0.10 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station2/2026-11-22/task02 | 26 | 0.18 | 26 | 0.18 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-22/task03 | 21 | 0.15 | 21 | 0.15 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-22/task04 | 9 | 0.18 | 2 | 0.05 | 0 | 0.00 | 7 | 0.13 | V9 left / right views not swapped (--views) x7 |
| task | station2/2026-11-22/task05 | 43 | 0.58 | 0 | 0.00 | 0 | 0.00 | 43 | 0.58 | V9 left / right views not swapped (--views) x43 |
| task | station2/2026-11-22/task06 | 41 | 0.32 | 0 | 0.00 | 0 | 0.00 | 41 | 0.32 | V9 left / right views not swapped (--views) x40, C3 at least 9 s long x3 |
| task | station2/2026-11-24/task00 | 22 | 0.45 | 22 | 0.45 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-24/task01 | 15 | 0.35 | 14 | 0.35 | 0 | 0.00 | 1 | 0.00 | V9 left / right views not swapped (--views) x1, C3 at least 9 s long x1 |
| task | station2/2026-11-24/task02 | 34 | 0.72 | 34 | 0.72 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-24/task03 | 26 | 0.83 | 26 | 0.83 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-24/task04 | 38 | 0.82 | 38 | 0.82 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-24/task05 | 25 | 0.72 | 24 | 0.72 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station2/2026-11-24/task06 | 5 | 0.27 | 5 | 0.27 | 0 | 0.00 | 0 | 0.00 |  |
| task | station3/2026-11-21/task02 | 33 | 0.28 | 33 | 0.28 | 0 | 0.00 | 0 | 0.00 |  |
| task | station3/2026-11-21/task03 | 87 | 0.59 | 86 | 0.59 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station3/2026-11-22/task01 | 65 | 0.58 | 65 | 0.58 | 0 | 0.00 | 0 | 0.00 |  |
| task | station3/2026-11-22/task04 | 57 | 0.50 | 56 | 0.50 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station3/2026-11-24/task01 | 67 | 0.84 | 66 | 0.84 | 0 | 0.00 | 1 | 0.00 | V9 left / right views not swapped (--views) x1, C3 at least 9 s long x1 |
| task | station3/2026-11-24/task02 | 27 | 0.58 | 27 | 0.58 | 0 | 0.00 | 0 | 0.00 |  |
| task | station3/2026-11-24/task03 | 50 | 0.71 | 48 | 0.71 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station3/2026-11-24/task04 | 35 | 0.73 | 35 | 0.73 | 0 | 0.00 | 0 | 0.00 |  |
| task | station3/task03 | 26 | 0.42 | 26 | 0.42 | 0 | 0.00 | 0 | 0.00 |  |
| task | station3/task04 | 31 | 0.27 | 31 | 0.27 | 0 | 0.00 | 0 | 0.00 |  |
| task | station4/2026-11-21/task00 | 33 | 0.12 | 19 | 0.10 | 0 | 0.00 | 14 | 0.01 | C3 at least 9 s long x14 |
| task | station4/2026-11-21/task01 | 109 | 0.54 | 101 | 0.53 | 0 | 0.00 | 8 | 0.01 | C3 at least 9 s long x8, V9 left / right views not swapped (--views) x1 |
| task | station4/2026-11-21/task02 | 16 | 0.07 | 14 | 0.06 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station4/2026-11-21/task03 | 22 | 0.21 | 21 | 0.21 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station4/2026-11-22/task01 | 63 | 0.54 | 61 | 0.54 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station4/2026-11-22/task02 | 30 | 0.68 | 29 | 0.68 | 0 | 0.00 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station4/2026-11-22/task03 | 39 | 0.26 | 29 | 0.25 | 0 | 0.00 | 10 | 0.01 | C3 at least 9 s long x10, V9 left / right views not swapped (--views) x5 |
| task | station4/2026-11-24/task01 | 17 | 0.11 | 17 | 0.11 | 0 | 0.00 | 0 | 0.00 |  |
| task | station4/2026-11-24/task02 | 44 | 0.35 | 42 | 0.35 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station4/2026-11-24/task03 | 38 | 0.64 | 38 | 0.64 | 0 | 0.00 | 0 | 0.00 |  |
| task | station4/2026-11-24/task04 | 43 | 0.43 | 41 | 0.42 | 0 | 0.00 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station5/2026-11-22/task01 | 7 | 0.15 | 7 | 0.15 | 0 | 0.00 | 0 | 0.00 |  |
| task | station5/2026-11-24/task01 | 29 | 0.42 | 29 | 0.42 | 0 | 0.00 | 0 | 0.00 |  |
| task | station5/2026-11-24/task02 | 22 | 0.32 | 22 | 0.32 | 0 | 0.00 | 0 | 0.00 |  |
| station | industrial_data_mp4 | 15 | 0.10 | 0 | 0.00 | 0 | 0.00 | 15 | 0.10 | D6 not a duplicate x15, C3 at least 9 s long x1 |
| station | station1 | 1000 | 7.10 | 603 | 5.34 | 1 | 0.02 | 396 | 1.74 | V9 left / right views not swapped (--views) x243, C3 at least 9 s long x191 |
| station | station2 | 320 | 5.67 | 226 | 4.64 | 0 | 0.00 | 94 | 1.03 | V9 left / right views not swapped (--views) x91, C3 at least 9 s long x6 |
| station | station3 | 478 | 5.50 | 473 | 5.49 | 0 | 0.00 | 5 | 0.01 | C3 at least 9 s long x5, V9 left / right views not swapped (--views) x1 |
| station | station4 | 454 | 3.94 | 412 | 3.90 | 0 | 0.00 | 42 | 0.04 | C3 at least 9 s long x42, V9 left / right views not swapped (--views) x6 |
| station | station5 | 58 | 0.90 | 58 | 0.90 | 0 | 0.00 | 0 | 0.00 |  |
| all | ALL | 2325 | 23.20 | 1772 | 20.26 | 1 | 0.02 | 552 | 2.92 | V9 left / right views not swapped (--views) x341, C3 at least 9 s long x245, D6 not a duplicate x15 |

## Repetition checks (VLM count; a hand count in manual_counts.csv overrides it)

| Level | Name | Recordings | Pass | Pass h | Review | Review h | Fail | Fail h | Both pass | Both pass h | Checks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| task | industrial_data_mp4 | 15 | 0 | 0.00 | 15 | 0.10 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x15, C2 REVIEW x15 |
| task | station1/2026-11-21/task01 | 91 | 75 | 0.62 | 0 | 0.00 | 16 | 0.09 | 0 | 0.00 | C1 FAIL x16 |
| task | station1/2026-11-21/task02 | 142 | 1 | 0.00 | 0 | 0.00 | 141 | 0.54 | 0 | 0.00 | C1 FAIL x141 |
| task | station1/2026-11-21/task03 | 158 | 1 | 0.01 | 1 | 0.00 | 156 | 0.36 | 1 | 0.01 | C1 FAIL x156, C1 REVIEW x1 |
| task | station1/2026-11-21/task04 | 28 | 18 | 0.17 | 0 | 0.00 | 10 | 0.09 | 18 | 0.17 | C1 FAIL x10 |
| task | station1/2026-11-21/task05 | 16 | 0 | 0.00 | 0 | 0.00 | 16 | 0.12 | 0 | 0.00 | C1 FAIL x16 |
| task | station1/2026-11-22/task01 | 31 | 23 | 0.17 | 0 | 0.00 | 8 | 0.06 | 23 | 0.17 | C1 FAIL x8 |
| task | station1/2026-11-22/task02 | 41 | 32 | 0.20 | 0 | 0.00 | 9 | 0.04 | 32 | 0.20 | C1 FAIL x9 |
| task | station1/2026-11-22/task03 | 10 | 8 | 0.05 | 0 | 0.00 | 2 | 0.01 | 8 | 0.05 | C1 FAIL x2 |
| task | station1/2026-11-22/task04 | 56 | 42 | 0.46 | 0 | 0.00 | 14 | 0.11 | 42 | 0.46 | C1 FAIL x14 |
| task | station1/2026-11-22/task05 | 49 | 40 | 0.23 | 0 | 0.00 | 9 | 0.04 | 40 | 0.23 | C1 FAIL x9 |
| task | station1/2026-11-22/task06 | 10 | 3 | 0.09 | 0 | 0.00 | 7 | 0.15 | 0 | 0.00 | C1 FAIL x7 |
| task | station1/2026-11-22/task07 | 32 | 13 | 0.06 | 1 | 0.00 | 18 | 0.07 | 13 | 0.06 | C1 FAIL x18, C2 REVIEW x1 |
| task | station1/2026-11-24/task01 | 14 | 0 | 0.00 | 0 | 0.00 | 14 | 0.10 | 0 | 0.00 | C1 FAIL x14 |
| task | station1/2026-11-24/task02 | 52 | 2 | 0.01 | 1 | 0.01 | 49 | 0.21 | 2 | 0.01 | C1 FAIL x49, C1 REVIEW x1 |
| task | station1/2026-11-24/task03 | 32 | 6 | 0.09 | 1 | 0.01 | 25 | 0.13 | 6 | 0.09 | C1 FAIL x25, C1 REVIEW x1 |
| task | station1/2026-11-24/task04 | 27 | 25 | 0.23 | 0 | 0.00 | 2 | 0.01 | 25 | 0.23 | C1 FAIL x2 |
| task | station1/2026-11-24/task05 | 23 | 18 | 0.27 | 0 | 0.00 | 5 | 0.08 | 18 | 0.27 | C1 FAIL x5 |
| task | station1/2026-11-24/task06 | 11 | 8 | 0.36 | 1 | 0.06 | 2 | 0.05 | 8 | 0.36 | C1 FAIL x2, C1 REVIEW x1 |
| task | station1/2026-11-24/task07 | 14 | 14 | 0.56 | 0 | 0.00 | 0 | 0.00 | 14 | 0.56 |  |
| task | station1/2026-11-24/task08 | 18 | 15 | 0.21 | 1 | 0.01 | 2 | 0.03 | 15 | 0.21 | C1 FAIL x2, C1 REVIEW x1 |
| task | station1/task03 | 46 | 11 | 0.09 | 0 | 0.00 | 35 | 0.22 | 11 | 0.09 | C1 FAIL x35 |
| task | station1/task04 | 49 | 24 | 0.16 | 0 | 0.00 | 25 | 0.12 | 24 | 0.16 | C1 FAIL x25 |
| task | station1/task05 | 50 | 38 | 0.27 | 0 | 0.00 | 12 | 0.06 | 38 | 0.27 | C1 FAIL x12 |
| task | station2/2026-11-22/task01 | 15 | 13 | 0.09 | 0 | 0.00 | 2 | 0.01 | 13 | 0.09 | C1 FAIL x2 |
| task | station2/2026-11-22/task02 | 26 | 26 | 0.18 | 0 | 0.00 | 0 | 0.00 | 26 | 0.18 |  |
| task | station2/2026-11-22/task03 | 21 | 21 | 0.15 | 0 | 0.00 | 0 | 0.00 | 21 | 0.15 |  |
| task | station2/2026-11-22/task04 | 9 | 2 | 0.06 | 0 | 0.00 | 7 | 0.12 | 1 | 0.04 | C1 FAIL x7 |
| task | station2/2026-11-22/task05 | 43 | 36 | 0.48 | 6 | 0.09 | 1 | 0.01 | 0 | 0.00 | C2 REVIEW x6, C1 FAIL x1 |
| task | station2/2026-11-22/task06 | 41 | 16 | 0.13 | 4 | 0.02 | 21 | 0.17 | 0 | 0.00 | C1 FAIL x21, C2 REVIEW x4 |
| task | station2/2026-11-24/task00 | 22 | 18 | 0.37 | 0 | 0.00 | 4 | 0.08 | 18 | 0.37 | C1 FAIL x4 |
| task | station2/2026-11-24/task01 | 15 | 4 | 0.12 | 8 | 0.19 | 3 | 0.04 | 4 | 0.12 | C1 REVIEW x8, C2 REVIEW x8, C1 FAIL x3 |
| task | station2/2026-11-24/task02 | 34 | 0 | 0.00 | 34 | 0.72 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x34, C2 REVIEW x34 |
| task | station2/2026-11-24/task03 | 26 | 0 | 0.00 | 26 | 0.83 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x26, C2 REVIEW x26 |
| task | station2/2026-11-24/task04 | 38 | 0 | 0.00 | 38 | 0.82 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x38, C2 REVIEW x38 |
| task | station2/2026-11-24/task05 | 25 | 0 | 0.00 | 25 | 0.72 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x25, C2 REVIEW x25 |
| task | station2/2026-11-24/task06 | 5 | 0 | 0.00 | 5 | 0.27 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x5, C2 REVIEW x5 |
| task | station3/2026-11-21/task02 | 33 | 11 | 0.10 | 1 | 0.01 | 21 | 0.17 | 11 | 0.10 | C1 FAIL x21, C1 REVIEW x1 |
| task | station3/2026-11-21/task03 | 87 | 61 | 0.41 | 4 | 0.02 | 22 | 0.15 | 61 | 0.41 | C1 FAIL x22, C2 REVIEW x4 |
| task | station3/2026-11-22/task01 | 65 | 28 | 0.26 | 0 | 0.00 | 37 | 0.32 | 28 | 0.26 | C1 FAIL x37 |
| task | station3/2026-11-22/task04 | 57 | 0 | 0.00 | 3 | 0.03 | 54 | 0.47 | 0 | 0.00 | C1 FAIL x54, C1 REVIEW x3 |
| task | station3/2026-11-24/task01 | 67 | 46 | 0.63 | 0 | 0.00 | 21 | 0.22 | 46 | 0.63 | C1 FAIL x21 |
| task | station3/2026-11-24/task02 | 27 | 22 | 0.48 | 0 | 0.00 | 5 | 0.10 | 22 | 0.48 | C1 FAIL x5 |
| task | station3/2026-11-24/task03 | 50 | 35 | 0.49 | 2 | 0.02 | 13 | 0.20 | 35 | 0.49 | C1 FAIL x13, C2 REVIEW x2 |
| task | station3/2026-11-24/task04 | 35 | 26 | 0.53 | 6 | 0.12 | 3 | 0.08 | 26 | 0.53 | C2 REVIEW x6, C1 FAIL x3 |
| task | station3/task03 | 26 | 9 | 0.19 | 1 | 0.02 | 16 | 0.21 | 9 | 0.19 | C1 FAIL x16, C1 REVIEW x1 |
| task | station3/task04 | 31 | 1 | 0.01 | 0 | 0.00 | 30 | 0.26 | 1 | 0.01 | C1 FAIL x30 |
| task | station4/2026-11-21/task00 | 33 | 0 | 0.00 | 33 | 0.12 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x33, C2 REVIEW x33 |
| task | station4/2026-11-21/task01 | 109 | 0 | 0.00 | 109 | 0.54 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x109, C2 REVIEW x109 |
| task | station4/2026-11-21/task02 | 16 | 0 | 0.00 | 0 | 0.00 | 16 | 0.07 | 0 | 0.00 | C1 FAIL x16 |
| task | station4/2026-11-21/task03 | 22 | 0 | 0.00 | 22 | 0.21 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x22, C2 REVIEW x22 |
| task | station4/2026-11-22/task01 | 63 | 0 | 0.00 | 63 | 0.54 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x63, C2 REVIEW x63 |
| task | station4/2026-11-22/task02 | 30 | 15 | 0.36 | 1 | 0.02 | 14 | 0.30 | 15 | 0.36 | C1 FAIL x14, C1 REVIEW x1 |
| task | station4/2026-11-22/task03 | 39 | 0 | 0.00 | 39 | 0.26 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x39, C2 REVIEW x39 |
| task | station4/2026-11-24/task01 | 17 | 2 | 0.02 | 1 | 0.01 | 14 | 0.08 | 2 | 0.02 | C1 FAIL x14, C1 REVIEW x1 |
| task | station4/2026-11-24/task02 | 44 | 5 | 0.06 | 2 | 0.02 | 37 | 0.27 | 5 | 0.06 | C1 FAIL x37, C1 REVIEW x2 |
| task | station4/2026-11-24/task03 | 38 | 0 | 0.00 | 38 | 0.64 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x38, C2 REVIEW x38 |
| task | station4/2026-11-24/task04 | 43 | 0 | 0.00 | 43 | 0.43 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x43, C2 REVIEW x43 |
| task | station5/2026-11-22/task01 | 7 | 3 | 0.08 | 1 | 0.03 | 3 | 0.04 | 3 | 0.08 | C1 FAIL x3, C1 REVIEW x1 |
| task | station5/2026-11-24/task01 | 29 | 18 | 0.27 | 2 | 0.03 | 9 | 0.12 | 18 | 0.27 | C1 FAIL x9, C2 REVIEW x2 |
| task | station5/2026-11-24/task02 | 22 | 17 | 0.25 | 3 | 0.04 | 2 | 0.03 | 17 | 0.25 | C2 REVIEW x3, C1 FAIL x2 |
| station | industrial_data_mp4 | 15 | 0 | 0.00 | 15 | 0.10 | 0 | 0.00 | 0 | 0.00 | C1 REVIEW x15, C2 REVIEW x15 |
| station | station1 | 1000 | 417 | 4.32 | 6 | 0.08 | 577 | 2.69 | 338 | 3.62 | C1 FAIL x577, C1 REVIEW x5, C2 REVIEW x1 |
| station | station2 | 320 | 136 | 1.57 | 146 | 3.68 | 38 | 0.42 | 83 | 0.94 | C2 REVIEW x146, C1 REVIEW x136, C1 FAIL x38 |
| station | station3 | 478 | 239 | 3.10 | 17 | 0.22 | 222 | 2.18 | 239 | 3.10 | C1 FAIL x222, C2 REVIEW x12, C1 REVIEW x5 |
| station | station4 | 454 | 22 | 0.45 | 351 | 2.78 | 81 | 0.72 | 22 | 0.45 | C1 REVIEW x351, C2 REVIEW x347, C1 FAIL x81 |
| station | station5 | 58 | 38 | 0.60 | 6 | 0.10 | 14 | 0.19 | 38 | 0.60 | C1 FAIL x14, C2 REVIEW x5, C1 REVIEW x1 |
| all | ALL | 2325 | 852 | 10.04 | 541 | 6.96 | 932 | 6.20 | 720 | 8.71 | C1 FAIL x932, C2 REVIEW x526, C1 REVIEW x513 |

## Why recordings fail the data checks

| Check | What | Status | Recordings |
|---|---|---|---|
| V9 | left / right views not swapped (--views) | FAIL | 341 |
| C3 | at least 9 s long | FAIL | 245 |
| D6 | not a duplicate | FAIL | 15 |
| V9 | left / right views not swapped (--views) | REVIEW | 1 |

## Repetition check findings

| Check | What | Status | Recordings |
|---|---|---|---|
| C1 | at least 3 cycles | FAIL | 932 |
| C2 | cycles at least 3 s | REVIEW | 526 |
| C1 | at least 3 cycles | REVIEW | 513 |

Every failed or review check, with the S3 file and the reason: `delivery_check_failures.csv`. Deliverable recordings: `delivery_check_deliverable.csv`. All checks per recording: `delivery_check.csv`.
