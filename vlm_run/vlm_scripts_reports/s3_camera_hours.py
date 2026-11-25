#!/usr/bin/env python3
"""Exact video hours per camera (head/left/right) under an S3 folder.

Reads each mp4's real duration with ffprobe over a presigned URL (only the
container header is fetched, not the whole file). Folder layout expected:

    <root>/<station>/<YYYY-MM-DD>/<task>/episode_*/..._{head,left,right}.mp4
    <root>/<station>/<task>/episode_*/...            (reported as date "undated")

Usage:
    python s3_camera_hours.py s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/ \
        --folders station1 station2 --profile prod --out hours

Writes <out>_files.csv (one row per mp4) and <out>_summary.md, and prints the summary.
"""
import argparse, csv, json, re, subprocess, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import boto3

CAMS = ("head", "left", "right")
CAM_RE = re.compile(r"_(head|left|right)\.mp4$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def list_mp4s(s3, bucket, prefix):
    out = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            m = CAM_RE.search(o["Key"])
            if m:
                out.append((o["Key"], m.group(1)))
    return out


def probe(s3, bucket, key, retries=4):
    err = ""
    for attempt in range(retries):
        url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration:stream=nb_frames,avg_frame_rate", "-of", "json", url],
            capture_output=True, text=True, timeout=180)
        try:
            j = json.loads(r.stdout)
            st = (j.get("streams") or [{}])[0]
            return float(j["format"]["duration"]), st.get("nb_frames", ""), st.get("avg_frame_rate", ""), ""
        except Exception:
            err = (r.stderr or "ffprobe parse error").strip().splitlines()[0][:200]
            time.sleep(1 + 2 * attempt)
    return None, "", "", err


def h(sec):
    return f"{sec / 3600:.4f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("s3_root", help="s3://bucket/prefix/ to scan")
    ap.add_argument("--folders", nargs="*", default=None,
                    help="sub-folders under the root to include (e.g. station1 station2); default: everything")
    ap.add_argument("--profile", default=None, help="AWS profile (e.g. prod)")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--out", default="camera_hours", help="output file prefix")
    a = ap.parse_args()

    u = urlparse(a.s3_root)
    bucket, root = u.netloc, u.path.lstrip("/")
    if root and not root.endswith("/"):
        root += "/"
    s3 = boto3.Session(profile_name=a.profile).client("s3")

    prefixes = [f"{root}{f.strip('/')}/" for f in a.folders] if a.folders else [root]
    items = [it for p in prefixes for it in list_mp4s(s3, bucket, p)]
    print(f"found {len(items)} head/left/right mp4s; probing...", file=sys.stderr)

    def work(it):
        key, cam = it
        dur, nb, fps, err = probe(s3, bucket, key)
        rel = key[len(root):].split("/")
        group = rel[0]
        if len(rel) > 2 and DATE_RE.match(rel[1]):
            date, task = rel[1], rel[2]
        else:
            date, task = "undated", rel[1] if len(rel) > 2 else ""
        return dict(folder=group, date=date, task=task, camera=cam, key=key,
                    duration_s=dur if dur is not None else "", nb_frames=nb, fps=fps, error=err)

    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(work, items))
    rows.sort(key=lambda r: r["key"])

    with open(f"{a.out}_files.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["key"])
        w.writeheader(); w.writerows(rows)

    # aggregate seconds: (folder, date, task) -> cam -> sec
    agg = defaultdict(lambda: defaultdict(float))
    eps = defaultdict(set)
    for r in rows:
        if r["duration_s"] == "":
            continue
        k = (r["folder"], r["date"], r["task"])
        agg[k][r["camera"]] += r["duration_s"]
        eps[k].add(r["key"].rsplit("/", 2)[-2])

    L = ["# Camera hours", "", f"Source: `{a.s3_root}`  folders: {a.folders or 'all'}", ""]
    hdr = "| {} | episodes | head h | left h | right h | total h |"
    sep = "|---|---:|---:|---:|---:|---:|"

    def line(label, n, d):
        t = sum(d[c] for c in CAMS)
        return f"| {label} | {n} | " + " | ".join(h(d[c]) for c in CAMS) + f" | {h(t)} |"

    def addup(keys):
        d = defaultdict(float); n = 0
        for k in keys:
            for c in CAMS:
                d[c] += agg[k][c]
            n += len(eps[k])
        return n, d

    L += ["## Per folder / date / task", "", hdr.format("folder / date / task"), sep]
    for k in sorted(agg):
        L.append(line(" / ".join(k), len(eps[k]), agg[k]))

    L += ["", "## Per folder / date", "", hdr.format("folder / date"), sep]
    for fd in sorted({k[:2] for k in agg}):
        L.append(line(" / ".join(fd), *addup([k for k in agg if k[:2] == fd])))

    L += ["", "## Per date (all folders)", "", hdr.format("date"), sep]
    for d in sorted({k[1] for k in agg}):
        L.append(line(d, *addup([k for k in agg if k[1] == d])))

    L += ["", "## Per folder", "", hdr.format("folder"), sep]
    for fo in sorted({k[0] for k in agg}):
        L.append(line(fo, *addup([k for k in agg if k[0] == fo])))

    L += ["", "## Grand total", "", hdr.format("all"), sep, line("all", *addup(list(agg)))]

    bad = [r for r in rows if r["error"]]
    L += ["", f"Files probed: {len(rows)}; failed: {len(bad)}"]
    L += [f"- FAILED `{r['key']}`: {r['error']}" for r in bad]

    md = "\n".join(L) + "\n"
    with open(f"{a.out}_summary.md", "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
