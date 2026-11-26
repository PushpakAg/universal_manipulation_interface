#!/usr/bin/env python3
"""reports/ingestion/funnel.html from the CSVs of ingestion_funnel.py and the deep check run (one page, data inline).

    .venv/bin/python scripts/ingestion_funnel.py && .venv/bin/python scripts/build_funnel_html.py
"""
import collections
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
D = HERE / "reports" / "ingestion"


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def note_kinds(note):
    """pairs.csv note -> kinds: '<camera> stops early', '<camera> split over files'."""
    out = set()
    for part in filter(None, (p.strip() for p in note.split(";"))):
        cam = part.split(":")[0].split(" ")[0]
        out.add(f"{cam} camera stops early" if "stops" in part else f"{cam} camera split over files (gaps)")
    return sorted(out)


def main():
    vids = list(csv.DictReader(open(D / "videos.csv")))
    takes = list(csv.DictReader(open(D / "takes.csv")))
    tasks = list(csv.DictReader(open(D / "tasks.csv")))
    md = (D / "funnel.md").read_text()
    run = md.split("deep check run ")[1].split(")")[0]
    H = lambda vs: sum(f(v["duration"]) for v in vs) / 3600
    by = collections.defaultdict(list)
    for v in vids:
        by[v["status"]].append(v)
    status = {s: {"n": len(vs), "h": round(H(vs), 2)} for s, vs in by.items()}
    proc = [t for t in tasks if t["processed"] == "True"]
    unproc = [t for t in tasks if t["processed"] != "True"]
    S = lambda xs, k: round(sum(f(x[k]) for x in xs), 2)
    prod_all_cam = sum(status[s]["h"] for s in status if s not in ("pilot", "set"))
    all_cam = sum(x["h"] for x in status.values())
    data = {
        "run": run,
        "status": status,
        # ingested recording hours per view = all camera hours / 3 (pilot files have no camera folder)
        "ingested": {"production": round(prod_all_cam / 3, 2), "all": round(all_cam / 3, 2),
                     "files_production": sum(status[s]["n"] for s in status if s not in ("pilot", "set")),
                     "files_all": sum(x["n"] for x in status.values())},
        "stages": [
            ["Paired into takes (head file)", len(takes), S(tasks, "take_h_head")],
            ["Shared window of the 3 cameras", len(takes), S(tasks, "shared_h")],
            ["In task folders that were processed", int(S(proc, "takes")), S(proc, "shared_h")],
            ["Cut into episodes (processed MP4s)", int(S(proc, "episodes")), S(proc, "episode_h")],
            ["Deliverable (data checks pass)", int(S(proc, "deliverable")), S(proc, "deliverable_h")],
            ["Also pass the VLM repetition checks", None, S(proc, "both_pass_h")],
        ],
        "mismatch_h": S(tasks, "mismatch_h"),
        "mismatch_takes": sum(1 for t in takes if f(t["mismatch_sec"]) > 10),
        "noted_takes": sum(1 for t in takes if t["note"]),
        "notes": collections.Counter(c for t in takes for c in note_kinds(t["note"])).most_common(),
        "unproc": [[t["folder"].replace("/raw_videos", ""), t["date"], int(f(t["takes"])), round(f(t["shared_h"]), 2)]
                   for t in unproc],
        "yield": [],
        "sessions": [],
        "long_left": [[v["station"], v["date"], v["cam"], v["name"], round(f(v["duration"]) / 60, 1)]
                      for v in vids if v["status"] == "left_out" and f(v["duration"]) >= 480],
        "problems": [l[2:] for l in md.split("## Pairing problems")[1].splitlines() if l.startswith("- ")]
        if "## Pairing problems" in md else [],
    }
    g = collections.defaultdict(list)
    for t in proc:
        g[(t["station"], t["date"])].append(t)
    for (st, d), xs in sorted(g.items()):
        sh = S(xs, "shared_h")
        data["yield"].append([st, d, len(xs), int(S(xs, "takes")), sh, int(S(xs, "episodes")), S(xs, "episode_h"),
                              S(xs, "deliverable_h")])
    paired_days = collections.Counter((t["station"], t["start"][:10]) for t in takes)
    lo = [v for v in vids if v["status"] in ("left_out", "in_task_unlisted")]
    s2 = collections.defaultdict(list)
    for v in lo:
        s2[(v["station"], v["date"])].append(v)
    for (st, d), vs in sorted(s2.items()):
        b = [sum(lo_ <= f(v["duration"]) < hi for v in vs) for lo_, hi in ((0, 30), (30, 120), (120, 480), (480, 1e9))]
        data["sessions"].append([st, d, paired_days.get((st, d), 0), len(vs), round(H(vs), 2), *b])
    tpl = (HERE / "scripts" / "funnel_template.html").read_text()
    out = D / "funnel.html"
    out.write_text(tpl.replace("/*__DATA__*/{}", json.dumps(data, separators=(",", ":")).replace("</", "<\\/")))
    print(f"-> {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
