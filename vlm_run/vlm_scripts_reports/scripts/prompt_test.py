#!/usr/bin/env python3
"""Old prompts vs v1.1 prompts (small objects, follow the UMI grippers), on images and on video, in ONE Gemini batch.

Conditions (each a prompt set x input; --repeats for the v1.1 sets to see run-to-run variation):
  img_old   final_prompts            sampled JPEGs, --img-fps, media resolution --img-res
  img_v11   final_prompts_v1.1       same images
  vid_old   final_video_prompts      the head MP4 via the Files API, videoMetadata.fps = --vid-fps, --vid-res
  vid_v11   final_video_prompts_v1.1 same video
Generation settings as the S3 runs (temperature 0, JSON, max_output_tokens and thinking level from configs/s3_run.json).
Everything stays local: video_test/prompt_test/<task>/<episode>/<condition>_r<k>.json and summary.csv. Nothing goes to S3.
"""
import argparse
import csv
import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # project root vlm_scripts_reports/ (scripts live in scripts/)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts (run_s3_vlm)
import run_s3_vlm as D  # noqa: E402
import video_token_test as VT  # noqa: E402

R = D.R
REPO = HERE.parent
OUT = HERE / "video_test" / "prompt_test"
SETS = {"img_old": REPO / "prompts" / "final_prompts", "img_v11": REPO / "prompts" / "final_prompts_v1.1",
        "vid_old": REPO / "prompts" / "final_video_prompts", "vid_v11": REPO / "prompts" / "final_video_prompts_v1.1"}


def existing_video_file(key, ep_id):
    """A Files API video uploaded by video_token_test.py for this episode, if still ACTIVE (files live 48 h)."""
    for f in sorted((HERE / "video_test" / ep_id).glob("*.json")):
        name = json.loads(f.read_text()).get("video_file")
        if name:
            try:
                info = D.http("GET", f"{D.GEMINI}/{name}", key)
                if info.get("state") == "ACTIVE":
                    return info
            except RuntimeError:
                pass
    return None


