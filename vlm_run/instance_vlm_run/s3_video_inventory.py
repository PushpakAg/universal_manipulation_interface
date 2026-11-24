#!/usr/bin/env python3
"""Duration of every *_head.mp4 under an S3 prefix, without downloading the videos (read-only).

Each MP4's 'moov/mvhd' box holds the duration. Only that box is fetched with ranged GETs (a few KB to a few hundred KB
per file, wherever moov sits: start or end of the file).

Folder layouts found under umi_data/industrial_data_mp4/:
    <station>/<date>/<task>/<episode>/..._head.mp4
    <station>/<task>/<episode>/..._head.mp4        (no date folder: date = "")
    <episode>/..._head.mp4                         (no station, date or task: all = "")

    python s3_video_inventory.py                      # default prefix, writes reports/s3_head_video_*.csv
    python s3_video_inventory.py --prefix s3://bucket/some/prefix/
"""
import argparse
import csv
import re
import struct
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_s3_vlm as D  # noqa: E402

OUT = HERE / "reports"


def boxes(buf, start=0, end=None):
    """(type, payload_start, box_end) of the boxes in buf[start:end]."""
    end = len(buf) if end is None else end
    i = start
    while i + 8 <= end:
        size, typ = struct.unpack(">I4s", buf[i:i + 8])
        hdr = 8
        if size == 1:
            if i + 16 > end:
                return
            size = struct.unpack(">Q", buf[i + 8:i + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - i
        if size < hdr:
            return
        yield typ.decode("latin-1"), i + hdr, i + size
        i += size


def mvhd_duration(moov):
    for typ, p, e in boxes(moov):
        if typ == "mvhd":
            v = moov[p]
            if v == 1:
                timescale, duration = struct.unpack(">IQ", moov[p + 20:p + 32])
            else:
                timescale, duration = struct.unpack(">II", moov[p + 12:p + 20])
            return duration / timescale if timescale else None
    return None


def duration_s3(client, bucket, key, size):
    """Walk the top-level boxes with small ranged reads until moov, then read moov (or just its start: mvhd is first)."""
    get = lambda a, b: client.get_object(Bucket=bucket, Key=key, Range=f"bytes={a}-{b}")["Body"].read()
    off = 0
    while off < size:
        h = get(off, min(off + 15, size - 1))
        sz, typ = struct.unpack(">I4s", h[:8])
        if sz == 1:
            sz = struct.unpack(">Q", h[8:16])[0]
        elif sz == 0:
            sz = size - off
        if typ == b"moov":
            moov = get(off, min(off + min(sz, 65536) - 1, size - 1))
            return mvhd_duration(moov[8:])
        if sz < 8:
            return None
        off += sz
    return None


def parse_path(rel):
    parts = rel.split("/")
    station = next((p for p in parts[:-1] if re.fullmatch(r"station\d+", p)), "")
    date = next((p for p in parts[:-1] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p)), "")
    task = next((p for p in parts[:-1] if re.fullmatch(r"task\d+", p)), "")
    episode = next((p for p in parts[:-1] if re.fullmatch(r"episode_\d+", p)), "")
    return station, date, task, episode


def main():
    D.load_env(HERE / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default="s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/")
    ap.add_argument("--suffix", default="_head.mp4")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--top", default=r"station\d+", help="regex for the first folder under the prefix (default: station folders only)")
    a = ap.parse_args()
    bucket, prefix = D.split_s3(a.prefix)
    client = D.s3_client(None)
    objs = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        objs += [o for o in page.get("Contents", []) if o["Key"].endswith(a.suffix)
                 and re.fullmatch(a.top, o["Key"][len(prefix):].split("/")[0])]
    print(f"{len(objs)} {a.suffix} files under s3://{bucket}/{prefix}", flush=True)

    def one(o):
        try:
            return o, duration_s3(client, bucket, o["Key"], o["Size"]), ""
        except Exception as ex:
            return o, None, repr(ex)[:200]

    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(one, objs))
    rows = []
    for o, dur, err in res:
        station, date, task, episode = parse_path(o["Key"][len(prefix):])
        rows.append({"station": station, "date": date, "task": task, "episode": episode,
                     "duration_s": round(dur, 2) if dur else "", "minutes": round(dur / 60, 3) if dur else "",
                     "size_mb": round(o["Size"] / 1e6, 1), "s3_uri": f"s3://{bucket}/{o['Key']}", "error": err})
    rows.sort(key=lambda r: (r["station"] or "~", r["date"] or "~", r["task"] or "~", r["episode"]))
    OUT.mkdir(exist_ok=True)
    with open(OUT / "s3_head_video_by_episode.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    agg = defaultdict(lambda: [0, 0.0, 0])
    for r in rows:
        k = (r["station"] or "(none)", r["date"] or "(no date folder)", r["task"] or "(none)")
        agg[k][0] += 1
        agg[k][1] += r["duration_s"] or 0
        agg[k][2] += 0 if r["duration_s"] else 1
    with open(OUT / "s3_head_video_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["station", "date", "task", "episodes", "minutes", "hh:mm:ss", "avg_episode_s", "no_duration"])
        for (s, d, t), (n, sec, bad) in sorted(agg.items()):
            w.writerow([s, d, t, n, round(sec / 60, 1), f"{int(sec // 3600)}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}",
                        round(sec / max(1, n - bad), 1), bad])
    tot = sum(r["duration_s"] or 0 for r in rows)
    print(f"total {tot / 3600:.2f} h ({tot / 60:.1f} min) in {len(rows)} files; "
          f"{sum(1 for r in rows if not r['duration_s'])} without duration -> {OUT}")


if __name__ == "__main__":
    main()
