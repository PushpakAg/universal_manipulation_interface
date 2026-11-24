#!/usr/bin/env python3
"""Video-input test for the repetition VLM (vlm_run/final_video_prompts).

Instead of sampled JPEGs, the head MP4 itself is uploaded to the Gemini Files API and referenced in the request
(fileData + videoMetadata.fps). Prompt content, output format and generation parameters are the same as the image
runs (temperature 0, JSON, maxOutputTokens, thinking level); only the input wording is adapted for video.

1. countTokens (free) for every test episode x media resolution x fps -> tokens per second of video.
2. live generateContent (paid) on --live episodes at each resolution at --live-fps -> real input/output tokens,
   cycle counts, code flags. Results stay local: video_test/<task>/<episode>/<res>_<fps>fps.json (no S3 upload).
3. cost of a full batch run over every episode in the S3 prefix (durations from S3 MP4 metadata via the cached
   step tables of the earlier runs), per resolution and fps.

    python video_token_test.py --episodes task06/episode_000038 task06/episode_000014 ... --live task06/episode_000038
"""
import argparse
import json
import math
import statistics
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_s3_vlm as D  # noqa: E402

R = D.R
VPROMPTS = HERE.parent / "final_video_prompts"
OUT = HERE / "video_test"


def upload_video(key, path, display_name):
    n = path.stat().st_size
    _, hdr = D.http("POST", f"{D.GEMINI_ROOT}/upload/v1beta/files", key, body={"file": {"display_name": display_name}},
                    headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                             "X-Goog-Upload-Header-Content-Length": str(n),
                             "X-Goog-Upload-Header-Content-Type": "video/mp4"}, raw=True)
    url = {k.lower(): v for k, v in hdr.items()}["x-goog-upload-url"]
    with open(path, "rb") as fh:
        f = D.http("POST", url, key, data=fh, timeout=3600,
                   headers={"Content-Length": str(n), "X-Goog-Upload-Offset": "0",
                            "X-Goog-Upload-Command": "upload, finalize"})["file"]
    while f.get("state") == "PROCESSING":
        time.sleep(5)
        f = D.http("GET", f"{D.GEMINI}/{f['name']}", key)
    if f.get("state") != "ACTIVE":
        raise RuntimeError(f"{display_name}: file state {f.get('state')}")
    return f


def video_duration(path):
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        if s.duration and s.time_base:
            return float(s.duration * s.time_base)
        return float(c.duration / 1e6)


def build_request(episode_id, duration, fps, file_uri, given_task, media_resolution, max_tokens, thinking_level):
    system_p = json.loads((VPROMPTS / "repetition_system.json").read_text())
    tmpl = json.loads((VPROMPTS / "repetition_episode_template.json").read_text())
    contract = json.loads((VPROMPTS / "repetition_output_contract.json").read_text())
    n = max(1, math.floor(duration * fps + 1e-6))
    steps = [{"step": i + 1, "t_s": round(i / fps, 2)} for i in range(n)]
    prompt = {
        "version": tmpl["version"],
        "episode_id": episode_id,
        "context": {"rig": "UMI handheld rig", "duration_s": round(duration, 2),
                    "step_interval_s": round(1 / fps, 3), "n_steps": n, "given_task": given_task},
        "steps": steps,
        "video_order": ["head (camera2)"],
        "output_contract": contract,
    }
    gc = {"temperature": 0.0, "responseMimeType": "application/json",
          "mediaResolution": f"MEDIA_RESOLUTION_{media_resolution.upper()}", "maxOutputTokens": max_tokens}
    if thinking_level:
        gc["thinkingConfig"] = {"thinkingLevel": thinking_level}
    req = {"systemInstruction": {"parts": [{"text": json.dumps(system_p, ensure_ascii=False)}]},
           "contents": [{"role": "user", "parts": [
               {"text": json.dumps(prompt, ensure_ascii=False)},
               {"fileData": {"fileUri": file_uri, "mimeType": "video/mp4"}, "videoMetadata": {"fps": fps}}]}],
           "generationConfig": gc}
    return req, steps


def count_tokens(key, model, req):
    body = {"generateContentRequest": dict(req, model=f"models/{model}")}
    return D.http("POST", f"{D.GEMINI}/models/{model}:countTokens", key, body=body)


