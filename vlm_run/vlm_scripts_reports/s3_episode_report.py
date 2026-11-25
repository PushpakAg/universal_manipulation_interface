#!/usr/bin/env python3
"""Per-episode CSV report of video length and VLM task labels for an S3 folder.

For every episode_* folder under <s3_parent>/<subfolder>/ the script:
  * checks that head, left, right and mosaic mp4 files are present,
  * reads each mp4's real length with ffprobe over a presigned URL (header only),
  * checks for *_vlm_result.json and pulls task_text, task_family and action,
  * uses the mosaic mp4's length as the episode length.

Layouts handled (the station is the first folder under the parent):
    <parent>/<station>/<YYYY-MM-DD>/<task>/episode_*/...
    <parent>/<station>/<task>/episode_*/...          (date = "undated")

Usage:
    python s3_episode_report.py s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/ \
        station1 station2 --profile prod --out report

Outputs:
    <out>_episodes.csv  one row per episode
    <out>_summary.csv   hours (from mosaic length) per station, station/date,
                        station/date/task and VLM task_family
"""
import argparse, csv, json, re, subprocess, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import boto3

VIDEOS = ("head", "left", "right", "mosaic")
VID_RE = re.compile(r"_(head|left|right|mosaic)\.mp4$")
EP_RE = re.compile(r"^episode_\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DIFF_FIELDS = ("task_text", "task_family", "task_action", "object_categories")
VLM_COLS = (
    [f"canonical_{f}" for f in ("task_text", "task_family", "task_action", "object_categories", "confidence")]
    + [f"task_{f}" for f in ("task_text", "task_family", "task_action", "object_categories", "confidence")]
    + [f"{f}_differs" for f in DIFF_FIELDS]
    + ["any_difference", "differences", "n_repetitions", "vlm_model", "vlm_code_flags"]
)


def _norm(s):
    """Compare case- and whitespace-insensitively; ignore a trailing period."""
    return re.sub(r"\s+", " ", str(s)).strip().rstrip(".").lower()


def ffprobe_seconds(s3, bucket, key, retries=4):
    """Return (seconds, frames, error). Retries transient HTTP failures."""
    err = ""
    for attempt in range(retries):
        url = s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration:stream=nb_frames", "-of", "json", url],
            capture_output=True, text=True, timeout=180)
        try:
            j = json.loads(r.stdout)
            frames = (j.get("streams") or [{}])[0].get("nb_frames", "")
            return round(float(j["format"]["duration"]), 3), frames, ""
        except Exception:
            err = (r.stderr or "ffprobe parse error").strip().splitlines()[0][:200]
            time.sleep(1 + 2 * attempt)
    return None, "", err


def read_vlm(s3, bucket, key):
    try:
        j = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except Exception as e:
        return {"vlm_error": f"read/parse failed: {e}"[:200]}
    resp = j.get("response") or {}
    canon = resp.get("canonical_task") or {}
    ep = resp.get("task") or {}
    out = {}
    for prefix, src in (("canonical", canon), ("task", ep)):
        out[f"{prefix}_task_text"] = src.get("task_text", "")
        out[f"{prefix}_task_family"] = src.get("task_family", "")
        out[f"{prefix}_task_action"] = src.get("action", "")
        out[f"{prefix}_object_categories"] = "; ".join(map(str, src.get("object_categories") or []))
        out[f"{prefix}_confidence"] = src.get("confidence", "")
    diffs = []
    for field in DIFF_FIELDS:
        c, t = out[f"canonical_{field}"], out[f"task_{field}"]
        same = _norm(c) == _norm(t)
        out[f"{field}_differs"] = not same
        if not same:
            diffs.append(f"{field}: canonical='{c}' vs task='{t}'")
    out["any_difference"] = bool(diffs)
    out["differences"] = " | ".join(diffs)
    return {
        **out,
        "n_repetitions": resp.get("n_repetitions", ""),
        "vlm_model": j.get("model", ""),
        "vlm_code_flags": ";".join(map(str, j.get("code_flags") or [])),
        "vlm_error": "",
    }


