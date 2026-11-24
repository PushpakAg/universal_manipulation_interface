#!/usr/bin/env python3
"""Run the repetition (cycle count) prompts on trimmed delivery MCAPs or head-camera MP4s.

All settings come from vlm_run/configs/config.json (prompt set, step grid, models, prices, batch, checks);
command-line options override them. For each input: sample the SAME timeline at frames.fps for every view (MCAP:
head camera2, left wrist camera1, right wrist camera0; MP4: head only, or head+left+right with --wrists), send the
labelled images with the final_prompts set to each model in default_models, and store ONE file per model and episode:
<results_dir>/<experiment>/<model key>/<episode>/vlm_result.json (--debug also keeps frames/, step_table.json,
raw_response.json). Gemini runs through Google's native API with media_resolution from the config, as a Batch API
job when use_batch is true (half price); DeepSeek runs through OpenRouter. API keys come from the environment or
the config's env_files and are never written to any output.

    python vlm_run/run_vlm_repetitions.py data/newmp4/episode_000007_head.mp4 --dry-run   # + exact Gemini input cost
    python vlm_run/run_vlm_repetitions.py data/newmp4/episode_000007_head.mp4
    python vlm_run/run_vlm_repetitions.py data/trimmed/episode_000001.mcap --model gemini-3.8-flash --no-batch

Experiments (folder under results_dir): '' trimmed MCAPs, experiment_2 head MP4s, experiment_3 head+left+right MP4s
(--wrists; <ep>_left.mp4 and <ep>_right.mp4 are found next to the head file), experiment_4 the chatgpt prompt set.
MCAP and MP4 inputs may not be mixed in one call. A Gemini batch can be resumed with --batch-name batches/<id>.
"""
import argparse
import base64
import bisect
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import av
import cv2

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CONFIG_PATH = HERE / "configs" / "config.json"
CFG = json.loads(CONFIG_PATH.read_text())
PROMPT_SETS = {k: REPO / v for k, v in CFG["prompt"]["sets"].items()}
PROMPTS = PROMPT_SETS[CFG["prompt"]["set"]]  # set from --prompts in main()
CHATGPT_PROMPTS = PROMPT_SETS["chatgpt"]  # comparison set (--prompts chatgpt): three MP4 views, own step numbering
PROMPT_FILES = {k: CFG["prompt"][k] for k in ("system_prompt", "episode_template", "output_contract")}
CHECKS = CFG["checks"]

# topic -> (camera id, view name); roles from the MCAP metadata: camera0 right wrist, camera1 left wrist, camera2 head
TOPICS = {t: (t.split("/")[2], v) for t, v in CFG["input"]["camera_roles"].items()}
VIEW_ORDER = CFG["input"]["view_order"]


def load_env_key(name):
    """Environment first (unless env_override), then the config's env_files. Name match is case-insensitive and
    tolerates spaces around '='."""
    if os.environ.get(name) and not CFG.get("env_override"):
        return os.environ[name]
    for env in CFG.get("env_files", []):
        env = REPO / env
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k.strip().upper() == name.upper() and v.strip():
                return v.strip().strip("'\"")
    return os.environ.get(name)


def model_cfgs(names):
    """model key -> request config from config.json models. The OpenAI-style fields (sampling, reasoning_body) are
    what call() sends to OpenRouter; Gemini uses the native API (to_gemini_request)."""
    out = {}
    for n in names:
        if n not in CFG["models"]:
            sys.exit(f"unknown model {n!r}: config.json has {sorted(CFG['models'])}")
        m = dict(CFG["models"][n])
        m["sampling"] = {"temperature": m.get("temperature", 0.0), "max_tokens": m.get("max_output_tokens", 12288)}
        m["reasoning"] = bool(m.get("reasoning_effort"))
        m["reasoning_body"] = {"reasoning": {"effort": m["reasoning_effort"]}} if m["reasoning"] else {}
        out[n] = m
    return out


def cost_usd(m, input_tokens, output_tokens, batch):
    p = m.get("batch_price_per_mtok" if batch else "price_per_mtok") or [0, 0]
    return round(((input_tokens or 0) * p[0] + (output_tokens or 0) * p[1]) / 1e6, 5)


def ts_ns(t):
    return int(t["sec"]) * 1_000_000_000 + int(t["nsec"])


def iter_video(path):
    from mcap.reader import make_reader
    with open(path, "rb") as f:
        r = make_reader(f)
        for _, ch, msg in r.iter_messages(topics=list(TOPICS)):
            cam, view = TOPICS[ch.topic]
            yield view, cam, json.loads(msg.data.decode())