def main():
    D.load_env(HERE / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "s3_run.json")
    ap.add_argument("--episodes", nargs="+", required=True, help="task/episode ids for countTokens")
    ap.add_argument("--live", nargs="*", default=[], help="task/episode ids for paid live calls")
    ap.add_argument("--resolutions", nargs="+", default=["low", "medium", "high"])
    ap.add_argument("--fps", nargs="+", type=float, default=[1, 3, 5, 10])
    ap.add_argument("--live-fps", type=float, default=10)
    a = ap.parse_args()
    cfg_run = json.loads(a.config.read_text())
    model = cfg_run["model"]
    mcfg = R.CFG["models"][model]
    key = R.load_env_key(mcfg["api_key_env"])
    max_tokens = cfg_run.get("max_output_tokens") or mcfg.get("max_output_tokens")
    thinking = cfg_run.get("thinking_level")
    bucket, prefix = D.split_s3(cfg_run["source"])
    s3 = D.s3_client(cfg_run.get("region"))
    eps = {f"{e['task']}/{e['episode']}": e for e in D.list_episodes(s3, bucket, prefix, cfg_run.get("head_suffix", "_head.mp4"))}
    OUT.mkdir(exist_ok=True)
    report = {"model": model, "prompts": {p.stem: json.loads(p.read_text())["version"] for p in sorted(VPROMPTS.glob("*.json"))},
              "thinking_level": thinking, "max_output_tokens": max_tokens, "count": [], "live": []}

    files = {}
    for ep_id in dict.fromkeys(a.episodes + a.live):
        e = eps[ep_id]
        with tempfile.TemporaryDirectory() as td:
            mp4 = Path(td) / "v.mp4"
            s3.download_file(bucket, e["key"], str(mp4))
            dur = video_duration(mp4)
            f = upload_video(key, mp4, ep_id.replace("/", "_"))
        files[ep_id] = (f, dur)
        print(f"uploaded {ep_id}: {e['size'] / 1e6:.0f} MB, {dur:.1f} s -> {f['name']}", flush=True)

    for ep_id in a.episodes:
        f, dur = files[ep_id]
        for fps in a.fps:
            for res in a.resolutions:
                req, steps = build_request(ep_id, dur, fps, f["uri"], None, res, max_tokens, thinking)
                ct = count_tokens(key, model, req)
                det = {d["modality"]: d["tokenCount"] for d in ct.get("promptTokensDetails", [])}
                row = {"episode": ep_id, "duration_s": round(dur, 2), "fps": fps, "resolution": res,
                       "total_tokens": ct.get("totalTokens"), "by_modality": det, "n_steps": len(steps)}
                report["count"].append(row)
                print(f"count {ep_id} {fps:>4} fps {res:6}: {ct.get('totalTokens'):>9,} tokens {det}", flush=True)

    for ep_id in a.live:
        f, dur = files[ep_id]
        for res in a.resolutions:
            req, steps = build_request(ep_id, dur, a.live_fps, f["uri"], None, res, max_tokens, thinking)
            t0 = time.time()
            g = R.gemini_generate(model, key, req, 1800)
            text, finish_reason, um = R.gemini_text_usage(g)
            usage = R.gemini_usage(mcfg, um, batch=False)
            usage["batch_cost_usd"] = R.cost_usd(mcfg, um.get("promptTokenCount"),
                                                 (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0), True)
            try:
                resp = R.parse_json(text)
                flags = R.check(resp, len(steps), steps, grippers=True)
            except Exception as ex:
                resp, flags = None, [f"unparseable: {ex}"]
            rec = {"episode": ep_id, "resolution": res, "fps": a.live_fps, "n_steps": len(steps), "finish_reason": finish_reason,
                   "elapsed_s": round(time.time() - t0, 1), "usage": usage, "code_flags": flags, "response": resp,
                   "video_file": f["name"], "prompt_versions": report["prompts"], "thinking_level": thinking}
            d = OUT / ep_id
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{res}_{a.live_fps:g}fps.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
            report["live"].append({k: rec[k] for k in ("episode", "resolution", "fps", "finish_reason", "elapsed_s")}
                                  | {"n_repetitions": (resp or {}).get("n_repetitions"), "prompt_tokens": um.get("promptTokenCount"),
                                     "output_tokens": (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0),
                                     "live_cost_usd": usage["cost_usd"], "batch_cost_usd": usage["batch_cost_usd"]})
            print(f"live {ep_id} {res:6} {a.live_fps:g} fps: n_repetitions {(resp or {}).get('n_repetitions')}, "
                  f"in {um.get('promptTokenCount'):,} out {report['live'][-1]['output_tokens']:,}, "
                  f"${usage['cost_usd']:.4f} live (${usage['batch_cost_usd']:.4f} batch), {finish_reason}", flush=True)

    # full-run extrapolation: tokens are linear in duration; fit per (fps, res) from the counted episodes
    work = D.here_path(cfg_run["work_dir"])
    total_s, n_eps = 0.0, 0
    for ep_id in eps:
        st = work / ep_id / "step_table.json"
        if st.exists():
            t = json.loads(st.read_text())
            total_s += t[-1]["t_s"] + (t[1]["t_s"] - t[0]["t_s"] if len(t) > 1 else 0)
            n_eps += 1
    out_tok = statistics.median([r["output_tokens"] for r in report["live"]]) if report["live"] else 8000
    p_in, p_out = mcfg["batch_price_per_mtok"]
    report["full_run"] = {"episodes": n_eps, "total_video_s": round(total_s, 1), "output_tokens_per_episode": out_tok, "rows": []}
    print(f"\nfull run: {n_eps} episodes, {total_s:.0f} s of head video; output {out_tok:,.0f} tokens/episode (median of live calls)")
    for fps in a.fps:
        for res in a.resolutions:
            rows = [r for r in report["count"] if r["fps"] == fps and r["resolution"] == res]
            per_s = sum(r["total_tokens"] for r in rows) / sum(r["duration_s"] for r in rows)
            tin = per_s * total_s
            c_in, c_out = tin * p_in / 1e6, n_eps * out_tok * p_out / 1e6
            report["full_run"]["rows"].append({"fps": fps, "resolution": res, "input_tokens_per_s": round(per_s, 1),
                                               "input_tokens": round(tin), "input_usd": round(c_in, 2),
                                               "output_usd": round(c_out, 2), "total_usd": round(c_in + c_out, 2)})
            print(f"  {fps:>4g} fps {res:6}: {per_s:7.0f} tok/s, input {tin / 1e6:6.2f} M = ${c_in:5.2f}, "
                  f"+ output ${c_out:4.2f} = ${c_in + c_out:5.2f} batch")
    (OUT / "report.json").write_text(json.dumps(report, indent=1))
    print(f"report -> {OUT / 'report.json'}")


if __name__ == "__main__":
    main()
