#!/usr/bin/env python3
"""Sanity check: is a <name>_vlm_result.json present and sound for EVERY episode, locally and in S3?

For each <task>/<episode>/<name>_head.mp4 under the config's source prefix (read-only S3 listing):
  local   results_dir/<task>/<episode>/<name>_vlm_result.json exists, is valid JSON
  s3      <task>/<episode>/<name>_vlm_result.json exists next to the MP4
  same    local and S3 copies are byte-identical (MD5 vs S3 ETag)
  parsed  "response" is not null (the model answer was parsed)
  video   the "video" field is this episode's S3 MP4 (no mixed-up episodes)
  count   response.n_repetitions is an int and equals len(response.repetitions)
  steps   n_steps matches step_table.json; every repetition range lies inside 1..n_steps
  flags   number of code flags (reported, not a failure)

    python check_results.py                 # all episodes; table of problems + totals
    python check_results.py --task task01   # one task
    python check_results.py --csv out.csv   # one row per episode
    python check_results.py --local-only    # skip the S3 side
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_s3_vlm as D  # noqa: E402  (same listing, names and paths as the run)


def check_episode(a, client, bucket, e):
    d = D.episode_dir(a, e)
    name = D.result_name(a, e["key"])
    f = d / name
    s3_key = e["key"].rsplit("/", 1)[0] + "/" + name
    row = {"task": e["task"], "episode": e["episode"], "local": False, "s3": None, "same": None, "parsed": False,
           "video": False, "count": False, "steps": False, "n_repetitions": None, "n_flags": None, "problems": []}
    r = None
    if f.exists():
        try:
            r = json.loads(f.read_text())
            row["local"] = True
        except Exception as ex:
            row["problems"].append(f"local file is not valid JSON: {ex}")
    else:
        legacy = d / "vlm_result.json"
        row["problems"].append("local result missing" + (" (only legacy vlm_result.json: run --summary-only to rename)"
                                                         if legacy.exists() else ""))
    if client is not None:
        try:
            head = client.head_object(Bucket=bucket, Key=s3_key)
            row["s3"] = True
            if row["local"]:
                row["same"] = hashlib.md5(f.read_bytes()).hexdigest() == head["ETag"].strip('"')
                if not row["same"]:
                    row["problems"].append("local and S3 copies differ")
        except client.exceptions.ClientError as ex:
            if ex.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                row["s3"] = False
                row["problems"].append("S3 result missing")
            else:
                raise
    if r is None:
        return row
    resp = r.get("response")
    row["parsed"] = resp is not None
    if not row["parsed"]:
        row["problems"].append(f"no parsed response ({r.get('error') or r.get('finish_reason') or 'unparseable'})")
    row["video"] = r.get("video") == e["s3_uri"]
    if not row["video"]:
        row["problems"].append(f"video field is {r.get('video')!r}, not this episode")
    row["n_flags"] = len(r.get("code_flags") or [])
    if resp is not None:
        reps = resp.get("repetitions") or []
        n = resp.get("n_repetitions")
        row["n_repetitions"] = n
        row["count"] = isinstance(n, int) and n == len(reps)
        if not row["count"]:
            row["problems"].append(f"n_repetitions {n!r} vs {len(reps)} repetitions listed")
        st = d / "step_table.json"
        n_steps = len(json.loads(st.read_text())) if st.exists() else None
        ok_range = all(isinstance(x.get("start_step"), int) and isinstance(x.get("end_step"), int)
                       and 1 <= x["start_step"] <= x["end_step"] <= (r.get("n_steps") or 0) for x in reps)
        row["steps"] = n_steps == r.get("n_steps") and ok_range
        if n_steps != r.get("n_steps"):
            row["problems"].append(f"n_steps {r.get('n_steps')} vs step_table {n_steps}")
        if not ok_range:
            row["problems"].append("a repetition range is outside 1..n_steps")
    return row


def main():
    D.load_env(HERE / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "s3_run.json")
    ap.add_argument("--task", action="append")
    ap.add_argument("--local-only", action="store_true")
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    a.results = D.here_path(cfg["results_dir"])
    a.head_suffix = cfg.get("head_suffix", "_head.mp4")
    a.s3_result_suffix = cfg.get("s3_result_suffix", "_vlm_result.json")
    bucket, prefix = D.split_s3(cfg["source"])
    s3 = D.s3_client(cfg.get("region"))
    eps = D.list_episodes(s3, bucket, prefix, a.head_suffix)
    if a.task:
        eps = [e for e in eps if e["task"] in a.task]
    client = None if a.local_only else s3
    rows = [check_episode(a, client, bucket, e) for e in eps]

    keys = ["local", "s3", "same", "parsed", "video", "count", "steps"]
    print(f"{len(rows)} episode(s) in S3 under {prefix}")
    print(f"{'task':8} {'episodes':>8} " + " ".join(f"{k:>7}" for k in keys) + f" {'flagged':>8}")
    for t in sorted({r["task"] for r in rows}) + ["ALL"]:
        sub = [r for r in rows if t in ("ALL", r["task"])]
        cells = []
        for k in keys:
            vals = [r[k] for r in sub if r[k] is not None]
            cells.append(f"{sum(bool(v) for v in vals)}/{len(sub)}" if vals or k != "same" else "-")
        print(f"{t:8} {len(sub):>8} " + " ".join(f"{c:>7}" for c in cells)
              + f" {sum(1 for r in sub if r['n_flags']):>8}")
    bad = [r for r in rows if r["problems"]]
    missing = [r for r in bad if r["problems"] and r["problems"][0].startswith("local result missing")]
    other = [r for r in bad if r not in missing]
    if missing:
        by = {}
        for r in missing:
            by.setdefault(r["task"], []).append(r["episode"].replace("episode_", ""))
        print(f"\nno result yet: {len(missing)} episode(s): " + "; ".join(f"{t} {','.join(v)}" for t, v in sorted(by.items())))
    for r in other:
        print(f"  PROBLEM {r['task']}/{r['episode']}: " + " | ".join(r["problems"]))
    if not bad:
        print("\nall episodes have a sound result locally" + ("" if a.local_only else " and in S3 (identical copies)"))
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["task"])
            w.writeheader()
            for r in rows:
                w.writerow(dict(r, problems=" | ".join(r["problems"])))
        print(f"csv -> {a.csv}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
