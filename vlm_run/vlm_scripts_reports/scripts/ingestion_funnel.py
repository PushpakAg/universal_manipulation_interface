#!/usr/bin/env python3
"""Ingestion -> processed MP4 funnel: what was recorded, what was paired, what was processed, what is deliverable.

Sources (S3):
  ingestion  upload_ingestion/GoPro/UMI_Collection/
     <station>/<date>/{head,left,right}/GX*.MP4          raw camera dumps (Set_2 / Set_3: same layout, no tasks)
     <station>/industrial_data*/[<date>/]<task>/raw_videos/{GX*.MP4, pairs.csv, gripper_calibration/, head_mapping/}
                                                         production task folders: copies of dump files + pairing
     <station>/<other>/raw_videos/                       pilot / test sessions (no pairs.csv)
     <station>/calibration/...                           camera calibration recordings
  processed  reports/deep_checks/<run>/delivery_check.csv (check_delivery.py over umi_data/industrial_data_mp4/)

A raw video is one file of a camera dump, identified by (station, file name, size); the copies in task folders
are matched to it. Each is classified:
  take           listed as head / left / right of a take in a pairs.csv
  support        listed as gripper_calibration / head_mapping in a pairs.csv
  calibration    in a station calibration/ folder
  pilot          only in a pilot / test task folder (no pairs.csv)
  set            in Set_2 / Set_3 (dumps without task folders)
  left_out       in a production dump, in no task folder at all
Two scopes: "production" (station dumps, production task folders and calibration) and "all" (+ pilot, Set_2/3).

    .venv/bin/python scripts/ingestion_funnel.py                 # durations cached in reports/ingestion/durations.csv
    .venv/bin/python scripts/ingestion_funnel.py --run v4

Output reports/ingestion/: funnel.md, videos.csv (every raw video), takes.csv (every take), tasks.csv (per task
folder: takes, hours, episodes, yield).
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import io
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "scripts"))
from check_delivery import S3, ffprobe, load_env, clean  # noqa: E402

BUCKET = "prod-mono-pipeline-v2-data"
ROOT = "upload_ingestion/GoPro/UMI_Collection/"
OUT = HERE / "reports" / "ingestion"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CAMS = ("head", "left", "right")


def classify_key(k):
    """(kind, station, info) of an ingestion object key relative to ROOT."""
    p = k.split("/")
    st = p[0]
    if len(p) == 4 and DATE.match(p[1]) and p[2] in CAMS:
        return "dump", st, {"date": p[1], "cam": p[2]}
    if len(p) > 1 and p[1] == "calibration":
        return "calibration", st, {}
    if "raw_videos" in p:
        i = p.index("raw_videos")
        folder = "/".join(p[: i + 1])
        prod = p[1].startswith("industrial_data")
        return ("task" if prod else "pilot"), st, {"folder": folder, "sub": p[i + 1] if len(p) > i + 2 else ""}
    return "other", st, {}


def out_task(folder):
    """Processed task path (as in industrial_data_mp4) of a production task folder."""
    p = folder.split("/")[:-1]  # drop raw_videos
    st, rest = p[0], p[1:]
    if rest[0].startswith("industrial_data_"):
        rest = [rest[0][len("industrial_data_"):]] + rest[1:]
    else:
        rest = rest[1:]
    return "/".join([st] + rest)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mins(d):
    return "" if d is None else f"{d / 60:.1f} min"


def main():
    ap =argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", default=None, help="deep check run under reports/deep_checks/ (default: latest)")
    ap.add_argument("--workers", type=int, default=32)
    a = ap.parse_args()
    load_env(HERE / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    store = S3(f"s3://{BUCKET}/{ROOT}")
    objs = [(k, n) for k, n in store.list()]
    print(f"{len(objs)} ingestion objects", flush=True)

    # ---- raw videos (unique) and where each appears
    videos = {}  # (station, name, size) -> record
    def vid(st, name, size):
        return videos.setdefault((st, name, size), {"station": st, "name": name, "size": size, "key": None,
                                                     "date": "", "cam": "", "in_dump": False, "folders": set(),
                                                     "pilot": set(), "calibration": False})
    pairs_keys = []
    for k, n in objs:
        rel = k[len(ROOT):]
        if rel.endswith("/raw_videos/pairs.csv"):
            pairs_keys.append(k)
            continue
        if not rel.lower().endswith(".mp4"):
            continue
        kind, st, info = classify_key(rel)
        name = rel.rsplit("/", 1)[-1]
        v = vid(st, name, n)
        if kind == "dump":
            v.update(in_dump=True, key=k, date=info["date"], cam=info["cam"])
        else:
            v["key"] = v["key"] or k
            if kind == "task":
                v["folders"].add(info["folder"])
            elif kind == "pilot":
                v["pilot"].add(info["folder"])
            elif kind == "calibration":
                v["calibration"] = True
    by_name = collections.defaultdict(list)  # (station, name) -> videos (for pairs lookups)
    for v in videos.values():
        by_name[(v["station"], v["name"])].append(v)

    # ---- durations (header only), cached
    cache_p = OUT / "durations.csv"
    cache = {}
    if cache_p.exists():
        cache = {(r["key"], int(r["size"])): num(r["duration_s"]) for r in csv.DictReader(open(cache_p))}
    todo = [v for v in videos.values() if (v["key"], v["size"]) not in cache]
    print(f"{len(videos)} unique raw videos; probing {len(todo)}", flush=True)

    def probe(v):
        try:
            return v, ffprobe(store.url(v["key"]))["duration"]
        except Exception as ex:
            print("  probe failed:", v["key"], clean(ex)[:100], flush=True)
            return v, None
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, (v, d) in enumerate(ex.map(probe, todo), 1):
            cache[(v["key"], v["size"])] = d
            if i % 200 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    with open(cache_p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "size", "duration_s"])
        w.writerows([k, s, "" if d is None else round(d, 3)] for (k, s), d in sorted(cache.items()))
    for v in videos.values():
        v["duration"] = cache.get((v["key"], v["size"]))

    # ---- pairs.csv: takes and support clips
    takes, problems = [], []
    use = collections.defaultdict(list)  # video id -> [(folder, role, recording)]
    for k in sorted(pairs_keys):
        rel = k[len(ROOT):]
        folder = rel.rsplit("/", 1)[0]
        st = folder.split("/")[0]
        rows = list(csv.DictReader(io.StringIO(store.read_text(k))))
        for r in rows:
            for role in CAMS:
                for name in [x.strip() for x in (r.get(role) or "").split(";") if x.strip()]:
                    cands = by_name.get((st, name), [])
                    cands = [c for c in cands if folder in c["folders"]] or cands
                    if not cands:
                        problems.append(f"{folder}: {name} ({r['type']} {role}) not found in the ingestion")
                        continue
                    v = cands[0]
                    use[id(v)].append((folder, r["type"], role, r.get("recording", "")))
                    if r["type"] == "take" and v["cam"] and v["cam"] != role:
                        problems.append(f"{folder}: take {r.get('recording')} {role} = {name}, but that file is in "
                                        f"the {v['cam']} dump ({v['date']})")
            if r["type"] == "take":
                secs = {c: num(r.get(f"{c}_sec")) for c in CAMS}
                shared = num(r.get("shared_sec"))
                longest = max([s for s in secs.values() if s] or [0])
                takes.append({"station": st, "folder": folder, "task": out_task(folder), "recording": r.get("recording"),
                              "start": r.get("start"), "end": r.get("end"), **{c: r.get(c) for c in CAMS},
                              **{f"{c}_sec": secs[c] for c in CAMS}, "shared_sec": shared,
                              "mismatch_sec": round(longest - shared, 1) if shared is not None else None,
                              "note": r.get("note", "")})

    # ---- classify each raw video
    for v in videos.values():
        roles = {t for _, t, _, _ in use.get(id(v), [])}
        if "take" in roles:
            v["status"] = "take"
        elif roles:
            v["status"] = "support"
        elif v["station"].startswith("Set_"):
            v["status"] = "set"
        elif v["calibration"]:
            v["status"] = "calibration"
        elif v["pilot"]:
            v["status"] = "pilot"
        elif v["folders"]:
            v["status"] = "in_task_unlisted"  # copied into a production task folder but not in its pairs.csv
        else:
            v["status"] = "left_out"
        v["used_in"] = "; ".join(sorted({f"{f} {t} {r} {rec}".strip() for f, t, r, rec in use.get(id(v), [])}))

    # ---- processed episodes (deep check run)
    runs = sorted(p for p in (HERE / "reports" / "deep_checks").iterdir() if (p / "delivery_check.csv").exists())
    run = (HERE / "reports" / "deep_checks" / a.run) if a.run else max(runs, key=lambda p: (len(p.name), p.name))
    eps = list(csv.DictReader(open(run / "delivery_check.csv")))
    by_task = collections.defaultdict(list)
    for e in eps:
        by_task[e["task"]].append(e)

    # ---- per task folder
    tasks = collections.OrderedDict()
    for t in takes:
        x = tasks.setdefault(t["folder"], {"station": t["station"], "folder": t["folder"], "task": t["task"],
                                           "takes": 0, "take_h_head": 0.0, "shared_h": 0.0, "mismatch_h": 0.0,
                                           "notes": 0, "first_start": t["start"]})
        x["takes"] += 1
        x["take_h_head"] += (t["head_sec"] or 0) / 3600
        x["shared_h"] += (t["shared_sec"] or 0) / 3600
        x["mismatch_h"] += (t["mismatch_sec"] or 0) / 3600
        x["notes"] += bool(t["note"])
    for x in tasks.values():
        e = by_task.get(x["task"], [])
        h = lambda rs: sum(num(r["duration_s"]) or 0 for r in rs) / 3600
        x.update(processed=bool(e), episodes=len(e), episode_h=h(e),
                 deliverable=sum(r["verdict"] == "PASS" for r in e),
                 deliverable_h=h([r for r in e if r["verdict"] == "PASS"]),
                 both_pass_h=h([r for r in e if r["verdict"] == "PASS" and r.get("vlm_verdict") == "PASS"]),
                 date=(x["first_start"] or "")[:10])
        x["yield_episode"] = x["episode_h"] / x["shared_h"] if x["shared_h"] and e else None
        x["yield_deliverable"] = x["deliverable_h"] / x["shared_h"] if x["shared_h"] and e else None
    loose = by_task.get("industrial_data_mp4", [])

    # ---- write CSVs
    vcols = ["station", "date", "cam", "name", "size", "duration", "status", "used_in", "key"]
    with open(OUT / "videos.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=vcols, extrasaction="ignore")
        w.writeheader()
        for v in sorted(videos.values(), key=lambda v: (v["station"], v["date"], v["cam"], v["name"])):
            w.writerow({**v, "duration": "" if v["duration"] is None else round(v["duration"], 1),
                        "key": f"s3://{BUCKET}/{v['key']}"})
    tcols = ["station", "folder", "task", "recording", "start", "end", "head", "head_sec", "left", "left_sec", "right",
             "right_sec", "shared_sec", "mismatch_sec", "note"]
    with open(OUT / "takes.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=tcols + ["processed"], extrasaction="ignore")
        w.writeheader()
        for t in takes:
            w.writerow({**t, "processed": tasks[t["folder"]]["processed"]})
    kcols = ["station", "date", "task", "folder", "takes", "take_h_head", "shared_h", "mismatch_h", "notes",
             "processed", "episodes", "episode_h", "yield_episode", "deliverable", "deliverable_h", "yield_deliverable",
             "both_pass_h"]
    with open(OUT / "tasks.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=kcols, extrasaction="ignore")
        w.writeheader()
        for x in tasks.values():
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()})

    # ---- funnel, two scopes
    H = lambda vs: sum(v["duration"] or 0 for v in vs) / 3600
    allv = list(videos.values())
    scopes = {"production": [v for v in allv if v["status"] not in ("pilot", "set")], "all": allv}
    md = ["# Ingestion -> processed MP4 funnel", "",
          f"Ingestion `s3://{BUCKET}/{ROOT}`, processed `umi_data/industrial_data_mp4/` (deep check run "
          f"{run.name}). Hours of raw video are per camera file (head + left + right add up); take and episode hours "
          f"are recording time (one view).", ""]
    md += ["## Raw videos by status", "",
           "| Status | Scope | Videos | Hours (all cameras) | Head videos | Head hours |", "|---|---|---|---|---|---|"]
    order = ["take", "support", "calibration", "in_task_unlisted", "left_out", "pilot", "set"]
    for s in order:
        vs = [v for v in allv if v["status"] == s]
        if not vs:
            continue
        hv = [v for v in vs if v["cam"] == "head"]
        md.append(f"| {s} | {'all only' if s in ('pilot', 'set') else 'both'} | {len(vs)} | {H(vs):.2f} | {len(hv)} | "
                  f"{H(hv):.2f} |")
    for name, vs in scopes.items():
        md.append(f"| **total {name}** | | **{len(vs)}** | **{H(vs):.2f}** | {sum(v['cam'] == 'head' for v in vs)} | "
                  f"{H([v for v in vs if v['cam'] == 'head']):.2f} |")

    tk = list(tasks.values())
    proc = [x for x in tk if x["processed"]]
    unproc = [x for x in tk if not x["processed"]]
    S = lambda xs, k: sum(x[k] or 0 for x in xs)
    hours_all_head = H([v for v in scopes["all"] if v["cam"] == "head"])
    hours_prod_head = H([v for v in scopes["production"] if v["cam"] == "head"])
    md += ["", "## Funnel (recording hours = head camera)", "",
           "| Stage | Count | Hours | % of production head hours | % of all head hours |", "|---|---|---|---|---|"]
    def stage(lbl, cnt, h):
        md.append(f"| {lbl} | {cnt} | {h:.2f} | {100 * h / hours_prod_head:.1f}% | {100 * h / hours_all_head:.1f}% |")
    stage("Ingested head videos, all (incl. pilot, Set_2/3)", sum(v["cam"] == "head" for v in scopes["all"]), hours_all_head)
    stage("Ingested head videos, production", sum(v["cam"] == "head" for v in scopes["production"]), hours_prod_head)
    stage("Paired takes (head file length)", len(takes), S(tk, "take_h_head"))
    stage("Paired takes, shared window of the 3 cameras", len(takes), S(tk, "shared_h"))
    stage("... in task folders that were processed", S(proc, "takes"), S(proc, "shared_h"))
    stage("Episodes cut (processed MP4s, excl. 15 loose copies)", S(proc, "episodes"), S(proc, "episode_h"))
    stage("Deliverable episodes (data checks PASS)", S(proc, "deliverable"), S(proc, "deliverable_h"))
    stage("Deliverable + repetition checks PASS (VLM)", "", S(proc, "both_pass_h"))
    md += ["", f"Loose recordings at the root of industrial_data_mp4 (copies, D6): {len(loose)}, "
           f"{sum(num(r['duration_s']) or 0 for r in loose) / 3600:.2f} h (not counted above).", ""]

    md += ["## Deltas", "",
           f"- Head videos never paired (production): "
           f"{sum(v['cam'] == 'head' and v['status'] not in ('take',) for v in scopes['production'])} files, "
           f"{H([v for v in scopes['production'] if v['cam'] == 'head' and v['status'] != 'take']):.2f} h "
           f"(support clips, calibration and left-out; split in the table above).",
           f"- Camera length mismatch inside takes (longest camera minus shared window): {S(tk, 'mismatch_h'):.2f} h "
           f"over {sum(1 for t in takes if (t['mismatch_sec'] or 0) > 10)} takes with > 10 s; "
           f"{sum(1 for t in takes if t['note'])} takes carry a note (a camera stopped early, split files).",
           f"- Paired but not processed: {len(unproc)} task folders, {S(unproc, 'takes')} takes, "
           f"{S(unproc, 'shared_h'):.2f} h shared.",
           f"- Processed take time not in any episode (cut out between episodes): "
           f"{S(proc, 'shared_h') - S(proc, 'episode_h'):.2f} h "
           f"({100 * (1 - S(proc, 'episode_h') / S(proc, 'shared_h')):.1f}% of processed take time).",
           f"- Episodes failing the data checks: {S(proc, 'episodes') - S(proc, 'deliverable')}, "
           f"{S(proc, 'episode_h') - S(proc, 'deliverable_h'):.2f} h.", ""]

    md += ["## Yield by station and date (processed task folders)", "",
           "| Station | Date | Task folders | Takes | Shared h | Episodes | Episode h | Episode yield | Deliverable h | Deliverable yield |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    grp = collections.defaultdict(list)
    for x in proc:
        grp[(x["station"], x["date"])].append(x)
    for (st, d), xs in sorted(grp.items()):
        sh = S(xs, "shared_h")
        md.append(f"| {st} | {d} | {len(xs)} | {S(xs, 'takes')} | {sh:.2f} | {S(xs, 'episodes')} | "
                  f"{S(xs, 'episode_h'):.2f} | {100 * S(xs, 'episode_h') / sh:.0f}% | {S(xs, 'deliverable_h'):.2f} | "
                  f"{100 * S(xs, 'deliverable_h') / sh:.0f}% |")

    md += ["", "## Paired task folders not processed", "", "| Task folder | Date | Takes | Shared h |", "|---|---|---|---|"]
    md += [f"| {x['folder']} | {x['date']} | {x['takes']} | {x['shared_h']:.2f} |" for x in unproc]

    lo = sorted((v for v in allv if v["status"] in ("left_out", "in_task_unlisted")),
                key=lambda v: (v["station"], v["date"], v["cam"], v["name"]))
    # left-out by session: a whole day without task folders vs short clips around the takes
    sess = collections.defaultdict(list)
    for v in lo:
        sess[(v["station"], v["date"])].append(v)
    paired_days = {(t["station"], (t["start"] or "")[:10]) for t in takes}
    md += ["", "## Left-out raw videos by session (head / left / right files; length buckets over all three)", "",
           "| Station | Date | Takes paired that day | Head files | Head h | All files | All h | < 30 s | 30 s-2 min | 2-8 min | >= 8 min |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (st, d), vs in sorted(sess.items()):
        hv = [v for v in vs if v["cam"] == "head"]
        b_ = [sum(lo_ <= (v["duration"] or 0) < hi for v in vs) for lo_, hi in ((0, 30), (30, 120), (120, 480), (480, 1e9))]
        md.append(f"| {st} | {d} | {sum(1 for t in takes if t['station'] == st and (t['start'] or '')[:10] == d)}"
                  f"{'' if (st, d) in paired_days else ' (none)'} | {len(hv)} | {H(hv):.2f} | {len(vs)} | {H(vs):.2f} | "
                  + " | ".join(map(str, b_)) + " |")
    md += ["", f"## Left-out raw videos ({len(lo)}: in a production dump, in no pairs.csv)", "",
           "| Station | Date | Camera | File | Length | Status |", "|---|---|---|---|---|---|"]
    md += [f"| {v['station']} | {v['date']} | {v['cam']} | {v['name']} | "
           f"{mins(v['duration'])} | {v['status']} |" for v in lo]
    if problems:
        md += ["", f"## Pairing problems ({len(problems)})", ""] + [f"- {p}" for p in problems]
    md += ["", "Files: `videos.csv` (every raw video with its status and use), `takes.csv` (every take: files, lengths, "
           "shared window, mismatch, note), `tasks.csv` (per task folder: takes, hours, episodes, yield).", ""]
    (OUT / "funnel.md").write_text("\n".join(md))
    print("\n".join(md[:60]))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
