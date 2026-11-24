#!/usr/bin/env python3
"""Task-only result files (local only, nothing goes to S3): each episode keeps ONLY

    {"task": {task_text, task_family, action, object_categories}, "n_repetitions": <manual count or null>}

task fields are reused from the run that identified the task best (no new VLM call):
    task01, task02, task03  R1  images 3 fps low   results/station2/2026-11-22/<task>/<episode>/
    task04, task06          R2  images 1 fps medium snapshots/1fps_medium_t04_t06/<task>/<episode>/
n_repetitions comes from the manual count in reports/manual_counts.csv (column n_repetitions_manual); empty -> null.
The sheet is created on the first run (task fields filled in, counts empty); run again after counting to fill the files.

Output: task_only/station2/2026-11-22/<task>/<episode>/<name>_vlm_result.json  (same file name as the S3 results)
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # project root vlm_scripts_reports/ (scripts live in scripts/)
DAY = "station2/2026-11-22"
SOURCES = {"task01": HERE / "results" / DAY, "task02": HERE / "results" / DAY, "task03": HERE / "results" / DAY,
           "task04": HERE / "snapshots" / "1fps_medium_t04_t06", "task06": HERE / "snapshots" / "1fps_medium_t04_t06"}
RUN = {"task01": "R1", "task02": "R1", "task03": "R1", "task04": "R2", "task06": "R2"}
OUT = HERE / "task_only" / DAY
SHEET = HERE / "reports" / "manual_counts.csv"
TASK_KEYS = ("task_text", "task_family", "action", "object_categories")
# One task for every episode of a folder (overrides the per-episode model answer). task06: built from the majority of the
# 27 R2 answers that named an LED (family 'sort' 18 of 27, action 'sort LED into plastic container' most frequent).
CANONICAL = {
    # task04: confirmed by the data owner (2026-11-24): the cycle is inserting the hex key into its holder. Wording from
    # the R2 'insert' answers (5 of 9 episodes: 01, 02, 06, 07, 08).
    "task04": {"task_text": "Insert a hex key into the hex key holder.",
               "task_family": "insert", "action": "insert hex key into holder",
               "object_categories": ["hex key", "hex key holder"]},
    "task06": {"task_text": "Pick an LED from the table and place it into a plastic container.",
               "task_family": "sort", "action": "sort LED into plastic container",
               "object_categories": ["LED", "plastic container"]},
}


def main():
    counts = {}
    if SHEET.exists():
        for r in csv.DictReader(open(SHEET)):
            v = (r.get("n_repetitions_manual") or "").strip()
            counts[(r["task"], r["episode"])] = int(v) if v else None
    rows, n_files, n_counted = [], 0, 0
    for task, src in sorted(SOURCES.items()):
        for f in sorted(src.glob(f"{task}/episode_*/*_vlm_result.json")):
            r = json.loads(f.read_text())
            episode = f.parent.name
            t = (r.get("response") or {}).get("task") or {}
            n = counts.get((task, episode))
            out = {"task": dict(CANONICAL[task]) if task in CANONICAL else {k: t.get(k) for k in TASK_KEYS},
                   "n_repetitions": n}
            d = OUT / task / episode
            d.mkdir(parents=True, exist_ok=True)
            (d / f.name).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
            n_files += 1
            n_counted += n is not None
            rows.append({"task": task, "episode": episode, "n_repetitions_manual": "" if n is None else n, "notes": "",
                         "task_text": out["task"]["task_text"], "action": out["task"]["action"],
                         "task_source_run": "canonical" if task in CANONICAL else RUN[task], "video": r.get("video")})
    if not SHEET.exists():
        with open(SHEET, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"counting sheet -> {SHEET}")
    print(f"{n_files} task-only files ({n_counted} with a manual count) -> {OUT}")


if __name__ == "__main__":
    main()
