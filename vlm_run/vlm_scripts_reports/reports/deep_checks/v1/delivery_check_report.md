# UMI delivery check: s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/

Checked against DataPRD1019 v1.1 (docs/UMI_delivery_checklist.md); header + every frame timestamp.
Not checked in this run: corrupt frames (V8, run with --decode). Deliverable means: passes every check that ran.

**Deliverable: 64 of 1186 recordings, 0.50 h of 7.61 h** (5.4%). Review: 944 (6.79 h). Fail: 178 (0.32 h).

| Level | Name | Recordings | Hours | Deliverable | Deliverable h | Review | Review h | Fail | Fail h | Fail checks |
|---|---|---|---|---|---|---|---|---|---|---|
| task | industrial_data_mp4 | 15 | 0.10 | 0 | 0.00 | 14 | 0.10 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-21/task01 | 91 | 0.70 | 0 | 0.00 | 90 | 0.70 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-21/task02 | 142 | 0.54 | 0 | 0.00 | 105 | 0.47 | 37 | 0.07 | C3 at least 9 s long x37 |
| task | station1/2026-11-21/task03 | 158 | 0.38 | 0 | 0.00 | 36 | 0.16 | 122 | 0.21 | C3 at least 9 s long x122 |
| task | station1/2026-11-21/task04 | 28 | 0.25 | 0 | 0.00 | 27 | 0.25 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-21/task05 | 16 | 0.12 | 0 | 0.00 | 16 | 0.12 | 0 | 0.00 |  |
| task | station1/2026-11-22/task01 | 31 | 0.23 | 0 | 0.00 | 31 | 0.23 | 0 | 0.00 |  |
| task | station1/2026-11-22/task02 | 41 | 0.24 | 0 | 0.00 | 40 | 0.24 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/2026-11-22/task03 | 10 | 0.06 | 0 | 0.00 | 10 | 0.06 | 0 | 0.00 |  |
| task | station1/2026-11-22/task04 | 56 | 0.58 | 0 | 0.00 | 56 | 0.58 | 0 | 0.00 |  |
| task | station1/2026-11-22/task05 | 49 | 0.28 | 0 | 0.00 | 47 | 0.27 | 2 | 0.01 | C3 at least 9 s long x2 |
| task | station1/2026-11-22/task07 | 32 | 0.14 | 0 | 0.00 | 31 | 0.14 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/task03 | 46 | 0.31 | 0 | 0.00 | 44 | 0.30 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station1/task04 | 49 | 0.28 | 0 | 0.00 | 48 | 0.28 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station1/task05 | 50 | 0.33 | 0 | 0.00 | 48 | 0.32 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station2/2026-11-22/task01 | 15 | 0.10 | 13 | 0.09 | 1 | 0.01 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station2/2026-11-22/task02 | 26 | 0.18 | 26 | 0.18 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-22/task03 | 21 | 0.15 | 21 | 0.15 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-22/task04 | 9 | 0.18 | 3 | 0.08 | 6 | 0.10 | 0 | 0.00 |  |
| task | station2/2026-11-22/task06 | 41 | 0.32 | 1 | 0.01 | 37 | 0.30 | 3 | 0.00 | C3 at least 9 s long x3 |
| task | station3/2026-11-22/task01 | 44 | 0.36 | 0 | 0.00 | 44 | 0.36 | 0 | 0.00 |  |
| task | station3/2026-11-22/task02 | 33 | 0.28 | 0 | 0.00 | 33 | 0.28 | 0 | 0.00 |  |
| task | station3/2026-11-22/task03 | 87 | 0.59 | 0 | 0.00 | 86 | 0.59 | 1 | 0.00 | C3 at least 9 s long x1 |
| task | station3/2026-11-22/task04 | 39 | 0.22 | 0 | 0.00 | 37 | 0.22 | 2 | 0.00 | C3 at least 9 s long x2 |
| task | station3/task03 | 26 | 0.42 | 0 | 0.00 | 26 | 0.42 | 0 | 0.00 |  |
| task | station3/task04 | 31 | 0.27 | 0 | 0.00 | 31 | 0.27 | 0 | 0.00 |  |
| station | industrial_data_mp4 | 15 | 0.10 | 0 | 0.00 | 14 | 0.10 | 1 | 0.00 | C3 at least 9 s long x1 |
| station | station1 | 799 | 4.44 | 0 | 0.00 | 629 | 4.13 | 170 | 0.31 | C3 at least 9 s long x170 |
| station | station2 | 112 | 0.92 | 64 | 0.50 | 44 | 0.42 | 4 | 0.01 | C3 at least 9 s long x4 |
| station | station3 | 260 | 2.14 | 0 | 0.00 | 257 | 2.14 | 3 | 0.00 | C3 at least 9 s long x3 |
| all | ALL | 1186 | 7.61 | 64 | 0.50 | 944 | 6.79 | 178 | 0.32 | C3 at least 9 s long x178 |

## Why recordings are not deliverable

| Check | What | Status | Recordings |
|---|---|---|---|
| C1 | at least 3 cycles | REVIEW | 1122 |
| C2 | cycles at least 3 s | REVIEW | 1074 |
| C3 | at least 9 s long | FAIL | 178 |
| W2 | task is not setup | REVIEW | 8 |

Every failed or review check, with the S3 file and the reason: `delivery_check_failures.csv`. Deliverable recordings: `delivery_check_deliverable.csv`. All checks per recording: `delivery_check.csv`.