def collect_episodes(s3, bucket, prefix):
    """Map episode folder prefix -> {'videos': {view: key}, 'vlm': key or None}."""
    eps = defaultdict(lambda: {"videos": {}, "vlm": None})
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            key = o["Key"]
            parts = key.split("/")
            if len(parts) < 2 or not EP_RE.match(parts[-2]):
                continue
            ep_prefix = "/".join(parts[:-1])
            m = VID_RE.search(parts[-1])
            if m:
                eps[ep_prefix]["videos"][m.group(1)] = key
            elif parts[-1].endswith("_vlm_result.json"):
                eps[ep_prefix]["vlm"] = key
    return eps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("s3_parent", help="s3://bucket/prefix/ (parent folder)")
    ap.add_argument("subfolders", nargs="+", help="sub-folder(s) under the parent to scan, e.g. station1 station2")
    ap.add_argument("--profile", default=None, help="AWS profile, e.g. prod")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--out", default="episode_report", help="output file prefix")
    a = ap.parse_args()

    u = urlparse(a.s3_parent)
    bucket, root = u.netloc, u.path.lstrip("/")
    if root and not root.endswith("/"):
        root += "/"
    s3 = boto3.Session(profile_name=a.profile).client("s3")

    eps = {}
    for sub in a.subfolders:
        eps.update(collect_episodes(s3, bucket, f"{root}{sub.strip('/')}/"))
    print(f"found {len(eps)} episode folders", file=sys.stderr)

    # probe every video in parallel
    jobs = [(ep, v, k) for ep, d in eps.items() for v, k in d["videos"].items()]
    with ThreadPoolExecutor(a.workers) as ex:
        probed = list(ex.map(lambda j: (j[0], j[1], ffprobe_seconds(s3, bucket, j[2])), jobs))
    lengths = defaultdict(dict)
    for ep, v, res in probed:
        lengths[ep][v] = res

    with ThreadPoolExecutor(a.workers) as ex:
        vlm = dict(zip(eps, ex.map(lambda ep: read_vlm(s3, bucket, eps[ep]["vlm"]) if eps[ep]["vlm"] else {}, eps)))
    print(f"probed {len(jobs)} videos, read {sum(1 for d in eps.values() if d['vlm'])} VLM results", file=sys.stderr)

    rows = []
    for ep in sorted(eps):
        rel = ep[len(root):].split("/")
        station = rel[0]
        if len(rel) >= 4 and DATE_RE.match(rel[1]):
            date, task = rel[1], "/".join(rel[2:-1])
        else:
            date, task = "undated", "/".join(rel[1:-1])
        d = eps[ep]
        row = {"station": station, "date": date, "task_folder": task, "episode": rel[-1]}
        errs = []
        for v in VIDEOS:
            row[f"has_{v}"] = v in d["videos"]
        row["all_4_videos"] = all(v in d["videos"] for v in VIDEOS)
        for v in VIDEOS:
            sec, frames, err = lengths[ep].get(v, (None, "", ""))
            row[f"{v}_seconds"] = sec if sec is not None else ""
            row[f"{v}_frames"] = frames
            if err:
                errs.append(f"{v}: {err}")
        mos = row["mosaic_seconds"]
        row["episode_seconds"] = mos
        row["episode_minutes"] = round(mos / 60, 4) if mos != "" else ""
        row["episode_hours"] = round(mos / 3600, 6) if mos != "" else ""
        row["has_vlm_result"] = d["vlm"] is not None
        v = vlm.get(ep, {})
        for k in VLM_COLS:  # blank when there is no VLM result
            row[k] = v.get(k, "")
        if v.get("vlm_error"):
            errs.append(v["vlm_error"])
        missing = [x for x in VIDEOS if x not in d["videos"]]
        if missing:
            errs.append("missing " + ",".join(missing))
        row["issues"] = " | ".join(errs)
        row["s3_episode_path"] = f"s3://{bucket}/{ep}/"
        rows.append(row)

    ep_csv = f"{a.out}_episodes.csv"
    with open(ep_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # summary: hours from mosaic length
    groups = {
        "station": lambda r: r["station"],
        "station/date": lambda r: f"{r['station']}/{r['date']}",
        "station/date/task": lambda r: f"{r['station']}/{r['date']}/{r['task_folder']}",
        "canonical_task_family": lambda r: r["canonical_task_family"] or "(no vlm result)",
        "all": lambda r: "all",
    }
    out = []
    for level, keyf in groups.items():
        agg = defaultdict(lambda: {"episodes": 0, "complete": 0, "with_vlm": 0, "sec": 0.0, "texts": set()})
        for r in rows:
            g = agg[keyf(r)]
            g["episodes"] += 1
            g["complete"] += r["all_4_videos"]
            g["with_vlm"] += r["has_vlm_result"]
            g["sec"] += r["episode_seconds"] or 0
            g["diff"] = g.get("diff", 0) + (r["any_difference"] is True)
            if r["canonical_task_text"]:
                g["texts"].add(r["canonical_task_text"])
        for k in sorted(agg):
            g = agg[k]
            out.append({"level": level, "group": k, "episodes": g["episodes"],
                        "episodes_all_4_videos": g["complete"], "episodes_with_vlm": g["with_vlm"],
                        "episodes_task_differs_from_canonical": g.get("diff", 0),
                        "hours": round(g["sec"] / 3600, 4), "minutes": round(g["sec"] / 60, 2),
                        "canonical_task_text": " || ".join(sorted(g["texts"])) if level == "station/date/task" else ""})
    sum_csv = f"{a.out}_summary.csv"
    with open(sum_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)

    for r in out:
        if r["level"] in ("station", "station/date/task", "all"):
            print(f"{r['level']:18} {r['group']:32} eps={r['episodes']:4} complete={r['episodes_all_4_videos']:4} "
                  f"vlm={r['episodes_with_vlm']:4} hours={r['hours']:.4f}")
    issues = sum(1 for r in rows if r["issues"])
    print(f"\nwrote {ep_csv} ({len(rows)} episodes, {issues} with issues) and {sum_csv}")


if __name__ == "__main__":
    main()
