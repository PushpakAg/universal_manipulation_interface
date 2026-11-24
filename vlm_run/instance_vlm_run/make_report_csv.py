#!/usr/bin/env python3
"""Collect every VLM run made on station2/2026-11-22 into report CSVs (read-only: raw batch outputs and test JSONs).

    reports/vlm_runs_by_episode.csv   one row per (run, episode, repeat): settings, count, task, cycles, tokens, cost
    reports/vlm_runs_summary.csv      one row per run/condition: settings, episodes, cycle totals, zeros, cost
    reports/video_token_counts.csv    countTokens (free) for video input at each fps x media resolution

Sources: results/.../batches/*/{job.json,responses.jsonl} (image runs R1 to R3), video_test/<task>/<episode>/*.json
(R4 live video calls), video_test/prompt_test/<task>/<episode>/*.json (R5 prompt test), video_test/report.json.
"""
import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_s3_vlm as D  # noqa: E402

R = D.R
MCFG = R.CFG["models"]["gemini-3.8-flash"]
BATCHES = HERE / "results" / "station2" / "2026-11-22" / "batches"
VT = HERE / "video_test"
OUT = HERE / "reports"
DATE = "2026-11-24"
IMG_V10 = "final_prompts (umi-repetition-final-1.0)"

RUNS = {  # batch folder -> run id and description (image runs on the head MP4, Gemini batch API)
    "20261124-011950_01": ("R1", "images 3 fps low, default thinking: 2-episode pilot"),
    "20261124-014644_01": ("R1", "images 3 fps low, default thinking: all episodes"),
    "20261124-022201_01": ("R2", "images 1 fps medium, thinking medium: task04 + task06"),
    "20261124-053456_01": ("R3", "images 10 fps low, thinking medium: task04 + task06"),
    "20261124-053738_01": ("R3", "images 10 fps low, thinking medium: task04 + task06"),
    "20261124-053908_01": ("R3", "images 10 fps low, thinking medium: task04 + task06"),
    "20261124-054516_01": ("R3", "images 10 fps low, thinking medium: task04 + task06 (episode_000000 at 512 px, 125 MB request too large at 768 px)"),
}
FIELDS = ["run_id", "run_description", "date", "input", "prompt_set", "fps", "media_resolution", "long_side_px",
          "thinking_level", "max_output_tokens", "api_mode", "task", "episode", "repeat", "n_repetitions",
          "task_action", "task_text", "object_categories", "grippers", "cycle_times_s", "n_steps", "n_flags", "flags",
          "prompt_tokens", "output_tokens", "thinking_tokens", "cost_usd", "price_basis", "finish_reason", "batch_or_file"]


def resp_fields(resp, table_t):
    """table_t(step) -> seconds."""
    resp = resp or {}
    task = resp.get("task") or {}
    reps = resp.get("repetitions") or []
    return {"n_repetitions": resp.get("n_repetitions") if resp else None,
            "task_action": task.get("action"), "task_text": task.get("task_text"),
            "object_categories": "; ".join(task.get("object_categories") or []),
            "grippers": "".join((r.get("gripper") or "?")[0] for r in reps),
            "cycle_times_s": " ".join(f"{table_t(r.get('start_step', 1)):.1f}-{table_t(r.get('end_step', 1)):.1f}" for r in reps)}


def usage_fields(um, batch):
    out_tok = (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0)
    return {"prompt_tokens": um.get("promptTokenCount"), "output_tokens": out_tok,
            "thinking_tokens": um.get("thoughtsTokenCount"),
            "cost_usd": R.cost_usd(MCFG, um.get("promptTokenCount"), out_tok, batch),
            "price_basis": "batch $0.375/$1.875 per M" if batch else "live $0.75/$3.75 per M"}


