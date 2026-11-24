#!/usr/bin/env python3
"""Collect every VLM result JSON (run_s3_vlm.py uploads) from S3 into CSVs, one column per field. Read-only on S3.

1. List s3://<source>/<station>/... recursively for each station (default station1 station2 station3) and keep
   the objects ending in --suffix (default _vlm_result.json). Both layouts are read:
   <station>/<date>/<taskNN>/<episode>/<name>_vlm_result.json and <station>/<taskNN>/<episode>/<name>_vlm_result.json.
2. Download each JSON (parallel) to <out>/json/<same key below the source>, skipped when a local copy with the
   same size already exists (--refresh downloads again).
3. Write
     <out>/vlm_results_episodes.csv     one row per JSON: station, date, task, episode, s3 uri, last modified,
                                        then every field of the JSON flattened to a dotted column
                                        (response.canonical_task.task_text, usage.cost_usd, ...). Lists of plain
                                        values are joined with " | "; lists of objects (response.repetitions) are
                                        kept as JSON text in the episode row and also expanded below.
     <out>/vlm_results_repetitions.csv  (only when present) one row per entry of response.repetitions (station, date, task, episode,
                                        then every field of the repetition flattened the same way).
   Columns are the union over all files, so results of different prompt versions sit in one table (empty cells
   where a version has no such field).

Credentials: the usual boto3 chain; --profile (default: $AWS_PROFILE, else prod). On a laptop: aws sso login --profile prod

    python scripts/collect_s3_vlm_results.py                                  # station1-3 -> reports/s3_vlm_results/
    python scripts/collect_s3_vlm_results.py --stations station2 --out /tmp/x
    python scripts/collect_s3_vlm_results.py --list                           # count the JSONs only, no download
"""
import argparse
import concurrent.futures as cf
import csv
import json
import os
import re
import sys
from pathlib import Path

import boto3
from botocore.config import Config