def read_meta(path):
    from mcap.reader import make_reader
    with open(path, "rb") as f:
        for m in make_reader(f).iter_metadata():
            if m.name == "recording":
                return dict(m.metadata)
    return {}


def nearest(ts, target):
    i = bisect.bisect_left(ts, target)
    c = [j for j in (i - 1, i) if 0 <= j < len(ts)]
    return min(c, key=lambda j: abs(ts[j] - target))


def sample(path, fps, max_side, quality):
    """Same 5 fps timeline for the three views, from the latest first frame to the earliest last frame.
    Pass 1 reads only timestamps; pass 2 decodes in order (H.265 needs it) and keeps just the chosen frames."""
    ts = {v: [] for v in VIEW_ORDER}
    for view, _, p in iter_video(path):
        ts[view].append(ts_ns(p["timestamp"]))
    for v in VIEW_ORDER:
        if not ts[v]:
            raise RuntimeError(f"no frames for {v}")
        if ts[v] != sorted(ts[v]):
            raise RuntimeError(f"{v}: timestamps not monotonic")
    t0 = max(x[0] for x in ts.values())
    t1 = min(x[-1] for x in ts.values())
    dt = int(1e9 / fps)
    targets = []
    k = 0
    while t0 + k * dt <= t1:
        targets.append(t0 + k * dt)
        k += 1
    want = {v: {} for v in VIEW_ORDER}  # frame index -> [step numbers]
    for k, tg in enumerate(targets):
        for v in VIEW_ORDER:
            want[v].setdefault(nearest(ts[v], tg), []).append(k)
    jpegs = {v: {} for v in VIEW_ORDER}
    decoders, count = {}, {v: -1 for v in VIEW_ORDER}
    for view, cam, p in iter_video(path):
        fmt = p["format"].lower()
        if view not in decoders:
            decoders[view] = av.CodecContext.create({"h265": "hevc"}.get(fmt, fmt), "r")
        frames = decoders[view].decode(av.Packet(base64.b64decode(p["data"])))
        if len(frames) != 1:
            raise RuntimeError(f"{view}: expected 1 decoded frame per message, got {len(frames)}")
        count[view] += 1
        j = count[view]
        if j not in want[view]:
            continue
        img = frames[0].to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        sc = max_side / max(h, w)
        if sc < 1:
            img = cv2.resize(img, (round(w * sc), round(h * sc)), interpolation=cv2.INTER_AREA)
        jpegs[view][j] = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
    steps = []
    for k, tg in enumerate(targets):
        row = {"step": k + 1, "t_s": round(k / fps, 3), "images": {}}
        for v in VIEW_ORDER:
            j = nearest(ts[v], tg)
            row["images"][v] = {"jpeg": jpegs[v][j], "frame_index": j, "skew_ms": round((ts[v][j] - tg) / 1e6, 2)}
        steps.append(row)
    return steps


def read_meta_mp4(path):
    """Metadata of a plain video, shaped like the MCAP recording metadata used by build_messages."""
    with av.open(str(path)) as c:
        st = c.streams.video[0]
        fps = float(st.average_rate or st.guessed_rate or 0)
        n = st.frames or 0
        if not n and st.duration and st.time_base:
            n = round(float(st.duration * st.time_base) * fps)
    return {"video_fps": fps or 59.94, "episode_length": n, "robot_type": ""}


def sample_mp4(path, fps, max_side, quality, view="head"):
    """Head-camera MP4: one view on a fixed fps timeline starting at the first frame (same step structure as
    sample(), one view). Pass 1 reads packet presentation times only; pass 2 decodes in order and keeps just the
    frames nearest to the targets."""
    with av.open(str(path)) as c:
        st = c.streams.video[0]
        ts = sorted(float(p.pts * st.time_base) for p in c.demux(st) if p.pts is not None)
    if not ts:
        raise RuntimeError(f"no frames in {path}")
    targets, k = [], 0
    while ts[0] + k / fps <= ts[-1] + 1e-9:
        targets.append(ts[0] + k / fps)
        k += 1
    want = {}
    for k, tg in enumerate(targets):
        want.setdefault(nearest(ts, tg), []).append(k)
    jpegs, j = {}, -1
    with av.open(str(path)) as c:
        for fr in c.decode(c.streams.video[0]):
            j += 1
            if j not in want:
                continue
            img = fr.to_ndarray(format="bgr24")
            h, w = img.shape[:2]
            sc = max_side / max(h, w)
            if sc < 1:
                img = cv2.resize(img, (round(w * sc), round(h * sc)), interpolation=cv2.INTER_AREA)
            jpegs[j] = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()
    return [{"step": k + 1, "t_s": round(k / fps, 3),
             "images": {view: {"jpeg": jpegs[nearest(ts, tg)], "frame_index": nearest(ts, tg),
                               "skew_ms": round((ts[nearest(ts, tg)] - tg) * 1e3, 2)}}}
            for k, tg in enumerate(targets)]


