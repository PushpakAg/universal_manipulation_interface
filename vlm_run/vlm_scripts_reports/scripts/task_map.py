"""Map every S3 task folder (and its episodes) to a task_id of task_data/UMI_Task_Matching_Report.xlsx.

One text-only Gemini call (no video): input = each folder's VLM canonical_task, agreement, objects, most common
episode wordings and the proposals of its outlier episodes, plus the collection sheet's tasks for the folder's date
(station where the sheet has one). Undated folders are treated as 20-11-2026 (the only other sheet date with stations).
Output: task_data/UMI_Task_Folder_Map.xlsx (Folder_Map, Episodes, Sheet_Tasks, README). Nothing in the VLM results
or on S3 is changed. The answer is cached in results/canonical/_task_map.json by input hash.

    .venv/bin/python scripts/task_map.py
"""
import collections, csv, hashlib, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.argv = sys.argv[:1]
import openpyxl  # noqa: E402
import run_s3_vlm as M  # noqa: E402
R = M.R

SHEET = ROOT / "task_data" / "UMI_Task_Matching_Report.xlsx"
OUT = ROOT / "task_data" / "UMI_Task_Folder_Map.xlsx"
CACHE = ROOT / "results" / "canonical" / "_task_map.json"
VERIFIED = ROOT / "task_data" / "verified_tasks.json"
HINTS = ROOT / "task_data" / "task_hints.json"
MODEL = json.loads((ROOT / "configs" / "s3_run.json").read_text())["model"]
DATE_OF = {"2026-11-21": "21-11-2026", "2026-11-22": "22-11-2026", "2026-11-24": "24-11-2026", "undated": "20-11-2026"}

PROMPT = {
    "system": "You match task folders of a robot-learning dataset to the task list of the data-collection log. A vision model watched every episode of a folder and named the task; the collection log lists what operators said they recorded that day (free text, often misspelt), each with a task_id and the official task wording. Use the log to identify which listed task the folder is; trust the vision model for what is physically visible (objects, action), and the log for the intended task when the vision model's naming is vague or slightly off (e.g. 'wall anchor' vs 'dowel pin' for similar small cylinders).",
    "instruction": "Return ONLY one JSON object matching `schema`. For every folder in the input: (1) choose the best task_id from candidates of the folder's date; prefer candidates with the folder's station when the log has one; one task_id may fit several folders. (2) If no candidate fits, task_id = null. (3) match_confidence: high = action and objects clearly the same; medium = same action, objects plausible; low = a guess. (4) vlm_conflict = true when the log task and the vision model's task differ in action or object kind (not wording). (5) If the folder's outlier episodes clearly show a different listed task, put them in other_tasks with that task_id. (6) reason: one short sentence. Use only folder names, episode ids and task_ids that appear in the input.",
    "schema": {"folders": [{"folder": "station/date/taskNN as given", "task_id": "IN-xxx or null",
                            "match_confidence": "high | medium | low", "vlm_conflict": "true | false",
                            "reason": "one short sentence",
                            "other_tasks": [{"task_id": "IN-xxx", "episodes": ["episode ids"]}]}]},
}


def sheet_tasks():
    wb = openpyxl.load_workbook(SHEET, data_only=True)
    new_ids = {}
    for r in wb["New_Task_Candidates"].iter_rows(min_row=4, values_only=True):
        if r[0] and r[3]:
            new_ids[r[3].strip().lower()] = (r[0], r[1], r[3])
    master = {}
    for r in wb["Master_Tasks"].iter_rows(min_row=2, values_only=True):
        if r[0]:
            master[r[0]] = {"category": r[1], "instruction": r[2], "workstation": r[6]}
    for tid, cat, ins in new_ids.values():
        master.setdefault(tid, {"category": cat, "instruction": ins, "workstation": "(new task candidate)"})
    rows = []
    for r in wb["Matched_Log"].iter_rows(min_row=2, values_only=True):
        if not r[0]:
            continue
        tid = r[4] or (new_ids.get((r[2] or "").strip().lower()) or (None,))[0]
        rows.append({"date": r[0], "recorded": (r[2] or "").strip(), "short": r[3], "task_id": tid,
                     "station": r[15], "hours": r[17] or 0})
    return rows, master


