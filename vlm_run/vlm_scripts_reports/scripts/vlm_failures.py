#!/usr/bin/env python3
"""Failure log of all VLM runs, rebuilt from the run_*.log files (no API calls).

    python scripts/vlm_failures.py

Writes
    reports/vlm_failures.csv   one row per failed episode per run: run, stage, category, error, S3 MP4 folder,
                               and whether the episode has a result now (resolved by a later run)
    reports/vlm_runs.csv       one row per run: episodes planned, parsed, failed by category, cost
and prints a short summary. Rerun any time; it overwrites both files.
"""
import csv
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
RESULTS = HERE / "results"
REPORTS = HERE / "reports"

RE_HEAD = re.compile(r"^(s3://\S+): (\d+) task\(s\), (\d+) episode\(s\).*?(?:input (\w+), )?prompts (\S+)")
RE_TODO = re.compile(r"^(\d+) already done, (\d+) to run")
RE_FAIL = re.compile(r"^\s+\[(?:group \d+: )?\d+/\d+\] (\S+)/(episode_\w+): (upload|prepare) FAILED: (.*)$")
RE_PARSED = re.compile(r"^  (batches/\S+): (\d+)/(\d+) parsed, \$([\d.]+)")
RE_RETRY = re.compile(r"^retry: \d+ episode\(s\) \((.*)\) with thinking")
RE_BATCHERR = re.compile(r"^  (batches/\S+) (?:: error|ended in (\w+) without a responses file)(.*)")
RE_SUMMARY = re.compile(r"^summary: (\d+) episode\(s\), cost \$([\d.]+)")
RE_NOT_PARSED = re.compile(r"^(\d+) episode\(s\) without a parsed result")


def category(err):
    if "TokenRetrievalError" in err or "Token has expired" in err:
        return "aws_sso_token_expired"
    if "(404)" in err or "Not Found" in err:
        return "mp4_not_found_in_s3"
    if "file state FAILED" in err:
        return "gemini_rejected_video"
    if "MAX_TOKENS" in err or "unparse" in err.lower():
        return "gemini_output_unparsed"
    return "other"


def has_result(task, ep):
    d = RESULTS / task / ep
    return d.is_dir() and any(d.glob("*_vlm_result.json"))


def parse(log):
    run = {"run_log": log.name, "log_updated_utc": datetime.fromtimestamp(log.stat().st_mtime, timezone.utc)
           .strftime("%Y-%m-%d %H:%M"), "source": "", "input": "", "prompts": "", "episodes_in_bucket": 0,
           "already_done": 0, "planned": 0, "parsed": 0, "cost_usd": 0.0, "finished": False}
    fails = []
    for line in log.read_text(errors="replace").splitlines():
        if m := RE_HEAD.match(line):
            run.update(source=m[1], episodes_in_bucket=int(m[3]), input=m[4] or "frames", prompts=m[5])
        elif m := RE_TODO.match(line):
            run["already_done"], run["planned"] = int(m[1]), int(m[2])
        elif m := RE_FAIL.match(line):
            fails.append({"task": m[1], "episode": m[2], "stage": f"{m[3]} (S3 download / Files API)",
                          "error": m[4][:300]})
        elif m := RE_PARSED.match(line):
            run["parsed"] += int(m[2])
            run["cost_usd"] += float(m[4])
        elif m := RE_RETRY.match(line):
            for item in m[1].split(", "):
                te, _, reason = item.partition(" ")
                task, _, ep = te.rpartition("/")
                fails.append({"task": task, "episode": ep, "stage": "gemini response (retried)",
                              "error": reason or "unparsed"})
        elif m := RE_BATCHERR.match(line):
            fails.append({"task": "", "episode": "", "stage": f"batch {m[1]}", "error": (m[2] or "") + m[3][:300]})
        elif RE_SUMMARY.match(line):
            run["finished"] = True
    run["cost_usd"] = round(run["cost_usd"], 4)
    for f in fails:
        f["category"] = category(f["error"]) if f["episode"] else "batch_error"
    return run, fails


def main():
    logs = sorted(HERE.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
    runs, rows = [], []
    for log in logs:
        run, fails = parse(log)
        base = run["source"]
        cats = Counter(f["category"] for f in fails)
        run.update({f"failed_{k}": v for k, v in sorted(cats.items())}, failed_total=len(fails))
        runs.append(run)
        for f in fails:
            rows.append({"run_log": run["run_log"], "log_updated_utc": run["log_updated_utc"], "input": run["input"],
                         "task": f["task"], "episode": f["episode"], "stage": f["stage"], "category": f["category"],
                         "error": f["error"],
                         "s3_mp4_folder": f"{base}{f['task']}/{f['episode']}/" if f["episode"] else "",
                         "has_result_now": has_result(f["task"], f["episode"]) if f["episode"] else ""})
    REPORTS.mkdir(exist_ok=True)
    fcols = ["run_log", "log_updated_utc", "input", "task", "episode", "stage", "category", "error",
             "s3_mp4_folder", "has_result_now"]
    with open(REPORTS / "vlm_failures.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fcols)
        w.writeheader()
        w.writerows(rows)
    rcols = list(dict.fromkeys(k for r in runs for k in r))
    with open(REPORTS / "vlm_runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, rcols, restval=0)
        w.writeheader()
        w.writerows(runs)

    print(f"{'run':<26}{'input':<8}{'planned':>8}{'parsed':>8}{'failed':>8}{'cost $':>9}  failure categories")
    for r in runs:
        cats = ", ".join(f"{k[7:]} {v}" for k, v in r.items() if k.startswith("failed_") and k != "failed_total")
        print(f"{r['run_log']:<26}{r['input']:<8}{r['planned']:>8}{r['parsed']:>8}{r['failed_total']:>8}"
              f"{r['cost_usd']:>9.2f}  {cats}{'' if r['finished'] else '  (not finished)'}")
    ep = {(x["task"], x["episode"]): x for x in rows if x["episode"]}
    open_ = [x for x in ep.values() if not x["has_result_now"]]
    print(f"\n{len(ep)} distinct episode(s) ever failed; {len(ep) - len(open_)} have a result now, "
          f"{len(open_)} still without:")
    for (cat, task), n in sorted(Counter((x["category"], x["task"]) for x in open_).items()):
        print(f"  {cat:<24} {n:>4}  {task}")
    print(f"\n-> {REPORTS / 'vlm_failures.csv'}\n-> {REPORTS / 'vlm_runs.csv'}")


if __name__ == "__main__":
    main()