def sample_mp4_three(head, fps, max_side, quality):
    """Head MP4 plus its _left and _right siblings: one step table, three views (same timeline for all)."""
    sib = {"head": head, "wrist_left": head.with_name(head.name.replace("_head", "_left")),
           "wrist_right": head.with_name(head.name.replace("_head", "_right"))}
    for v, f in sib.items():
        if not f.exists() or (v != "head" and f == head):
            sys.exit(f"{v} video not found next to the head file: {f}")
    per = {v: sample_mp4(f, fps, max_side, quality, view=v) for v, f in sib.items()}
    n = {v: len(x) for v, x in per.items()}
    if len(set(n.values())) != 1:
        sys.exit(f"the three videos give different step counts {n}: they must cover the same span")
    steps = []
    for k in range(n["head"]):
        steps.append({"step": k + 1, "t_s": per["head"][k]["t_s"],
                      "images": {v: per[v][k]["images"][v] for v in VIEW_ORDER}})
    return steps


def build_messages_chatgpt(episode_id, steps, videos, fps):
    """Messages for the chatgpt_prompts set, used as written: system_prompt.json as the system turn; the episode
    template filled with the sampled keyframes (frame ids, timestamps, video files) plus the output contract as the
    user turn, then the images in the order of the frame list. These prompts have the model build its OWN global
    action-step sequence, so start_step/end_step are NOT frame/step numbers of the table sent here."""
    system_p = json.loads((CHATGPT_PROMPTS / "system_prompt.json").read_text())
    tmpl = json.loads((CHATGPT_PROMPTS / "episode_template.json").read_text())["episode"]
    contract = json.loads((CHATGPT_PROMPTS / "output_contract.json").read_text())
    key = {"head": "head", "left": "wrist_left", "right": "wrist_right"}
    ep = dict(tmpl, episode_id=episode_id)
    ep["synchronization"] = dict(tmpl["synchronization"], camera_time_offsets_seconds={"head": 0.0, "left": 0.0, "right": 0.0},
                                 synchronization_notes="The three videos start and end together and carry the same frame times; "
                                                       "frames with the same timestamp show the same instant. Keyframes are sampled "
                                                       f"every {1 / fps:.2f} s.")
    streams = {}
    for cam, view in key.items():
        st = dict(tmpl["camera_streams"][cam], video_file=videos[cam].name)
        st["frames"] = [{"frame_id": f"{cam}_{s['step']:06d}", "timestamp_seconds": s["t_s"], "image": "<IMAGE_INPUT>"}
                        for s in steps]
        streams[cam] = st
    ep["camera_streams"] = streams
    content = [{"type": "text", "text": json.dumps({"episode": ep, "output_contract": contract}, ensure_ascii=False)}]
    for s in steps:
        for cam, view in key.items():
            b64 = base64.b64encode(s["images"][view]["jpeg"]).decode()
            content.append({"type": "text", "text": f"{cam}_{s['step']:06d} | camera {cam} | timestamp_seconds = {s['t_s']:.2f}"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    return [{"role": "system", "content": json.dumps(system_p, ensure_ascii=False)},
            {"role": "user", "content": content}], contract


def build_messages(episode_id, meta, steps, fps, given_task):
    system_p = json.loads((PROMPTS / PROMPT_FILES["system_prompt"]).read_text())
    tmpl = json.loads((PROMPTS / PROMPT_FILES["episode_template"]).read_text())
    contract = json.loads((PROMPTS / PROMPT_FILES["output_contract"]).read_text())
    vfps = float(meta.get("video_fps", 59.94))
    ep_len = int(meta.get("episode_length", 0))
    n = len(steps)
    views = [v for v in VIEW_ORDER if v in steps[0]["images"]]  # all three for MCAP, head only for a head MP4
    prompt = {
        "version": tmpl["version"],
        "episode_id": episode_id,
        "context": {"rig": meta.get("robot_type") or "UMI handheld rig",
                    "duration_s": round(ep_len / vfps, 2) if ep_len else None,
                    "step_interval_s": round(1 / fps, 3), "n_steps": n, "given_task": given_task},
        "steps": [{"step": s["step"], **{v: f"f{s['step']:03d}_{v}" for v in views}} for s in steps],
        "image_order": [o for o in tmpl["fields"]["image_order"] if o.split(" ")[0] in views],
        "output_contract": contract,
    }
    content = [{"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]
    for s in steps:
        for v in views:
            label = CFG["frames"]["label_format"].format(step=s["step"], view=v, t_s=s["t_s"])
            b64 = base64.b64encode(s["images"][v]["jpeg"]).decode()
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    return [{"role": "system", "content": json.dumps(system_p, ensure_ascii=False)},
            {"role": "user", "content": content}], contract


def call(cfg, key, messages, timeout, provider=None, max_tokens=None):
    s = cfg.get("sampling", {})
    body = {"model": cfg["model"], "messages": messages,
            "temperature": s.get("temperature", 0.0), "max_tokens": max_tokens or s.get("max_tokens", 12288),
            "response_format": {"type": "json_object"}}
    body.update(cfg.get("reasoning_body", {}) if cfg.get("reasoning") else cfg.get("no_reasoning_body", {}))
    # The benchmark config pins DeepInfra, which serves this model text-only: images need another provider.
    if provider:
        body["provider"] = {"order": [provider], "allow_fallbacks": False}
    req = urllib.request.Request(cfg["base_url"].rstrip("/") + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    last = None
    for attempt in range(int(cfg.get("max_retries", 3))):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:500].decode(errors='replace')}"
            if e.code not in (408, 429, 500, 502, 503, 504):
                break
        except Exception as e:  # network
            last = repr(e)
        time.sleep(2 ** attempt)
    raise RuntimeError(last)


# ---- Gemini native API: generateContent (live) or the Batch API (half price, minutes to 24 h) ----
GEMINI_NATIVE = CFG["models"].get("gemini-3.8-flash", {}).get("base_url", "https://generativelanguage.googleapis.com/v1beta")


def gemini_http(method, url, key, body=None, timeout=600):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:800].decode(errors='replace')}")


def to_gemini_request(messages, media_resolution, max_tokens):
    """OpenAI-style messages (system string + user parts) -> native GenerateContentRequest, same content and order."""
    system = next(m["content"] for m in messages if m["role"] == "system")
    parts = []
    for p in next(m["content"] for m in messages if m["role"] == "user"):
        if p["type"] == "text":
            parts.append({"text": p["text"]})
        else:
            head, b64 = p["image_url"]["url"].split(",", 1)
            parts.append({"inlineData": {"mimeType": head[5:].split(";")[0], "data": b64}})
    return {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json",
                                 "mediaResolution": f"MEDIA_RESOLUTION_{media_resolution.upper()}",
                                 "maxOutputTokens": max_tokens}}