def folders():
    res = ROOT / "results"
    by = collections.defaultdict(list)
    for f in M.result_files(argparse_ns()):
        by[M.result_task(argparse_ns(), f)].append(f)
    hours = {}
    with open(ROOT / "report_summary.csv") as fh:
        for row in csv.DictReader(fh):
            if row["level"] == "station/date/task":
                hours[row["group"]] = float(row["hours"])
    out = {}
    for task, files in sorted(by.items()):
        eps, props, cons, canon = [], [], None, None
        for f in sorted(files):
            d = json.loads(f.read_text())
            ep = d.get("episode_id") or f.parent.name
            eps.append((ep, d, f))
            p = d.get("canonical_task_model") or {}
            props.append((f.parent.name, p))
            cons = d.get("canonical_task_consolidation") or cons
            canon = (d.get("response") or {}).get("canonical_task") or canon
        parts = task.split("/")
        station, date = parts[0], (parts[1] if len(parts) == 3 else "undated")
        rep_key = f"{station}/{date}/{parts[-1]}"
        out[task] = {"task": task, "station": station, "date": date, "folder": parts[-1], "key": rep_key,
                     "episodes": eps, "props": props, "cons": cons or {}, "canon": canon or {},
                     "hours": hours.get(rep_key, 0.0)}
    return out


_NS = None
def argparse_ns():
    global _NS
    if _NS is None:
        import argparse
        _NS = argparse.Namespace(results=ROOT / "results", s3_result_suffix="_vlm_result.json")
    return _NS


def build_input(F, rows, master):
    blocks = []
    for k, d in DATE_OF.items():
        cands, seen = [], {}
        for r in rows:
            if r["date"] != d:
                continue
            key = (r["recorded"].lower(), r["task_id"])
            if key in seen:
                if r["station"] and str(r["station"]) not in seen[key]["stations"]:
                    seen[key]["stations"].append(str(r["station"]))
                seen[key]["hours"] += r["hours"]
                continue
            c = {"task_id": r["task_id"], "recorded": r["recorded"],
                 "official": (master.get(r["task_id"]) or {}).get("instruction"),
                 "stations": [str(r["station"])] if r["station"] else [], "hours": r["hours"]}
            seen[key] = c
            cands.append(c)
        lines = [f"{c['task_id'] or 'no-id'} | station {','.join(c['stations']) or '?'} | {c['hours']:.2f} h | "
                 f"recorded: {c['recorded']} | official: {c['official'] or '-'}" for c in cands]
        blocks.append(f"## log candidates for folder date {k} (log date {d})\n" + "\n".join(lines))
    fl = []
    for t, x in F.items():
        c, cons = x["canon"], x["cons"]
        outl = set(cons.get("outlier_episodes") or [])
        common = collections.Counter((p.get("task_text") or "").strip() for _, p in x["props"]).most_common(4)
        s = [f"### folder {x['key']} | station {x['station'][-1]} | date {x['date']} | {len(x['episodes'])} episodes | {x['hours']:.2f} h",
             f"vision canonical: {c.get('task_text')} | action: {c.get('action')} | objects: {', '.join(c.get('object_categories') or [])} | agreement {cons.get('support')}",
             "most common episode wordings: " + " || ".join(f"{w} (x{n})" for w, n in common)]
        if outl:
            s.append("outlier episodes:")
            s += [f"  {ep} | {p.get('action')} | {', '.join(p.get('object_categories') or [])} | {p.get('task_text')}"
                  for ep, p in x["props"] if ep in outl]
        fl.append("\n".join(s))
    return "\n\n".join(blocks) + "\n\n# folders\n\n" + "\n\n".join(fl)


def call(user):
    h = hashlib.sha1((json.dumps(PROMPT) + MODEL + user).encode()).hexdigest()[:16]
    if CACHE.exists():
        c = json.loads(CACHE.read_text())
        if c.get("input_hash") == h:
            print("cached answer (no API call)")
            return c["output"], c["usage"]
    mcfg = R.model_cfgs([MODEL])[MODEL]
    key = R.load_env_key(mcfg["api_key_env"])
    req = {"systemInstruction": {"parts": [{"text": PROMPT["system"]}]},
           "contents": [{"role": "user", "parts": [
               {"text": json.dumps({k: PROMPT[k] for k in ("instruction", "schema")}, ensure_ascii=False)},
               {"text": user}]}],
           "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json", "maxOutputTokens": 65536,
                                "thinkingConfig": {"thinkingLevel": "medium"}}}
    g = R.gemini_generate(MODEL, key, req, 900)
    text, fin, um = R.gemini_text_usage(g)
    out = R.parse_json(text)
    usage = R.gemini_usage(mcfg, um, False)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"input_hash": h, "model": MODEL, "input": user, "output": out, "usage": usage,
                                 "finish": fin, "created": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1, ensure_ascii=False))
    return out, usage