def image_runs():
    rows = []
    for folder, (rid, desc) in RUNS.items():
        d = BATCHES / folder
        job = json.loads((d / "job.json").read_text())
        fps = float(job.get("fps") or 3.0)
        side = 512 if folder == "20261124-054516_01" else 768
        for line in (d / "responses.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            j = json.loads(line)
            task, episode = j["key"].split("/")
            text, fin, um = R.gemini_text_usage(j.get("response") or {})
            try:
                resp = R.parse_json(text)
            except Exception:
                resp = None
            n_steps = None
            flags = []
            if resp is not None:
                flags = R.check(resp, None, None, grippers=True)  # step table of R1/R2 was replaced: duration check skipped
            rows.append({"run_id": rid, "run_description": desc, "date": DATE, "input": "images (sampled JPEG frames)",
                         "prompt_set": IMG_V10, "fps": fps, "media_resolution": job.get("media_resolution"),
                         "long_side_px": side, "thinking_level": job.get("thinking_level") or "default (model)",
                         "max_output_tokens": job.get("max_output_tokens") or 32768, "api_mode": "batch",
                         "task": task, "episode": episode, "repeat": 1,
                         **resp_fields(resp, lambda s: (s - 1) / fps), "n_steps": n_steps,
                         "n_flags": len(flags), "flags": " | ".join(flags), **usage_fields(um, True),
                         "finish_reason": fin, "batch_or_file": job.get("batch_name")})
    return rows


def video_live_runs():
    rows = []
    for f in sorted(VT.glob("task*/episode_*/*_10fps.json")):
        j = json.loads(f.read_text())
        task, episode = j["episode"].split("/")
        fps = float(j["fps"])
        um = j["usage"]
        rows.append({"run_id": "R4", "run_description": "video 10 fps, low / medium / high, thinking medium: live test on 2 task06 episodes",
                     "date": DATE, "input": "video (head MP4 via Files API)",
                     "prompt_set": "final_video_prompts (" + j["prompt_versions"]["repetition_system"] + ")",
                     "fps": fps, "media_resolution": j["resolution"], "long_side_px": "original",
                     "thinking_level": j.get("thinking_level"), "max_output_tokens": 65536, "api_mode": "live",
                     "task": task, "episode": episode, "repeat": 1,
                     **resp_fields(j["response"], lambda s: (s - 1) / fps), "n_steps": j["n_steps"],
                     "n_flags": len(j["code_flags"]), "flags": " | ".join(j["code_flags"]), **usage_fields(um, False),
                     "finish_reason": j["finish_reason"], "batch_or_file": j["video_file"]})
    return rows


def prompt_test_runs():
    names = {"img_old": ("images (sampled JPEG frames)", IMG_V10),
             "img_v11": ("images (sampled JPEG frames)", "final_prompts_v1.1 (umi-repetition-final-1.1)"),
             "vid_old": ("video (head MP4 via Files API)", "final_video_prompts (umi-repetition-final-video-1.0)"),
             "vid_v11": ("video (head MP4 via Files API)", "final_video_prompts_v1.1 (umi-repetition-final-video-1.1)")}
    rows = []
    for f in sorted((VT / "prompt_test").glob("task*/episode_*/*.json")):
        j = json.loads(f.read_text())
        task, episode = j["episode"].split("/")
        fps = float(j["fps"])
        inp, ps = names[j["condition"]]
        um = j["usage"]
        rows.append({"run_id": "R5-" + j["condition"], "date": DATE,
                     "run_description": f"prompt test 3 fps, {j['condition']} ({'old prompts' if j['condition'].endswith('old') else 'v1.1: small objects, follow the UMI grippers'}), thinking medium",
                     "input": inp, "prompt_set": ps, "fps": fps, "media_resolution": j["media_resolution"],
                     "long_side_px": 768 if inp.startswith("images") else "original",
                     "thinking_level": j.get("thinking_level"), "max_output_tokens": 65536, "api_mode": "batch",
                     "task": task, "episode": episode, "repeat": int(j["repeat"].lstrip("r")),
                     **resp_fields(j["response"], lambda s: (s - 1) / fps), "n_steps": j["n_steps"],
                     "n_flags": len(j["code_flags"]), "flags": " | ".join(j["code_flags"]), **usage_fields(um, True),
                     "finish_reason": j["finish_reason"], "batch_or_file": j["batch_name"]})
    return rows


def main():
    OUT.mkdir(exist_ok=True)
    rows = image_runs() + video_live_runs() + prompt_test_runs()
    with open(OUT / "vlm_runs_by_episode.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    groups = {}
    for r in rows:
        groups.setdefault((r["run_id"], r["input"], r["prompt_set"], r["fps"], r["media_resolution"], r["thinking_level"],
                           r["api_mode"]), []).append(r)
    summ = []
    for (rid, inp, ps, fps, res, th, mode), rs in groups.items():
        for task in sorted({r["task"] for r in rs}) + ["ALL"]:
            sub = [r for r in rs if task in ("ALL", r["task"])]
            n = [r["n_repetitions"] for r in sub if isinstance(r["n_repetitions"], int)]
            summ.append({"run_id": rid, "run_description": sub[0]["run_description"].split(":")[0], "input": inp,
                         "prompt_set": ps, "fps": fps, "media_resolution": res, "thinking_level": th, "api_mode": mode,
                         "task": task, "results": len(sub), "parsed": len(n), "total_cycles": sum(n),
                         "median_cycles": statistics.median(n) if n else None, "zero_cycle_results": sum(x == 0 for x in n),
                         "below_3_cycles": sum(x < 3 for x in n), "max_output_tokens_used": max(r["output_tokens"] for r in sub),
                         "cost_usd": round(sum(r["cost_usd"] for r in sub), 4)})
    with open(OUT / "vlm_runs_summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)

    rep = json.loads((VT / "report.json").read_text())
    with open(OUT / "video_token_counts.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["episode", "duration_s", "fps", "media_resolution", "total_tokens", "video_tokens", "text_tokens",
                     "video_tokens_per_frame", "full_run_112_eps_input_tokens", "full_run_batch_input_usd",
                     "full_run_batch_total_usd_est"])
        full = {(x["fps"], x["resolution"]): x for x in rep["full_run"]["rows"]}
        for c in rep["count"]:
            v = c["by_modality"].get("VIDEO", 0)
            fr = full[(c["fps"], c["resolution"])]
            w.writerow([c["episode"], c["duration_s"], c["fps"], c["resolution"], c["total_tokens"], v,
                        c["by_modality"].get("TEXT", 0), round(v / max(1, c["n_steps"]), 1), fr["input_tokens"],
                        fr["input_usd"], fr["total_usd"]])
    total = sum(r["cost_usd"] for r in rows)
    print(f"{len(rows)} episode rows, {len(summ)} summary rows, total cost ${total:.2f} -> {OUT}")


if __name__ == "__main__":
    main()