HERE = Path(__file__).resolve().parents[1]  # vlm_scripts_reports/
DEFAULT_SOURCE = "s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/"
ID_COLS = ["station", "date", "task", "episode", "file", "s3_uri", "last_modified", "size_bytes"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def split_uri(uri):
    if not uri.startswith("s3://"):
        sys.exit(f"not an s3:// uri: {uri}")
    bucket, _, prefix = uri[5:].partition("/")
    return bucket, (prefix.rstrip("/") + "/") if prefix else ""


def list_results(client, bucket, prefix, stations, suffix):
    """[{key, size, last_modified}] of every object ending in suffix below prefix/<station>/."""
    found = []
    pg = client.get_paginator("list_objects_v2")
    for st in stations:
        n = 0
        for page in pg.paginate(Bucket=bucket, Prefix=f"{prefix}{st.strip('/')}/"):
            for o in page.get("Contents", []):
                if o["Key"].endswith(suffix):
                    found.append({"key": o["Key"], "size": o["Size"], "last_modified": o["LastModified"].isoformat()})
                    n += 1
        print(f"  {st}: {n} result file(s)")
    return found


def path_ids(rel):
    """station/[date/]task/episode/file -> ids. Deeper or shallower paths keep what can be read."""
    parts = rel.split("/")
    ids = {"station": parts[0] if len(parts) > 1 else "", "date": "", "task": "", "episode": "", "file": parts[-1]}
    mid = parts[1:-1]
    if mid and DATE_RE.match(mid[0]):
        ids["date"] = mid.pop(0)
    if len(mid) >= 2:
        ids["task"], ids["episode"] = "/".join(mid[:-1]), mid[-1]
    elif mid:
        ids["task"] = mid[0]
    return ids


def flatten(obj, prefix="", out=None, expand_lists=True):
    """Dotted columns. Plain-value lists -> ' | ' joined; lists with objects -> JSON text."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        if not obj and prefix:
            out[prefix] = ""
        for k, v in obj.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out, expand_lists)
    elif isinstance(obj, list):
        if all(not isinstance(x, (dict, list)) for x in obj):
            out[prefix] = " | ".join("" if x is None else str(x) for x in obj)
        else:
            out[prefix] = json.dumps(obj, ensure_ascii=False)
        out[prefix + ".count"] = len(obj)
    else:
        out[prefix] = obj
    return out


def download(client, bucket, item, dest, refresh):
    if not refresh and dest.exists() and dest.stat().st_size == item["size"]:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    client.download_file(bucket, item["key"], str(tmp))
    os.replace(tmp, dest)
    return "downloaded"


def write_csv(path, rows, first_cols):
    cols = list(first_cols)
    seen = set(cols)
    for r in rows:  # union of columns, in first-seen order
        for k in r:
            if k not in seen:
                seen.add(k)
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(cols)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=DEFAULT_SOURCE, help="S3 prefix holding the station folders")
    ap.add_argument("--stations", nargs="+", default=["station1", "station2", "station3"])
    ap.add_argument("--suffix", default="_vlm_result.json", help="file name ending of the result JSONs")
    ap.add_argument("--out", default=str(HERE / "reports" / "s3_vlm_results"), help="output folder (json/ + CSVs)")
    ap.add_argument("--profile", default=os.environ.get("AWS_PROFILE") or "prod")
    ap.add_argument("--region", default=None)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--refresh", action="store_true", help="download again even when a local copy exists")
    ap.add_argument("--list", action="store_true", help="only list and count the result JSONs")
    a = ap.parse_args()

    session = boto3.Session(profile_name=a.profile or None, region_name=a.region)
    client = session.client("s3", config=Config(retries={"max_attempts": 8, "mode": "adaptive"},
                                                max_pool_connections=max(10, a.workers)))
    bucket, prefix = split_uri(a.source)
    print(f"listing s3://{bucket}/{prefix} {a.stations} *{a.suffix}")
    items = list_results(client, bucket, prefix, a.stations, a.suffix)
    print(f"{len(items)} result file(s)")
    if a.list or not items:
        return

    out = Path(a.out)
    jdir = out / "json"
    jobs = {}
    stats = {"downloaded": 0, "cached": 0, "failed": 0}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for it in items:
            dest = jdir / it["key"][len(prefix):]
            jobs[ex.submit(download, client, bucket, it, dest, a.refresh)] = (it, dest)
        for i, fut in enumerate(cf.as_completed(jobs), 1):
            it, _ = jobs[fut]
            try:
                stats[fut.result()] += 1
            except Exception as e:
                stats["failed"] += 1
                print(f"  download FAILED s3://{bucket}/{it['key']}: {e}")
            if i % 200 == 0:
                print(f"  {i}/{len(items)}")
    print(f"downloads: {stats}")

    ep_rows, rep_rows, bad = [], [], 0
    for it, dest in sorted(jobs.values(), key=lambda x: x[0]["key"]):
        if not dest.exists():
            continue
        rel = it["key"][len(prefix):]
        ids = path_ids(rel)
        ids.update({"s3_uri": f"s3://{bucket}/{it['key']}", "last_modified": it["last_modified"], "size_bytes": it["size"]})
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
        except Exception as e:
            bad += 1
            ep_rows.append({**ids, "read_error": repr(e)})
            continue
        ep_rows.append({**ids, **flatten(data)})
        reps = ((data.get("response") or {}) if isinstance(data, dict) else {}).get("repetitions") or []
        for r in reps if isinstance(reps, list) else []:
            rep_rows.append({**{k: ids[k] for k in ("station", "date", "task", "episode", "s3_uri")},
                             **flatten(r if isinstance(r, dict) else {"value": r})})

    out.mkdir(parents=True, exist_ok=True)
    f1, f2 = out / "vlm_results_episodes.csv", out / "vlm_results_repetitions.csv"
    n1 = write_csv(f1, ep_rows, ID_COLS)
    print(f"{len(ep_rows)} episode row(s), {n1} columns -> {f1}" + (f" ({bad} unreadable)" if bad else ""))
    if rep_rows:
        n2 = write_csv(f2, rep_rows, ["station", "date", "task", "episode", "s3_uri"])
        print(f"{len(rep_rows)} repetition row(s), {n2} columns -> {f2}")
    else:
        print("no response.repetitions in these results (count-only prompts): no repetitions CSV")


if __name__ == "__main__":
    main()