def write_xlsx(F, ans, rows, master, usage):
    from openpyxl.styles import Font, PatternFill, Alignment
    by = {a["folder"]: a for a in ans.get("folders", [])}
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Folder_Map"
    hdr = ["task_folder", "station", "date", "folder", "episodes", "hours", "task_id", "official_task (sheet)",
           "recorded_as (sheet)", "category", "match_confidence", "vlm_conflict", "vlm_canonical_task", "vlm_agreement",
           "other_task_ids (outlier episodes)", "reason", "verified_task (by eye)", "s3_folder"]
    ws.append(hdr)
    rec_by_id = collections.defaultdict(list)
    for r in rows:
        if r["task_id"] and r["recorded"] not in rec_by_id[r["task_id"]]:
            rec_by_id[r["task_id"]].append(r["recorded"])
    ep_rows, used = [], collections.Counter()
    src = "s3://prod-mono-pipeline-v2-data/umi_data/industrial_data_mp4/"
    for t, x in F.items():
        a = by.get(x["key"]) or by.get(t) or {}
        tid = a.get("task_id")
        m = master.get(tid) or {}
        others = {e: o.get("task_id") for o in a.get("other_tasks") or [] for e in o.get("episodes") or []}
        ws.append([x["key"], x["station"], x["date"], x["folder"], len(x["episodes"]), round(x["hours"], 3), tid,
                   m.get("instruction"), " / ".join(rec_by_id.get(tid, [])[:3]), m.get("category"),
                   a.get("match_confidence"), str(a.get("vlm_conflict")).lower() if a else None,
                   x["canon"].get("task_text"), x["cons"].get("support"),
                   "; ".join(f"{o.get('task_id')}: {len(o.get('episodes') or [])} eps" for o in a.get("other_tasks") or []),
                   a.get("reason"), a.get("verified_task"), src + t + "/"])
        outl = set(x["cons"].get("outlier_episodes") or [])
        for ep, d, f in x["episodes"]:
            name = f.parent.name
            etid = others.get(name, tid)
            used[etid] += 1
            resp = d.get("response") or {}
            ep_rows.append([x["key"], name, etid, (master.get(etid) or {}).get("instruction"),
                            "other task (outlier)" if name in others else ("outlier, unmatched" if name in outl else "folder task"),
                            (resp.get("task") or {}).get("task_text"), x["canon"].get("task_text"),
                            src + t + "/" + name + "/"])
    es = wb.create_sheet("Episodes")
    es.append(["task_folder", "episode", "task_id", "official_task (sheet)", "assignment", "vlm_episode_task",
               "vlm_canonical_task", "s3_episode_folder"])
    for r in ep_rows:
        es.append(r)
    ss = wb.create_sheet("Sheet_Tasks")
    ss.append(["task_id", "official_task", "category", "recorded_as", "sheet_hours", "s3_folders", "s3_episodes"])
    fold_by_id = collections.defaultdict(list)
    for a in ans.get("folders", []):
        if a.get("task_id"):
            fold_by_id[a["task_id"]].append(a["folder"])
    hrs = collections.Counter()
    for r in rows:
        if r["task_id"]:
            hrs[r["task_id"]] += r["hours"]
    for tid in sorted(set(rec_by_id) | set(fold_by_id)):
        m = master.get(tid) or {}
        ss.append([tid, m.get("instruction"), m.get("category"), " / ".join(rec_by_id.get(tid, [])), round(hrs[tid], 3),
                   ", ".join(fold_by_id.get(tid, [])), used.get(tid, 0)])
    rd = wb.create_sheet("README")
    for line in [
        "Map of S3 task folders and episodes to task_ids of UMI_Task_Matching_Report.xlsx.",
        f"Made {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} with one text-only {MODEL} call (no video), cost ${usage.get('cost_usd', 0):.4f}.",
        "Input per folder: the VLM canonical task, agreement, objects, most common episode wordings and the outlier episodes' proposals; plus the log's tasks for the folder's date.",
        "Undated S3 folders (station1/task03-05, station3/task03-04) are matched against the 20-11-2026 log (the only other date with stations).",
        "match_confidence: high = same action and objects; medium = same action, objects plausible; low = a guess. vlm_conflict = the log task and the VLM task differ in action or object kind.",
        "Episodes: task_id is the folder's, except outlier episodes the call matched to another task_id ('other task (outlier)').",
        "verified (green rows): folder task checked by eye on a few episodes (task_data/verified_tasks.json); overrides the LLM match.",
        "The VLM result files and S3 are NOT changed by this map; task_id is not written into any VLM response.",
    ]:
        rd.append([line])
    bold = Font(bold=True); fill = PatternFill("solid", fgColor="DDEBF7")
    for w in wb.worksheets:
        if w.title == "README":
            w.column_dimensions["A"].width = 160; continue
        for c in w[1]:
            c.font = bold; c.fill = fill; c.alignment = Alignment(wrap_text=True, vertical="top")
        w.freeze_panes = "B2"; w.auto_filter.ref = w.dimensions
        for col in w.columns:
            L = max(len(str(c.value or "")) for c in col[:200])
            w.column_dimensions[col[0].column_letter].width = min(max(10, L + 2), 70)
    hl = PatternFill("solid", fgColor="FCE4D6")
    for row in ws.iter_rows(min_row=2):
        if row[10].value == "verified":
            for c in row:
                c.fill = PatternFill("solid", fgColor="E2EFDA")
        elif row[10].value == "low" or row[11].value == "true" or row[6].value is None:
            for c in row:
                c.fill = hl
    wb.save(OUT)


