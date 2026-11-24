#!/usr/bin/env python3
"""Build reports/deep_checks.html: one page for every saved delivery deep check, with a switch between runs.

Each run is a folder reports/deep_checks/<id>/ (v1, v2, ...) holding the outputs of check_delivery.py
(delivery_check.csv, delivery_check_summary.csv) and a run.json with its label, date and notes.

After a new deep check:
    .venv/bin/python scripts/check_delivery.py --deep 2>&1 | tee check.log
    .venv/bin/python scripts/build_deep_checks_html.py --snapshot v2 --note "VLM counts complete"
--snapshot copies the current reports/delivery_check*.{csv,md} and check.log into reports/deep_checks/v2/
and writes its run.json; without it the page is only rebuilt from the saved runs.
"""
import argparse
import collections
import csv
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
RUNS = HERE / "reports" / "deep_checks"
OUT = HERE / "reports" / "deep_checks.html"
TEMPLATE = HERE / "scripts" / "deep_checks_template.html"
SNAP_FILES = ["delivery_check.csv", "delivery_check_summary.csv", "delivery_check_failures.csv",
              "delivery_check_deliverable.csv", "delivery_check_report.md"]

sys.path.insert(0, str(HERE / "scripts"))
from check_delivery import CHECK_IDS, CHECK_NAMES as NAMES  # noqa: E402  (one list of checks for both)

VLM_DEPENDENT = {"C1", "C2", "W2", "W3", "W4"}
WARN_KIND = {"W4": "warn", "W6": "warn", "W7": "calib", "W8": "sync", "W9": "gripper", "W10": "gripper", "W11": "bitrate"}


def run_key(p):
    m = re.fullmatch(r"v(\d+)", p.name)
    return (0, int(m.group(1))) if m else (1, p.name)


def snapshot(rid, notes):
    dst = RUNS / rid
    if dst.exists():
        raise SystemExit(f"{dst} exists already; pick a new id")
    dst.mkdir(parents=True)
    for f in SNAP_FILES:
        if (HERE / "reports" / f).exists():
            shutil.copy2(HERE / "reports" / f, dst / f)
    if (HERE / "check.log").exists():
        shutil.copy2(HERE / "check.log", dst / "check.log")
    n = sum(1 for _ in open(dst / "delivery_check.csv")) - 1
    meta = {"id": rid, "label": f"{rid} deep check", "date": datetime.date.today().isoformat(),
            "command": "scripts/check_delivery.py --deep", "notes": notes}
    (dst / "run.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"saved {n} recordings -> {dst}")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_run(d):
    meta = json.loads((d / "run.json").read_text()) if (d / "run.json").exists() else {"id": d.name}
    meta.setdefault("label", f"{d.name} deep check")
    rows = list(csv.DictReader(open(d / "delivery_check.csv")))
    summary = list(csv.DictReader(open(d / "delivery_check_summary.csv")))
    ids = [k for k in CHECK_IDS if k in rows[0]]

    checks = []
    for k in CHECK_IDS:
        if k not in ids:  # a check added after this run
            checks.append({"id": k, "name": NAMES[k], "hard": k[0] in "DVC", "vlm": k in VLM_DEPENDENT, "absent": True,
                           "counts": {}, "top": []})
            continue
        counts = collections.Counter(r[k] or "-" for r in rows)
        odd = collections.Counter(r[k + "_value"] for r in rows if r[k] not in ("PASS", "SKIP", "N/A", ""))
        checks.append({"id": k, "name": NAMES[k], "hard": k[0] in "DVC", "vlm": k in VLM_DEPENDENT,
                       "counts": dict(counts), "top": [[v, n] for v, n in odd.most_common(4)]})

    # recordings worth a look, one row per (recording, finding); the plain "no count yet" REVIEWs are left out
    issues = []
    for r in rows:
        dur = num(r["duration_s"])
        def add(check, kind, why):
            issues.append({"task": r["task"], "episode": r["episode"], "verdict": r["verdict"], "check": check,
                           "kind": kind, "reason": why, "duration": dur, "folder": r["folder"]})
        for k in ids:
            st, val = r[k], r[k + "_value"]
            if st == "FAIL":
                add(k, "dup" if k == "D6" else "fail", val)
            elif k == "C1" and st == "REVIEW" and val.startswith(("0 cycles", "1 cycles", "2 cycles")):
                add(k, "count", val)
            elif k == "W2" and st == "REVIEW":
                add(k, "setup", val)
            elif k == "W1" and st == "WARN" and "right, left" in val:
                add(k, "idle", val)
            elif st == "WARN" and k in WARN_KIND:
                add(k, WARN_KIND[k], val)
            elif st == "WARN" and k[0] in "DV":
                add(k, "warn", val)

    tot = next(s for s in summary if s["level"] == "all")
    return {"meta": meta, "total": tot, "summary": summary, "checks": checks, "issues": issues,
            "counted": sum(1 for r in rows if r["count_source"]),
            "count_sources": dict(collections.Counter(r["count_source"] or "none" for r in rows))}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--snapshot", metavar="ID", help="save the current reports as run ID (v2, v3, ...) first")
    ap.add_argument("--note", action="append", default=[], help="a note for the snapshot (repeatable)")
    a = ap.parse_args()
    if a.snapshot:
        snapshot(a.snapshot, a.note)
    runs = [load_run(d) for d in sorted((p for p in RUNS.iterdir() if (p / "delivery_check.csv").exists()), key=run_key)]
    if not runs:
        raise SystemExit(f"no runs under {RUNS}")
    data = json.dumps(runs, separators=(",", ":")).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.read_text().replace("/*__RUNS__*/[]", data))
    print(f"{len(runs)} run(s): {', '.join(r['meta']['id'] for r in runs)} -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
