#!/usr/bin/env python3
"""Progress of a run_s3_vlm.py video run, read from its log (no API calls).

    python scripts/vlm_progress.py                    # newest run_*.log in the project root, bars per group
    python scripts/vlm_progress.py run_video_full.log
    python scripts/vlm_progress.py --line             # one line (for a status bar / Claude Code statusLine)
    watch -n 10 python scripts/vlm_progress.py        # live

Counts per group: MP4s uploaded to the Files API (or failed), episodes parsed by Gemini, cost; then the phase
(uploading, waiting for Gemini, consolidating, S3 upload, done).
"""
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]

RE_HEAD = re.compile(r"^s3://\S+: (\d+) task\(s\), (\d+) episode\(s\)")
RE_TODO = re.compile(r"^(\d+) already done, (\d+) to run")
RE_GROUP = re.compile(r"^\[group (\d+)/(\d+)\] (\d+) episodes, ([\d.]+) GB: (.*)")
RE_EP = re.compile(r"^  \[group (\d+): (\d+)/(\d+)\] (\S+): (.*)")
RE_JOB = re.compile(r"^\[job \d+/\d+_g(\d+)\] submitted (batches/\S+)")
RE_PARSED = re.compile(r"^  (batches/\S+): (\d+)/(\d+) parsed, \$([\d.]+)")
RE_STATE = re.compile(r"^  (batches/\S+): (BATCH_STATE_\w+) after (\d+) s")
RE_UPLOADED = re.compile(r"^uploaded (\d+)/(\d+) result")
RE_SUMMARY = re.compile(r"^summary: (\d+) episode\(s\), cost \$([\d.]+)")


def parse(log):
    s = {"total": 0, "todo": 0, "done_before": 0, "groups": {}, "jobs": {}, "phase": "starting", "cost": 0.0,
         "s3_up": 0, "s3_result_lines": 0, "summary": None, "last_state": None}
    for line in log.read_text(errors="replace").splitlines():
        if m := RE_HEAD.match(line):
            s["total"] = int(m[2])
        elif m := RE_TODO.match(line):
            s["done_before"], s["todo"] = int(m[1]), int(m[2])
        elif m := RE_GROUP.match(line):
            s["groups"][int(m[1])] = {"n": int(m[3]), "gb": float(m[4]), "tasks": m[5], "up": 0, "fail": 0,
                                      "parsed": 0, "sent": 0, "cost": 0.0, "batch": None, "state": None}
            s["n_groups"] = int(m[2])
        elif m := RE_EP.match(line):
            g = s["groups"].get(int(m[1]))
            if g:
                g["fail" if "FAILED" in m[5] else "up"] += 1
            s["phase"] = f"uploading group {m[1]}"
        elif m := RE_JOB.match(line):
            g = s["groups"].get(int(m[1]))
            if g:
                g["batch"] = m[2]
                s["jobs"][m[2]] = int(m[1])
            s["phase"] = "waiting for Gemini"
        elif m := RE_STATE.match(line):
            gi = s["jobs"].get(m[1])
            if gi:
                s["groups"][gi]["state"] = m[2].replace("BATCH_STATE_", "").lower()
            s["last_state"] = (m[1], m[2], int(m[3]))
        elif m := RE_PARSED.match(line):
            gi = s["jobs"].get(m[1])
            if gi:  # a retry job is not in jobs: its episodes are already counted in sent
                g = s["groups"][gi]
                g["parsed"] += int(m[2])
                g["sent"] += int(m[3])
                g["cost"] += float(m[4])
                g["state"] = "collected"
            s["cost"] += float(m[4])
        elif line.startswith("consolidating canonical_task"):
            s["phase"] = "consolidating canonical_task"
        elif line.startswith("  -> s3://"):
            s["s3_result_lines"] += 1
            s["phase"] = "uploading results to S3"
        elif m := RE_UPLOADED.match(line):
            s["s3_up"] = int(m[1])
        elif m := RE_SUMMARY.match(line):
            s["summary"] = (int(m[1]), float(m[2]))
    return s