def write_hints(F, ans, rows):
    """Grounding hints for the canonical aggregation (keyed by the results task path). Only the operator's own
    words (or the by-eye description): no task_id, no official master wording."""
    by = {a["folder"]: a for a in ans.get("folders", [])}
    hints = {"_note": "Written by scripts/task_map.py. Read by run_s3_vlm.py canonical aggregation as a grounding "
                      "hint. Contains no task_id. source: verified = checked by eye; log = operator's recorded "
                      "instruction(s) for the matched task on that date."}
    for t, x in F.items():
        a = by.get(x["key"]) or {}
        if a.get("verified_task"):
            hints[t] = {"source": "verified", "hint": [a["verified_task"]]}
            continue
        tid = a.get("task_id")
        if not tid or a.get("match_confidence") == "low":
            continue
        rec = []
        for same_date in (True, False):
            for r in rows:
                if r["task_id"] == tid and (r["date"] == DATE_OF[x["date"]]) == same_date and r["recorded"] not in rec:
                    rec.append(r["recorded"])
            if rec:
                break
        hints[t] = {"source": "log", "match_confidence": a.get("match_confidence"), "hint": rec[:6]}
    HINTS.write_text(json.dumps(hints, indent=1, ensure_ascii=False))
    print(f"wrote {len(hints) - 1} folder hint(s) -> {HINTS}")


def main():
    rows, master = sheet_tasks()
    F = folders()
    user = build_input(F, rows, master)
    print(f"{len(F)} folders, {sum(len(x['episodes']) for x in F.values())} episodes, {len(rows)} log rows; input ~{len(user)//4} tokens")
    ans, usage = call(user)
    ver = {k: v for k, v in json.loads(VERIFIED.read_text()).items() if not k.startswith("_")} if VERIFIED.exists() else {}
    for a in ans.get("folders", []):
        v = ver.get(a["folder"])
        if v:
            a.update(task_id=v["task_id"], match_confidence="verified", vlm_conflict=a.get("vlm_conflict"),
                     verified_task=v["verified_task"], reason=f"checked by eye; LLM match was {a.get('task_id')}: {a.get('reason')}",
                     other_tasks=[])
    print(f"applied {sum(1 for a in ans.get('folders', []) if a.get('verified_task'))} verified folder(s)")
    write_xlsx(F, ans, rows, master, usage)
    write_hints(F, ans, rows)
    got = {a["folder"] for a in ans.get("folders", [])}
    miss = [x["key"] for x in F.values() if x["key"] not in got]
    print(f"answered {len(got)} folders, missing {len(miss)} {miss[:5]}; cost ${usage.get('cost_usd', 0):.4f} -> {OUT}")


if __name__ == "__main__":
    main()
