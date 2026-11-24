#!/usr/bin/env python3
"""Manual counting sheet (reports/manual_counts.csv): one row per episode of every station, date and task, with the
VLM answer next to the empty columns a person fills in (n_repetitions_manual, notes).

Rows come from the S3 head-video inventory (reports/s3_head_video_by_episode.csv, written by s3_video_inventory.py),
or from a fresh S3 listing with --from-s3. The VLM columns come from the local results of run_s3_vlm.py
(<results_dir>/<task path>/<episode>/<name>_vlm_result.json). Run it again after every batch run: the VLM columns are
refreshed, the manual columns (n_repetitions_manual, notes) are always kept. Rows of the earlier sheet that used a bare
task name (task01, station2/2026-11-22 only) are matched by their video and keep their manual values.

    python scripts/make_manual_counts.py              # inventory + local results -> reports/manual_counts.csv
    python scripts/make_manual_counts.py --from-s3    # list S3 instead of reading the inventory
"""
import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # project root vlm_scripts_reports/ (scripts live in scripts/)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts (run_s3_vlm)
SHEET = HERE / "reports" / "manual_counts.csv"
INVENTORY = HERE / "reports" / "s3_head_video_by_episode.csv"
MANUAL = ("n_repetitions_manual", "notes")
COLUMNS = ["task", "task_folder", "episode", "duration_s", "n_repetitions_manual", "notes",
           "n_repetitions_vlm", "n_repetitions_confidence", "canonical_task", "canonical_task_confidence",
           "task_text", "action", "task_confidence", "code_flags", "prompt_version", "video"]


def task_path(uri, root):
    """s3://.../industrial_data_mp4/station1/2026-11-21/task01/episode_000000/x_head.mp4
    -> (station1/2026-11-21/task01, task01, episode_000000), the same split as run_s3_vlm.list_episodes."""
    import run_s3_vlm as D
    parts = uri[len(root):].split("/")
    i = next((j for j, p in enumerate(parts[:-1]) if D.TASK_DIR.match(p)), 0)
    return "/".join(parts[: i + 1]), parts[i], "__".join(parts[i + 1:-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "s3_run.json")
    ap.add_argument("--from-s3", action="store_true", help="list S3 (config source) instead of reading the inventory")
    a = ap.parse_args()
    import run_s3_vlm as D
    cfg = json.loads(a.config.read_text())
    root = cfg["source"].rstrip("/") + "/"
    results = D.here_path(cfg["results_dir"])
    suffix, head = cfg.get("s3_result_suffix", "_vlm_result.json"), cfg.get("head_suffix", "_head.mp4")

    if a.from_s3:
        D.load_env(HERE / ".env")
        bucket, prefix = D.split_s3(root)
        eps = D.list_episodes(D.s3_client(cfg.get("region")), bucket, prefix, head)
        videos = {e["s3_uri"]: None for e in eps}
    else:
        videos = {r["s3_uri"]: r.get("duration_s") for r in csv.DictReader(open(INVENTORY)) if r.get("s3_uri")}

    old = {}  # video -> manual values of the earlier sheet
    if SHEET.exists():
        for r in csv.DictReader(open(SHEET)):
            if any((r.get(k) or "").strip() for k in MANUAL):
                old[r.get("video")] = {k: r.get(k, "") for k in MANUAL}

    rows, n_vlm = [], 0
    for uri, dur in videos.items():
        task, folder, episode = task_path(uri, root)
        row = {"task": task, "task_folder": folder, "episode": episode, "duration_s": dur or "", "video": uri,
               **{k: "" for k in MANUAL}, **old.get(uri, {})}
        name = uri.rsplit("/", 1)[-1]
        f = results / task / episode / ((name[: -len(head)] if name.endswith(head) else name) + suffix)
        if f.exists():
            r = json.loads(f.read_text())
            resp = r.get("response") or {}
            ct, t = resp.get("canonical_task") or {}, resp.get("task") or {}
            row.update({"n_repetitions_vlm": resp.get("n_repetitions"),
                        "n_repetitions_confidence": resp.get("n_repetitions_confidence"),
                        "canonical_task": ct.get("task_text"), "canonical_task_confidence": ct.get("confidence"),
                        "task_text": t.get("task_text"), "action": t.get("action"), "task_confidence": t.get("confidence"),
                        "code_flags": " | ".join(r.get("code_flags") or []),
                        "prompt_version": (r.get("prompt_versions") or {}).get("repetition_system")})
            n_vlm += resp.get("n_repetitions") is not None
        rows.append(row)
    rows.sort(key=lambda r: (r["task"], r["episode"]))
    lost = set(old) - set(videos)
    if lost:
        sys.exit(f"{len(lost)} episode(s) with manual values are not in the episode list (e.g. {sorted(lost)[0]}); "
                 f"sheet left unchanged")
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with open(SHEET, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} episodes in {len({r['task'] for r in rows})} tasks, {n_vlm} with a VLM count, "
          f"{len(old)} with manual values kept -> {SHEET}")


if __name__ == "__main__":
    main()
