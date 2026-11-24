#!/usr/bin/env python3
"""Hours of raw GoPro video per station, date and camera under the UMI collection upload (read-only on S3).

Counts only the raw layout <prefix>/<station>/<YYYY-MM-DD>/<head|left|right>/*.MP4. Processed copies under the same
station (industrial_data/..., raw_videos/, task folders) are listed separately as skipped, never counted. Durations
come from each MP4's moov/mvhd box via small ranged GETs (s3_video_inventory.duration_s3), so no video is downloaded.

Writes to --out (default reports/s3_collection_hours/):
    collection_files.csv      one row per MP4: station, date, camera, file, size, duration_s, error
    collection_hours.csv      station, date, camera: files, hours, GB, files without duration
    collection_summary.csv    station, date: head / left / right hours and files side by side, plus the gap
                              between the longest and the shortest camera (a missing or partial camera shows here)
    collection_skipped.csv    objects under the stations that are not in the raw layout (path, size)

    python scripts/s3_collection_hours.py
    python scripts/s3_collection_hours.py --stations station1 station4 --prefix s3://bucket/other/prefix/
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # vlm_scripts_reports/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_video_inventory import duration_s3  # noqa: E402

CAMS = ("head", "left", "right")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def hms(sec):
    sec = int(round(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def write(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default="s3://prod-mono-pipeline-v2-data/upload_ingestion/GoPro/UMI_Collection/")
    ap.add_argument("--stations", nargs="+", default=[f"station{i}" for i in range(1, 6)])
    ap.add_argument("--out", default=str(HERE / "reports" / "s3_collection_hours"))
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE") or "prod")
    ap.add_argument("--workers", type=int, default=32)
    a = ap.parse_args()

    import boto3
    from botocore.config import Config
    client = boto3.Session(profile_name=a.profile or None).client(
        "s3", config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, max_pool_connections=a.workers))
    bucket, _, prefix = a.prefix[5:].partition("/")
    prefix = prefix.rstrip("/") + "/"

    raw, skipped = [], []
    for st in a.stations:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{prefix}{st}/"):
            for o in page.get("Contents", []):
                p = o["Key"][len(prefix):].split("/")
                if len(p) == 4 and DATE_RE.match(p[1]) and p[2].lower() in CAMS and p[3].lower().endswith(".mp4"):
                    raw.append((p[0], p[1], p[2].lower(), p[3], o))
                elif not o["Key"].endswith("/"):
                    skipped.append((o["Key"][len(prefix):], o["Size"]))
    print(f"{len(raw)} raw MP4s in <station>/<date>/<camera>/, {len(skipped)} other objects skipped", flush=True)

    def one(item):
        o = item[4]
        try:
            return item, duration_s3(client, bucket, o["Key"], o["Size"]), ""
        except Exception as e:
            return item, None, repr(e)

    files = []
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (item, dur, err) in enumerate(ex.map(one, raw), 1):
            st, date, cam, name, o = item
            files.append([st, date, cam, name, o["Size"], round(dur, 3) if dur else "", err or ("" if dur else "no mvhd")])
            if i % 200 == 0:
                print(f"  {i}/{len(raw)}", flush=True)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files.sort()
    write(out / "collection_files.csv", ["station", "date", "camera", "file", "size_bytes", "duration_s", "error"], files)
    write(out / "collection_skipped.csv", ["path", "size_bytes"], sorted(skipped))

    agg = defaultdict(lambda: [0, 0.0, 0, 0])  # files, seconds, bytes, no duration
    for st, date, cam, _, size, dur, _ in files:
        for k in ((st, date, cam), (st, "ALL", cam)):
            g = agg[k]
            g[0] += 1
            g[1] += dur or 0
            g[2] += size
            g[3] += 0 if dur else 1
    rows = [[*k, g[0], round(g[1] / 3600, 3), hms(g[1]), round(g[2] / 1e9, 2), g[3]]
            for k, g in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1] == "ALL", kv[0][1], kv[0][2]))]
    write(out / "collection_hours.csv", ["station", "date", "camera", "files", "hours", "h:mm:ss", "GB", "no_duration"], rows)

    summ = []
    for st, date in sorted({(k[0], k[1]) for k in agg}, key=lambda x: (x[0], x[1] == "ALL", x[1])):
        hrs = [agg[(st, date, c)][1] / 3600 if (st, date, c) in agg else 0.0 for c in CAMS]
        n = [agg[(st, date, c)][0] if (st, date, c) in agg else 0 for c in CAMS]
        summ.append([st, date, *[round(h, 3) for h in hrs], *n, round(max(hrs) - min(hrs), 3)])
    write(out / "collection_summary.csv", ["station", "date", "head_hours", "left_hours", "right_hours",
                                           "head_files", "left_files", "right_files", "max_minus_min_hours"], summ)

    print(f"\n{'station':9} {'date':11} {'head h':>8} {'left h':>8} {'right h':>8} {'files h/l/r':>12} {'gap h':>6}")
    for r in summ:
        print(f"{r[0]:9} {r[1]:11} {r[2]:8.2f} {r[3]:8.2f} {r[4]:8.2f} {f'{r[5]}/{r[6]}/{r[7]}':>12} {r[8]:6.2f}")
    bad = sum(1 for f in files if f[6])
    print(f"\n{len(files)} files, {bad} without duration -> {out}")


if __name__ == "__main__":
    main()