def main():
    D.load_env(HERE / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "s3_run.json")
    ap.add_argument("--episodes", nargs="+", required=True)
    ap.add_argument("--img-fps", type=float, default=3.0)
    ap.add_argument("--img-res", default="low")
    ap.add_argument("--vid-fps", type=float, default=3.0)
    ap.add_argument("--vid-res", default="high")
    ap.add_argument("--repeats", type=int, default=2, help="runs of each v1.1 condition (old prompts run once)")
    ap.add_argument("--collect", help="batch name to collect instead of submitting")
    a = ap.parse_args()
    cfg_run = json.loads(a.config.read_text())
    model = cfg_run["model"]
    mcfg = R.CFG["models"][model]
    key = R.load_env_key(mcfg["api_key_env"])
    max_tokens = cfg_run.get("max_output_tokens") or mcfg.get("max_output_tokens")
    thinking = cfg_run.get("thinking_level")
    OUT.mkdir(parents=True, exist_ok=True)
    meta_f = OUT / "requests_meta.json"

    if not a.collect:
        bucket, prefix = D.split_s3(cfg_run["source"])
        s3 = D.s3_client(cfg_run.get("region"))
        eps = {f"{e['task']}/{e['episode']}": e for e in D.list_episodes(s3, bucket, prefix, cfg_run.get("head_suffix", "_head.mp4"))}
        lines, meta = [], {}
        for ep_id in a.episodes:
            e = eps[ep_id]
            with tempfile.TemporaryDirectory() as td:
                mp4 = Path(td) / "v.mp4"
                s3.download_file(bucket, e["key"], str(mp4))
                dur = VT.video_duration(mp4)
                vf = existing_video_file(key, ep_id) or VT.upload_video(key, mp4, ep_id.replace("/", "_"))
                steps = R.sample_mp4(mp4, a.img_fps, R.CFG["frames"]["long_side_px"], R.CFG["frames"]["jpeg_quality"])
                vmeta = R.read_meta_mp4(mp4)
            table = [{"step": s["step"], "t_s": s["t_s"]} for s in steps]
            print(f"{ep_id}: {dur:.1f} s, {len(steps)} image steps, video {vf['name']}", flush=True)
            for cond in ("img_old", "img_v11", "vid_old", "vid_v11"):
                reps = 1 if cond.endswith("old") else a.repeats
                if cond.startswith("img"):
                    R.PROMPTS = SETS[cond]
                    messages, _ = R.build_messages(e["episode"], vmeta, steps, a.img_fps, None)
                    req = R.to_gemini_request(messages, a.img_res, max_tokens)
                    if thinking:
                        req["generationConfig"]["thinkingConfig"] = {"thinkingLevel": thinking}
                    n_steps, tab = len(steps), table
                else:
                    VT.VPROMPTS = SETS[cond]
                    req, vsteps = VT.build_request(e["episode"], dur, a.vid_fps, vf["uri"], None, a.vid_res, max_tokens, thinking)
                    n_steps, tab = len(vsteps), vsteps
                for k in range(1, reps + 1):
                    rk = f"{ep_id}|{cond}|r{k}"
                    lines.append(json.dumps({"key": rk, "request": req}))
                    meta[rk] = {"n_steps": n_steps, "table": tab,
                                "fps": a.img_fps if cond.startswith("img") else a.vid_fps,
                                "res": a.img_res if cond.startswith("img") else a.vid_res,
                                "prompts": {p.stem: json.loads(p.read_text())["version"] for p in sorted(SETS[cond].glob("*.json"))}}
        jl = OUT / "batch_input.jsonl"
        jl.write_text("\n".join(lines) + "\n")
        print(f"{len(lines)} requests, {jl.stat().st_size / 1e6:.0f} MB", flush=True)
        file_name = D.upload_file(key, jl, "prompt_test")
        name = D.submit(key, model, file_name, "prompt_test")
        jl.unlink()
        meta_f.write_text(json.dumps({"batch": name, "requests": meta}))
        print(f"submitted {name}", flush=True)
    m = json.loads(meta_f.read_text())
    name = a.collect or m["batch"]
    op, state = D.wait(key, name, 30)
    if state != "BATCH_STATE_SUCCEEDED":
        sys.exit(f"batch {state}")
    out = D.download_results(key, D.responses_file(op), OUT / "responses.jsonl")
    rows = []
    for rk, line in sorted(out.items()):
        ep_id, cond, rep = rk.split("|")
        info = m["requests"][rk]
        text, fin, um = R.gemini_text_usage(line.get("response") or {})
        usage = R.gemini_usage(mcfg, um, True)
        try:
            resp = R.parse_json(text)
            flags = R.check(resp, info["n_steps"], info["table"], grippers=True)
        except Exception as ex:
            resp, flags = None, [f"unparseable: {ex}"]
        rec = {"episode": ep_id, "condition": cond, "repeat": rep, "fps": info["fps"], "media_resolution": info["res"],
               "thinking_level": thinking, "prompt_versions": info["prompts"], "n_steps": info["n_steps"],
               "finish_reason": fin, "usage": usage, "code_flags": flags, "response": resp, "batch_name": name,
               "error": (line.get("error") if isinstance(line, dict) else None)}
        d = OUT / ep_id
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{cond}_{rep}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        reps = (resp or {}).get("repetitions") or []
        t = {s["step"]: s["t_s"] for s in info["table"]}
        rows.append({"episode": ep_id, "condition": cond, "repeat": rep, "n_repetitions": (resp or {}).get("n_repetitions"),
                     "action": ((resp or {}).get("task") or {}).get("action"),
                     "objects": "; ".join(((resp or {}).get("task") or {}).get("object_categories") or []),
                     "grippers": "".join((r.get("gripper") or "?")[0] for r in reps),
                     "cycles_s": " ".join(f"{t.get(r.get('start_step'), 0):.0f}-{t.get(r.get('end_step'), 0):.0f}" for r in reps),
                     "prompt_tokens": um.get("promptTokenCount"),
                     "output_tokens": (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0),
                     "batch_cost_usd": usage["cost_usd"], "n_flags": len(flags), "finish_reason": fin})
    with open(OUT / "summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} results, ${sum(r['batch_cost_usd'] for r in rows):.4f} batch -> {OUT / 'summary.csv'}")


if __name__ == "__main__":
    main()