def running():
    try:
        out = subprocess.run(["pgrep", "-f", "scripts/run_s3_vlm.py"], capture_output=True, text=True).stdout
        return bool(out.strip())
    except Exception:
        return False


def bar(done, total, width=30, fail=0):
    if total <= 0:
        return "-" * width
    d = round(width * done / total)
    f = min(width - d, round(width * fail / total))
    return "█" * d + "x" * f + "░" * (width - d - f)


def pct(a, b):
    return f"{100 * a / b:5.1f}%" if b else "  -  "


def render(s, log, alive):
    groups = s["groups"]
    n = s["todo"] or sum(g["n"] for g in groups.values())
    up = sum(g["up"] for g in groups.values())
    fail = sum(g["fail"] for g in groups.values())
    parsed = sum(g["parsed"] for g in groups.values())
    finished = s["summary"] is not None and not alive
    phase = "done" if finished else (s["phase"] if alive else f"stopped ({s['phase']})")
    age = time.time() - log.stat().st_mtime
    out = [f"VLM run  {log.name}  ({'running' if alive else 'not running'}, log updated {age / 60:.0f} min ago)",
           f"phase    {phase}",
           "",
           f"uploaded  {bar(up, n, fail=fail)} {up + fail:>5}/{n} {pct(up + fail, n)}" + (f"  ({fail} failed)" if fail else ""),
           f"parsed    {bar(parsed, n)} {parsed:>5}/{n} {pct(parsed, n)}",
           f"S3 upload {bar(s['s3_up'] or s['s3_result_lines'], parsed or 1)} {s['s3_up'] or s['s3_result_lines']:>5}/{parsed}",
           f"cost      ${s['cost']:.2f}" + (f"   (+{s['done_before']} done before this run)" if s["done_before"] else ""),
           ""]
    for gi, g in sorted(groups.items()):
        st = g["state"] or ("failed" if g["fail"] == g["n"] else ("uploading" if g["up"] + g["fail"] < g["n"] else "queued"))
        tasks = g["tasks"] if len(g["tasks"]) <= 60 else g["tasks"][:57] + "..."
        out.append(f"  g{gi:<2} {bar(g['parsed'] or g['up'], g['n'], 16, g['fail'])} {g['parsed'] or g['up']:>4}/{g['n']:<4} "
                   f"{st:<10} ${g['cost']:>5.2f}  {tasks}")
    return "\n".join(out)


def line(s, alive):
    groups = s["groups"]
    n = s["todo"] or sum(g["n"] for g in groups.values())
    up = sum(g["up"] + g["fail"] for g in groups.values())
    parsed = sum(g["parsed"] for g in groups.values())
    fail = sum(g["fail"] for g in groups.values())
    done_groups = sum(1 for g in groups.values() if g["state"] == "collected" or g["fail"] == g["n"])
    if s["summary"] is not None and not alive:
        phase = "done"
    else:
        phase = {"waiting for Gemini": "gemini", "consolidating canonical_task": "consolidate",
                 "uploading results to S3": "s3 upload"}.get(s["phase"], s["phase"].replace("uploading group", "upload g"))
        if not alive:
            phase = "stopped"
    return (f"VLM {bar(parsed, n, 12)} {parsed}/{n} parsed · up {up}/{n}" + (f" ({fail}✗)" if fail else "")
            + f" · g {done_groups}/{s.get('n_groups', len(groups))} · ${s['cost']:.2f} · {phase}")


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    log = Path(args[0]) if args else max(HERE.glob("run_*.log"), key=lambda p: p.stat().st_mtime, default=None)
    if log is None or not log.exists():
        sys.exit("no run log found (run_*.log in the project root)")
    if not log.is_absolute() and not log.exists():
        log = HERE / log
    s = parse(log)
    alive = running()
    print(line(s, alive) if "--line" in sys.argv else render(s, log, alive))


if __name__ == "__main__":
    main()
