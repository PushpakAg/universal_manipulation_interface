# UMI delivery check: s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/

Checked against DataPRD1019 v1.1 (docs/UMI_delivery_checklist.md); header only, full decode.
Not checked in this run: dropped frames inside a file (V7, run with --deep).

**Deliverable: 9 of 15 recordings, 0.10 h of 0.16 h** (60.0%). Review: 6 (0.06 h). Fail: 0 (0.00 h).

| Level | Name | Recordings | Hours | Deliverable | Deliverable h | Review | Review h | Fail | Fail h | Fail checks |
|---|---|---|---|---|---|---|---|---|---|---|
| task | station2/2026-11-22/task01 | 3 | 0.03 | 2 | 0.02 | 1 | 0.01 | 0 | 0.00 |  |
| task | station2/2026-11-22/task02 | 3 | 0.02 | 3 | 0.02 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-22/task03 | 3 | 0.02 | 3 | 0.02 | 0 | 0.00 | 0 | 0.00 |  |
| task | station2/2026-11-22/task04 | 3 | 0.07 | 1 | 0.04 | 2 | 0.03 | 0 | 0.00 |  |
| task | station2/2026-11-22/task06 | 3 | 0.02 | 0 | 0.00 | 3 | 0.02 | 0 | 0.00 |  |
| station | station2 | 15 | 0.16 | 9 | 0.10 | 6 | 0.06 | 0 | 0.00 |  |
| all | ALL | 15 | 0.16 | 9 | 0.10 | 6 | 0.06 | 0 | 0.00 |  |

## Why recordings are not deliverable

| Check | What | Status | Recordings |
|---|---|---|---|
| C1 | at least 3 cycles | REVIEW | 6 |
| W2 | task is not setup | REVIEW | 2 |

Every failed or review check, with the S3 file and the reason: `delivery_decode_sample_failures.csv`. Deliverable recordings: `delivery_decode_sample_deliverable.csv`. All checks per recording: `delivery_decode_sample.csv`.