def gemini_count_tokens(model, key, request):
    body = {"generateContentRequest": dict(request, model=f"models/{model}")}
    return gemini_http("POST", f"{GEMINI_NATIVE}/models/{model}:countTokens", key, body).get("totalTokens")


def gemini_generate(model, key, request, timeout):
    return gemini_http("POST", f"{GEMINI_NATIVE}/models/{model}:generateContent", key, request, timeout)


def gemini_text_usage(g):
    """GenerateContentResponse -> (answer text without thought parts, finish reason, usageMetadata)."""
    cand = (g.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
    return text, cand.get("finishReason"), g.get("usageMetadata") or {}


def gemini_batch(model, key, requests, display_name, resume=None, poll_s=30):
    """requests: {key: GenerateContentRequest}. One inline batch (< 20 MB). Returns {key: response or {'error': ...}}."""
    if resume:
        name = resume
    else:
        body = {"batch": {"displayName": display_name, "inputConfig": {"requests": {"requests": [
            {"request": r, "metadata": {"key": k}} for k, r in requests.items()]}}}}
        name = gemini_http("POST", f"{GEMINI_NATIVE}/models/{model}:batchGenerateContent", key, body)["name"]
    print(f"  batch {name} submitted (resume with --batch-name {name})", flush=True)
    done = {"BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED", "BATCH_STATE_EXPIRED",
            "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
    t0 = time.time()
    while True:
        op = gemini_http("GET", f"{GEMINI_NATIVE}/{name}", key)
        state = (op.get("metadata") or {}).get("state") or op.get("state")
        if state in done or op.get("done"):
            break
        print(f"  {state} after {time.time() - t0:.0f} s", flush=True)
        time.sleep(poll_s)
    print(f"  batch finished: {state} after {time.time() - t0:.0f} s", flush=True)
    if op.get("error"):
        raise RuntimeError(f"batch {name}: {op['error']}")
    # inlined responses: response.inlinedResponses.inlinedResponses (REST) or metadata.output.inlinedResponses...
    found = []
    for root in (op.get("response") or {}, (op.get("metadata") or {}).get("output") or {}, op.get("dest") or {}):
        x = root.get("inlinedResponses")
        x = x.get("inlinedResponses") if isinstance(x, dict) else x
        if x:
            found = x
            break
    if not found:
        raise RuntimeError(f"batch {name} ended in {state} with no inlined responses: {json.dumps(op)[:800]}")
    keys = list(requests)
    return {(r.get("metadata") or {}).get("key") or keys[i]: r for i, r in enumerate(found)}, name


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def check(resp, n_steps, table=None, objects=True, grippers=False):
    """Code checks from the output contract (flags only, the model count is never edited).
    table is the step table (step -> t_s); with it, the 3 to 30 s duration check runs too.
    grippers (final_prompts): each repetition names its gripper, and two ranges may overlap only when one is
    'left' and the other 'right' (two objects handled independently at the same time)."""
    flags = []
    reps = resp.get("repetitions", [])
    if resp.get("n_repetitions") != len(reps):
        flags.append("n_repetitions != len(repetitions)")
    if [r.get("index") for r in reps] != list(range(1, len(reps) + 1)):
        flags.append("repetition indices are not 1, 2, 3 ... without gaps")
    reasoning = str(resp.get("counting_reasoning", "")).strip()
    if not reasoning:
        flags.append("counting_reasoning missing")
    else:
        n_sent = len([s for s in re.split(r"(?<=[.!?])\s+", reasoning) if s.strip()])
        lo, hi = CHECKS["reasoning_sentences"]
        if not lo <= n_sent <= hi:
            flags.append(f"counting_reasoning has {n_sent} sentences (contract: {lo} to {hi})")
    action = (resp.get("task") or {}).get("action")
    lo, hi = CHECKS["action_words"]
    if isinstance(action, str) and not lo <= len(action.split()) <= hi:
        flags.append(f"task.action has {len(action.split())} words (contract: {lo} to {hi})")
    done = []  # (start, end, gripper) of the valid repetitions so far
    for r in reps:
        a, b = r.get("start_step", 0), r.get("end_step", 0)
        g = r.get("gripper")
        if grippers and g not in ("left", "right", "both"):
            flags.append(f"repetition {r.get('index')}: gripper missing or not left/right/both ({g!r})")
        ok = (isinstance(a, int) and isinstance(b, int) and 1 <= a <= b and (n_steps is None or b <= n_steps)
              and (not done or a >= done[-1][0]))
        if not ok:
            flags.append(f"repetition {r.get('index')}: bad range or out of order")
            continue
        for pa, pb, pg in done:
            if a <= pb and not (grippers and {g, pg} == set(CHECKS["overlap_allowed_for"])):
                flags.append(f"repetition {r.get('index')}: overlaps an earlier repetition"
                             + (" (allowed only for left vs right gripper)" if grippers else ""))
                break
        done.append((a, b, g))
        oc = r.get("object_confidence")
        if not objects:
            pass
        elif not isinstance(oc, (int, float)) or not 0 <= oc <= 1:
            flags.append(f"repetition {r.get('index')}: object_confidence missing or outside 0..1")
        elif oc < CHECKS["low_object_confidence"]:
            flags.append(f"repetition {r.get('index')}: low object confidence ({oc})")
        if table:
            dur = table[b - 1]["t_s"] - table[a - 1]["t_s"]
            lo, hi = CHECKS["repetition_seconds"]
            if not lo <= dur <= hi:
                flags.append(f"repetition {r.get('index')}: duration {dur:.1f} s outside {lo} to {hi} s")
    if len(reps) < CHECKS["min_repetitions"]:
        flags.append(f"PRD R2: fewer than {CHECKS['min_repetitions']} repetitions")
    return flags


def prompt_versions(cg):
    if cg:  # no version field in these files: short content hash
        import hashlib
        return {p.stem: "sha1:" + hashlib.sha1(p.read_bytes()).hexdigest()[:10] for p in sorted(CHATGPT_PROMPTS.glob("*.json"))}
    return {p.stem: json.loads(p.read_text())["version"] for p in sorted(PROMPTS.glob("*.json"))}


def log_experiment(root, name, cfg, a, ep, video, resp, flags):  # one entry per (model, episode)
    """experiment.json in the experiment folder: settings once, one line per episode (replaced on a rerun)."""
    f = root / "experiment.json"
    log = json.loads(f.read_text()) if f.exists() else {}
    log.update({
        "experiment": "experiment_4" if a.prompts == "chatgpt" else ("experiment_3" if a.wrists else "experiment_2"),
        "description": ("Repetition count from the head, left and right MP4s with the vlm_run/chatgpt_prompts set; "
                        "start_step/end_step are the model's own action steps, not frame steps."
                        if a.prompts == "chatgpt" else
                        "Repetition count from the head, left and right MP4s of one episode (same timeline)."
                        if a.wrists else "Repetition count from the head camera MP4 only (no wrist views)."),
        "views": ["head", "wrist_left", "wrist_right"] if a.wrists else ["head"], "fps": a.fps, "max_side": a.max_side,
        "prompt_versions": prompt_versions(a.prompts == "chatgpt")})
    eps = {(e["model"], e["episode_id"]): e for e in log.get("episodes", [])}
    eps[(cfg["model"], ep)] = {"model": cfg["model"], "episode_id": ep, "video": str(video), "n_repetitions": resp.get("n_repetitions") if resp else None,
               "segments": [[r.get("start_step"), r.get("end_step")] for r in resp.get("repetitions", [])] if resp else None,
               "code_flags": flags, "result": f"{name}/{ep}/vlm_result.json"}
    log["episodes"] = [eps[k] for k in sorted(eps)]
    f.write_text(json.dumps(log, indent=1, ensure_ascii=False))


def main():
    fr = CFG["frames"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mcaps", nargs="*", type=Path,
                    help=f"trimmed MCAPs or head-camera MP4s (default: input.mp4_glob {CFG['input']['mp4_glob']})")
    ap.add_argument("--out", type=Path, default=None, help=f"default <results_dir>/<experiment> ({CFG['results_dir']})")
    ap.add_argument("--fps", type=float, default=fr["fps"])
    ap.add_argument("--max-side", type=int, default=fr["long_side_px"], help="longest image side sent to the model (px)")
    ap.add_argument("--jpeg-quality", type=int, default=fr["jpeg_quality"])
    ap.add_argument("--given-task", default=None, help="task text of the delivery order, if any")
    ap.add_argument("--dry-run", action="store_true",
                    help="write frames and step table, print request size and the exact Gemini input cost (countTokens, "
                         "free); no model call")
    ap.add_argument("--provider", default=None, help="pin one OpenRouter provider (default: the model's openrouter_provider)")
    ap.add_argument("--max-tokens", type=int, default=None, help="reasoning + answer (default: the model's max_output_tokens)")
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--prompts", choices=sorted(PROMPT_SETS), default=CFG["prompt"]["set"],
                    help="final (config default): vlm_run/final_prompts; mcap: the earlier set; chatgpt: "
                         "vlm_run/chatgpt_prompts as written (needs --wrists; experiment 4; the model's own steps, "
                         "no step->time mapping)")
    ap.add_argument("--wrists", action="store_true",
                    help="with a head MP4: also use <ep>_left.mp4 and <ep>_right.mp4 next to it (experiment 3)")
    ap.add_argument("--model", action="append", choices=sorted(CFG["models"]), default=None,
                    help=f"repeatable (default: {', '.join(CFG['default_models'])}). "
                         "Results go to <out>/<model>/<episode>/vlm_result.json")
    ap.add_argument("--batch", action=argparse.BooleanOptionalAction, default=None,
                    help="Gemini: Batch API (half price) or live generateContent (default: the model's use_batch)")
    ap.add_argument("--media-resolution", choices=["low", "medium", "high"], default=None,
                    help="Gemini image token budget, about 280 / 560 / 1120 per image (default: the model's media_resolution)")
    ap.add_argument("--batch-name", default=None, help="resume waiting on this Gemini batch (batches/...)")
    ap.add_argument("--debug", action="store_true",
                    help="also write frames/, step_table.json and raw_response.json next to vlm_result.json")
    a = ap.parse_args()

    if not a.mcaps:
        a.mcaps = sorted(REPO.glob(CFG["input"]["mp4_glob"]))
        if not a.mcaps:
            sys.exit(f"no input given and nothing matches {CFG['input']['mp4_glob']}")
    mp4 = [m.suffix.lower() == ".mp4" for m in a.mcaps]
    if any(mp4) and not all(mp4):
        sys.exit("do not mix MCAP and MP4 inputs in one call")
    mp4 = all(mp4)
    cg = a.prompts == "chatgpt"
    if a.out is None:
        a.out = REPO / CFG["results_dir"] / (
            ("experiment_4" if cg else "experiment_3" if a.wrists else "experiment_2") if mp4 else "")
    global PROMPTS
    PROMPTS = PROMPT_SETS[a.prompts]
    if cg and not (mp4 and a.wrists):
        sys.exit("--prompts chatgpt needs head MP4 input with --wrists")
    if a.wrists and not mp4:
        sys.exit("--wrists applies to MP4 input")

    cfgs = model_cfgs(a.model or CFG["default_models"])
    for m in cfgs.values():
        if a.batch is not None:
            m["use_batch"] = a.batch and m["provider"] == "gemini"
        if a.media_resolution:
            m["media_resolution"] = a.media_resolution
        if a.max_tokens:
            m["max_output_tokens"] = m["sampling"]["max_tokens"] = a.max_tokens
    if cg and any(m["provider"] == "gemini" for m in cfgs.values()):
        sys.exit("--prompts chatgpt runs through OpenRouter models only")
    keys = {}
    for name, cfg in cfgs.items():
        if a.dry_run and cfg["provider"] != "gemini":
            continue  # a dry run still calls Gemini countTokens (free) for the cost estimate
        keys[name] = load_env_key(cfg["api_key_env"])
        if not keys[name] and not a.dry_run:
            sys.exit(f"{cfg['api_key_env']} not set in the environment or in {CFG['env_files']}")
    pending = {}  # model key -> episodes for that model's Gemini batch, sent after sampling every input

    for mcap in a.mcaps:
        if mp4:
            meta = read_meta_mp4(mcap)
            ep = mcap.stem[:-len("_head")] if mcap.stem.endswith("_head") else mcap.stem
            steps = (sample_mp4_three if a.wrists else sample_mp4)(mcap, a.fps, a.max_side, a.jpeg_quality)
        else:
            meta = read_meta(mcap)
            ep = f"episode_{int(meta.get('episode_index', 0)):06d}" if meta.get("episode_index") else mcap.stem
            steps = sample(mcap, a.fps, a.max_side, a.jpeg_quality)
        views = [v for v in VIEW_ORDER if v in steps[0]["images"]]
        if cg:
            h = mcap
            videos = {"head": h, "left": h.with_name(h.name.replace("_head", "_left")),
                      "right": h.with_name(h.name.replace("_head", "_right"))}
            messages, _ = build_messages_chatgpt(ep, steps, videos, a.fps)
        else:
            messages, _ = build_messages(ep, meta, steps, a.fps, a.given_task)
        size_mb = len(json.dumps(messages)) / 1e6
        print(f"{ep}: {len(steps)} steps x {len(views)} view(s) = {len(steps)*len(views)} images, request {size_mb:.1f} MB")
        table = [{"step": s["step"], "t_s": s["t_s"],
                  "frame_index": {v: s["images"][v]["frame_index"] for v in views},
                  "skew_ms": {v: s["images"][v]["skew_ms"] for v in views}} for s in steps]
        for name, cfg in cfgs.items():
            out = a.out / name / ep
            out.mkdir(parents=True, exist_ok=True)
            if a.debug or a.dry_run:  # what the model saw: frames + step -> time/frame table
                (out / "frames").mkdir(exist_ok=True)
                for s in steps:
                    for v in views:
                        (out / "frames" / f"f{s['step']:03d}_{v}.jpg").write_bytes(s["images"][v]["jpeg"])
                (out / "step_table.json").write_text(json.dumps(table, indent=1))
            job = dict(name=name, cfg=cfg, ep=ep, mcap=mcap, views=views, steps=steps, table=table, out=out)
            timeout = a.timeout or cfg.get("timeout_s", 360) * 2
            if cfg["provider"] == "gemini":
                job["request"] = req = to_gemini_request(messages, cfg["media_resolution"], cfg["max_output_tokens"])
                n_img = len(steps) * len(views)
                tok, how = None, "countTokens"
                if keys.get(name):
                    try:
                        tok = gemini_count_tokens(cfg["model"], keys[name], req)
                    except RuntimeError as e:
                        print(f"  [{name}] countTokens failed: {e}")
                if not tok:
                    tok, how = n_img * {"low": 280, "medium": 560, "high": 1120}[cfg["media_resolution"]] + 9000, "estimate"
                print(f"  [{name}] {cfg['media_resolution']} resolution, {'batch' if cfg['use_batch'] else 'live'}: "
                      f"input {tok} tokens ({how}) = ${cost_usd(cfg, tok, 0, cfg['use_batch']):.4f}", flush=True)
                if a.dry_run:
                    continue
                if cfg["use_batch"]:
                    pending.setdefault(name, []).append(job)
                    continue
                t = time.time()
                try:
                    g = gemini_generate(cfg["model"], keys[name], req, timeout)
                except RuntimeError as e:
                    print(f"  [{name}] request failed: {e}")
                    continue
                if a.debug:
                    (out / "raw_response.json").write_text(json.dumps(g, indent=1))
                text, fin, um = gemini_text_usage(g)
                finish(a, job, text, fin, gemini_usage(cfg, um, False), round(time.time() - t, 1), cg, mp4,
                       {"mode": "gemini live", "media_resolution": cfg["media_resolution"]})
                continue
            if a.dry_run:
                continue
            t = time.time()
            try:
                raw = call(cfg, keys[name], messages, timeout, a.provider or cfg.get("openrouter_provider"),
                           cfg["max_output_tokens"])
            except RuntimeError as e:
                print(f"  [{name}] request failed: {e}")
                continue
            if a.debug:
                (out / "raw_response.json").write_text(json.dumps(raw, indent=1))
            choice = (raw.get("choices") or [{}])[0]
            finish(a, job, (choice.get("message") or {}).get("content") or "", choice.get("finish_reason"),
                   raw.get("usage"), round(time.time() - t, 1), cg, mp4,
                   {"mode": "openrouter live", "reasoning_effort": cfg.get("reasoning_effort")})

    for name, jobs in pending.items():
        cfg = jobs[0]["cfg"]
        size_mb = len(json.dumps([j["request"] for j in jobs])) / 1e6
        if size_mb > cfg.get("inline_limit_mb", 19.5):
            sys.exit(f"[{name}] batch request is {size_mb:.1f} MB, over the inline limit "
                     f"({cfg.get('inline_limit_mb', 19.5)} MB): run fewer episodes per call")
        t = time.time()
        print(f"[{name}] batch: {len(jobs)} episode(s), {size_mb:.1f} MB, media resolution {cfg['media_resolution']}",
              flush=True)
        results, batch_name = gemini_batch(cfg["model"], keys[name], {j["ep"]: j["request"] for j in jobs},
                                           f"umi-repetitions-{time.strftime('%Y%m%d-%H%M%S')}", a.batch_name,
                                           CFG["batch"].get("poll_seconds", 30))
        total = 0.0
        for j in jobs:
            r = results.get(j["ep"]) or {"error": "no response for this episode in the batch"}
            if a.debug:
                (j["out"] / "raw_response.json").write_text(json.dumps(r, indent=1))
            text, fin, um = gemini_text_usage(r.get("response") or {})
            usage = gemini_usage(cfg, um, True)
            total += usage["cost_usd"]
            extra = {"mode": "gemini batch", "batch_name": batch_name, "media_resolution": cfg["media_resolution"]}
            if r.get("error"):
                extra["error"] = r["error"]
            finish(a, j, text, fin, usage, round(time.time() - t, 1), cg, mp4, extra)
        print(f"[{name}] batch total: ${total:.4f} ({len(jobs)} episode(s))")


def gemini_usage(cfg, um, batch):
    out_tok = (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0)
    return dict(um, cost_usd=cost_usd(cfg, um.get("promptTokenCount"), out_tok, batch),
                price_per_mtok=cfg["batch_price_per_mtok" if batch else "price_per_mtok"])


def finish(a, job, text, finish_reason, usage, elapsed, cg, mp4, extra=None):
    """Parse, check and map steps to times, then write the one result file <out>/vlm_result.json."""
    name, cfg, ep, steps, table, out = job["name"], job["cfg"], job["ep"], job["steps"], job["table"], job["out"]
    try:
        resp = parse_json(text)
        flags = check(resp, None, None, objects=False) if cg else check(resp, len(steps), table, grippers=a.prompts == "final" and CHECKS["require_gripper"])
        if cg:
            flags.append("steps are the model's own action steps (chatgpt prompts), not frame steps: no time mapping")
    except Exception as e:
        resp, flags = None, [f"unparseable response: {e!r}"]
    # step -> time mapping done here, never by the model
    if resp and not cg:
        for r in resp.get("repetitions", []):
            for k_in, k_out in (("start_step", "start_t_s"), ("end_step", "end_t_s")):
                st = r.get(k_in)
                if isinstance(st, int) and 1 <= st <= len(table):
                    r[k_out] = table[st - 1]["t_s"]
    result = {
        "episode_id": ep, ("video" if mp4 else "mcap"): str(job["mcap"]), "views": job["views"], "model": cfg["model"],
        "fps": a.fps, "n_steps": len(steps), **(extra or {}),
        "prompt_versions": prompt_versions(cg),
        "usage": usage, "elapsed_s": elapsed,
        "response": resp, "code_flags": flags}
    if resp is None:  # unparseable: keep what came back, in the same single file
        result["finish_reason"] = finish_reason
        result["raw_content"] = text
    (out / "vlm_result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    if mp4:
        log_experiment(a.out, name, cfg, a, ep, job["mcap"], resp, flags)
    print(f"  [{name}] -> {out/'vlm_result.json'} | cycles: {resp.get('n_repetitions') if resp else '?'} | flags: {flags}")


if __name__ == "__main__":
    main()
