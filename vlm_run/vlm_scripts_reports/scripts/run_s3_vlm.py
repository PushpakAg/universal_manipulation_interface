#!/usr/bin/env python3
"""Repetition VLM on every head MP4 under an S3 prefix, as ONE Gemini Batch API job (low media resolution, 3 fps).

1. List <source>/<task>/<episode>/*_head.mp4 recursively (all tasks, all episodes).
2. Prepare each episode in parallel: download the head MP4, sample it on a fixed fps grid (configs/s3_run.json,
   default 3 fps), build the final_prompts request exactly as vlm_run/run_vlm_repetitions.py does, with
   Gemini media_resolution low. The request is cached in work_dir/<task>/<episode>/request.json.
3. Write all requests to one JSONL file, upload it with the Gemini Files API and submit one batch job
   (file input: up to 2 GB, so long episodes fit; split into several jobs only above max_batch_mb).
4. Wait for the job, download its results and write everything of an episode into ONE folder:

       results_dir/<task>/<episode>/<name>_vlm_result.json   response, flags, step -> time, usage, cost, batch name
       results_dir/<task>/<episode>/step_table.json   step -> t_s / frame index (what the model saw; copied from work_dir
                                                       when the result is written, so a dry run leaves results untouched)
       results_dir/<task>/<episode>/frames/           sampled JPEGs (--debug)
       results_dir/<task>/<episode>/raw_response.json batch line as returned (--debug)

   plus results_dir/summary.csv and results_dir/batches/<id>/ (job name, input key list) for resuming.
5. Upload each parsed result, under the SAME file name, into the S3 folder of its MP4:
       s3://.../<task>/<episode>/<name>_head.mp4  ->  s3://.../<task>/<episode>/<name>_vlm_result.json
   (config upload_results_to_s3 / s3_result_suffix; --no-upload keeps results local; failed episodes are not uploaded).

Episodes that already have a parsed result from the current prompt set are skipped (--force redoes them);
results of an earlier prompt version are redone and overwritten, locally and in S3.

    python scripts/run_s3_vlm.py --list                   # episodes in S3
    python scripts/run_s3_vlm.py --dry-run                # download + sample + build requests, print size and cost estimate
    python scripts/run_s3_vlm.py                          # the full run: one batch job
    python scripts/run_s3_vlm.py --task task01 --limit 2  # a subset
    python scripts/run_s3_vlm.py --resume                 # wait again for the last submitted job(s) and write results
    python scripts/run_s3_vlm.py --summary-only
    python scripts/run_s3_vlm.py --upload-only            # push existing parsed local results next to their MP4s
"""
import argparse
import concurrent.futures as cf
import csv
import json
import re
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # project root vlm_scripts_reports/ (scripts live in scripts/)
V2 = HERE.parent
sys.path.insert(0, str(V2))
import run_vlm_repetitions as R  # noqa: E402  (prompts, sampling, request building, checks: one implementation)

GEMINI = R.GEMINI_NATIVE  # https://generativelanguage.googleapis.com/v1beta
GEMINI_ROOT = GEMINI.rsplit("/", 1)[0]  # upload/ and download/ endpoints hang off the root
DONE_STATES = {"BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED", "BATCH_STATE_EXPIRED",
               "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}


def load_env(path):
    """KEY=value lines into os.environ, without overriding what the shell already set. Names are upper-cased."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        k, v = k.strip().upper(), v.strip().strip("'\"")
        if k and v and not os.environ.get(k):
            os.environ[k] = v


def here_path(p):
    p = Path(p)
    return p if p.is_absolute() else HERE / p


def split_s3(url):
    if not url.startswith("s3://"):
        sys.exit(f"not an s3:// url: {url}")
    bucket, _, prefix = url[5:].partition("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix


def s3_client(region):
    import boto3
    return boto3.Session(region_name=region or None).client("s3")


TASK_DIR = re.compile(r"^task\d+$", re.I)


def list_episodes(client, bucket, prefix, suffix):
    """All head MP4s under prefix, in either layout:
        <prefix>[<station>/[<date>/]]<taskNN>/<episode>/<name><suffix>
    task is the task's whole path below the prefix (e.g. station1/2026-11-21/task01, station1/task03, or task01 when
    the prefix already points into a station/date folder), so equal task names of different stations or dates stay
    separate everywhere (work dir, results, batch keys, --limit). task_folder is the task folder's own name (task01),
    which the prompt gets. The first folder named task<digits> is the task; deeper folders form the episode id."""
    eps = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            parts = o["Key"][len(prefix):].split("/")
            if not parts[-1].endswith(suffix):
                continue
            i = next((j for j, p in enumerate(parts[:-1]) if TASK_DIR.match(p)), 0 if len(parts) >= 3 else None)
            if i is None or len(parts) - i < 3:  # need <task>/<episode>/<file>
                continue
            eps.append({"task": "/".join(parts[: i + 1]), "task_folder": parts[i],
                        "episode": "__".join(parts[i + 1:-1]), "key": o["Key"], "size": o["Size"],
                        "s3_uri": f"s3://{bucket}/{o['Key']}"})
    return sorted(eps, key=lambda e: (e["task"], e["episode"]))


def task_matches(task, wanted):
    """--task filter: the full task path (station1/2026-11-21/task01), a path prefix (station1, station1/2026-11-21)
    or a bare task folder name (task01, any station or date)."""
    return any(task == w or task.startswith(w.rstrip("/") + "/") or task.rsplit("/", 1)[-1] == w for w in wanted)


def result_files(a):
    """Local result files of every episode: <results>/<task path>/<episode>/<name><s3_result_suffix>."""
    return sorted(f for f in a.results.rglob("*" + a.s3_result_suffix) if "batches" not in f.relative_to(a.results).parts)


def result_task(a, f):
    return "/".join(f.relative_to(a.results).parts[:-2])


def episode_dir(a, e):
    return a.results / e["task"] / e["episode"]


def result_name(a, video):
    """Same file name locally and in S3: <name>_head.mp4 -> <name>_vlm_result.json."""
    name = str(video).rsplit("/", 1)[-1]
    return (name[: -len(a.head_suffix)] if name.endswith(a.head_suffix) else name.rsplit(".", 1)[0]) + a.s3_result_suffix


def result_file(a, e):
    return episode_dir(a, e) / result_name(a, e["key"])


def migrate_legacy(a):
    """Rename results written as vlm_result.json by earlier versions to the S3 name (<name>_vlm_result.json)."""
    for f in sorted(a.results.glob("*/*/vlm_result.json")):
        video = json.loads(f.read_text()).get("video")
        new = f.parent / result_name(a, video) if video else None
        if new and not new.exists():
            f.rename(new)
            print(f"renamed {f.relative_to(a.results)} -> {new.name}")


def is_done(a, e):
    """Done = a parsed response made with the CURRENT prompt set (same versions of all three prompt files). A result
    from an earlier prompt version does not block the run: the episode is redone and its file overwritten."""
    f = result_file(a, e)
    try:
        r = json.loads(f.read_text())
    except Exception:
        return False
    return r.get("response") is not None and r.get("prompt_versions") == R.prompt_versions(False)


# ---------------------------------------------------------------- prepare (runs in worker processes)
def prepare(e, a_dict, bucket, region):
    """Download, sample, build the Gemini request. Returns a small dict; the request itself goes to disk."""
    a = argparse.Namespace(**a_dict)
    R.PROMPTS = R.PROMPT_SETS[a.prompts]  # worker processes re-import R: set the prompt set here too
    work = Path(a.work) / e["task"] / e["episode"]
    out = work  # step table and frames stay in work_dir until the result is written (a dry run never touches results)
    req_f = work / "request.json"
    sig = {"fps": a.fps, "max_side": a.max_side, "jpeg_quality": a.jpeg_quality,
           "media_resolution": a.media_resolution, "prompt_versions": R.prompt_versions(False)}
    if req_f.exists() and (work / "request_sig.json").exists() and \
            json.loads((work / "request_sig.json").read_text()) == sig and (out / "step_table.json").exists():
        return {**e, "request": str(req_f), "request_mb": req_f.stat().st_size / 1e6,
                "n_steps": len(json.loads((out / "step_table.json").read_text())), "cached": True}
    work.mkdir(parents=True, exist_ok=True)
    head = work / f"{e['episode']}_head.mp4"
    if not (head.exists() and head.stat().st_size == e["size"]):
        tmp = head.with_name(head.name + ".part")
        s3_client(region).download_file(bucket, e["key"], str(tmp))
        tmp.replace(head)
    meta = R.read_meta_mp4(head)
    steps = R.sample_mp4(head, a.fps, a.max_side, a.jpeg_quality)
    messages, _ = R.build_messages(e["episode"], meta, steps, a.fps, a.given_task, task_folder=e.get("task_folder") or e["task"].rsplit("/", 1)[-1])
    req = R.to_gemini_request(messages, a.media_resolution, a.max_output_tokens)
    req_f.write_text(json.dumps(req))
    (work / "request_sig.json").write_text(json.dumps(sig))
    table = [{"step": s["step"], "t_s": s["t_s"], "frame_index": {"head": s["images"]["head"]["frame_index"]},
              "skew_ms": {"head": s["images"]["head"]["skew_ms"]}} for s in steps]
    (out / "step_table.json").write_text(json.dumps(table, indent=1))
    if a.debug:
        fd = out / "frames"
        shutil.rmtree(fd, ignore_errors=True)
        fd.mkdir()
        for s in steps:
            (fd / f"f{s['step']:03d}_head.jpg").write_bytes(s["images"]["head"]["jpeg"])
    if not a.keep_videos:
        head.unlink(missing_ok=True)
    return {**e, "request": str(req_f), "request_mb": req_f.stat().st_size / 1e6, "n_steps": len(steps),
            "video_fps": meta.get("video_fps"), "cached": False}


# ---------------------------------------------------------------- video input (MP4 via the Gemini Files API)
def video_duration(path):
    """Seconds, from the container (no decoding)."""
    import av
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        if s.duration and s.time_base:
            return float(s.duration * s.time_base)
        return float(c.duration / 1e6)


def build_video_request(a, e, duration, file_uri):
    """Same prompt structure as the frame requests (system turn, episode prompt with output contract), but the head MP4
    is referenced as one fileData part sampled by Gemini at a.fps (videoMetadata.fps). Steps are the fixed grid
    t = (n - 1) / fps, so every answer step maps to a time exactly as with frames."""
    system_p = json.loads((R.PROMPTS / R.PROMPT_FILES["system_prompt"]).read_text())
    tmpl = json.loads((R.PROMPTS / R.PROMPT_FILES["episode_template"]).read_text())
    contract = json.loads((R.PROMPTS / R.PROMPT_FILES["output_contract"]).read_text())
    n = max(1, int(duration * a.fps + 1e-6))
    steps = [{"step": i + 1, "t_s": round(i / a.fps, 3)} for i in range(n)]
    prompt = {"version": tmpl["version"], "episode_id": e["episode"],
              "context": {"rig": "UMI handheld rig", "duration_s": round(duration, 2), "step_interval_s": round(1 / a.fps, 3),
                          "n_steps": n, "given_task": a.given_task},
              "steps": steps, "video_order": ["head (camera2)"], "output_contract": contract}
    if "task_folder" in tmpl["fields"]["context"]:
        prompt["context"]["task_folder"] = e.get("task_folder") or e["task"].rsplit("/", 1)[-1]
    req = {"systemInstruction": {"parts": [{"text": json.dumps(system_p, ensure_ascii=False)}]},
           "contents": [{"role": "user", "parts": [
               {"text": json.dumps(prompt, ensure_ascii=False)},
               {"fileData": {"fileUri": file_uri, "mimeType": "video/mp4"}, "videoMetadata": {"fps": a.fps}}]}],
           "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json",
                                "mediaResolution": f"MEDIA_RESOLUTION_{a.media_resolution.upper()}",
                                "maxOutputTokens": a.max_output_tokens}}
    return req, steps


def upload_video(key, path, display_name):
    """Upload one MP4 to the Files API and wait until it is ACTIVE (processed). Returns the file resource."""
    n = path.stat().st_size
    _, hdr = http("POST", f"{GEMINI_ROOT}/upload/v1beta/files", key, body={"file": {"display_name": display_name}},
                  headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                           "X-Goog-Upload-Header-Content-Length": str(n),
                           "X-Goog-Upload-Header-Content-Type": "video/mp4"}, raw=True)
    url = {k.lower(): v for k, v in hdr.items()}["x-goog-upload-url"]
    with open(path, "rb") as fh:
        f = http("POST", url, key, data=fh, timeout=3600,
                 headers={"Content-Length": str(n), "X-Goog-Upload-Offset": "0",
                          "X-Goog-Upload-Command": "upload, finalize"})["file"]
    t0 = time.time()
    while f.get("state") == "PROCESSING" and time.time() - t0 < 1800:
        time.sleep(5)
        f = http("GET", f"{GEMINI}/{f['name']}", key)
    if f.get("state") != "ACTIVE":
        raise RuntimeError(f"{display_name}: file state {f.get('state')}")
    return f


def delete_files(key, names):
    n = 0
    for name in names:
        try:
            http("DELETE", f"{GEMINI}/{name}", key)
            n += 1
        except Exception as ex:
            print(f"  could not delete {name}: {ex}")
    print(f"  deleted {n}/{len(names)} uploaded video(s) from the Files API", flush=True)


def prepare_video(e, a, bucket, region, key):
    """Download the head MP4, read its duration, upload it to the Files API, delete the local copy, write the request
    (with the file's URI) and the step table to work_dir. Runs in a thread (I/O bound, no decoding)."""
    work = Path(a.work) / e["task"] / e["episode"]
    work.mkdir(parents=True, exist_ok=True)
    head = work / f"{e['episode']}_head.mp4"
    if not (head.exists() and head.stat().st_size == e["size"]):
        tmp = head.with_name(head.name + ".part")
        s3_client(region).download_file(bucket, e["key"], str(tmp))
        tmp.replace(head)
    duration = video_duration(head)
    f = upload_video(key, head, f"{e['task']}/{e['episode']}".replace("/", "_"))
    if not a.keep_videos:
        head.unlink(missing_ok=True)
    req, steps = build_video_request(a, e, duration, f["uri"])
    req_f = work / "request.json"
    req_f.write_text(json.dumps(req))
    (work / "step_table.json").write_text(json.dumps(steps, indent=1))
    return {**e, "request": str(req_f), "request_mb": req_f.stat().st_size / 1e6, "n_steps": len(steps),
            "duration_s": round(duration, 2), "file_name": f["name"], "cached": False}


def video_groups(a, eps):
    """Job groups for video input: whole task folders of one station, packed up to video_job_gb of MP4 (a task is
    split only when it alone is larger)."""
    by_task = {}
    for e in sorted(eps, key=lambda e: (e["task"], e["episode"])):
        by_task.setdefault(e["task"], []).append(e)
    cap = a.video_job_gb * 1e9
    groups, cur, cur_b, cur_station = [], [], 0, None
    for task, es in by_task.items():
        station, task_b = task.split("/", 1)[0], sum(e["size"] for e in es)
        if cur and (station != cur_station or cur_b + task_b > cap):
            groups.append(cur)
            cur, cur_b = [], 0
        cur_station = station
        for e in es:
            if cur and cur_b + e["size"] > cap:
                groups.append(cur)
                cur, cur_b = [], 0
            cur.append(e)
            cur_b += e["size"]
    if cur:
        groups.append(cur)
    return groups


def finish_video_job(a, cfg, key, client, jd):
    """Collect one video job, retry its unparsed episodes (same uploaded files), then delete its files."""
    bad = collect(a, cfg, key, jd, client)
    bad = retry_failed(a, cfg, key, client, bad)
    job = json.loads((jd / "job.json").read_text())
    delete_files(key, [e["file_name"] for e in job["episodes"] if e.get("file_name")])
    return bad


def run_video(a, cfg, key, client, bucket, todo):
    """Rolling per-group pipeline: upload a group's MP4s, submit its batch; at most video_jobs_in_flight jobs (and
    their uploaded files) exist at once, so the Files API storage stays bounded and the local disk holds only the
    MP4s being uploaded. Returns the number of episodes without a parsed result."""
    groups = video_groups(a, todo)
    for gi, g in enumerate(groups, 1):
        print(f"[group {gi}/{len(groups)}] {len(g)} episodes, {sum(e['size'] for e in g) / 1e9:.1f} GB: "
              f"{', '.join(sorted({e['task'] for e in g}))}", flush=True)
    a_ns = argparse.Namespace(**{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()})
    inflight, bad = [], 0
    for gi, g in enumerate(groups, 1):
        while len(inflight) >= a.video_jobs_in_flight:
            bad += len(finish_video_job(a, cfg, key, client, inflight.pop(0)))
        ready, failed = [], 0
        with cf.ThreadPoolExecutor(max_workers=a.upload_workers) as ex:
            futs = {ex.submit(prepare_video, e, a_ns, bucket, a.region, key): e for e in g}
            for i, f in enumerate(cf.as_completed(futs), 1):
                e = futs[f]
                try:
                    r = f.result()
                    ready.append(r)
                    print(f"  [group {gi}: {i}/{len(g)}] {e['task']}/{e['episode']}: {r['duration_s']:.1f} s, "
                          f"{r['n_steps']} steps -> {r['file_name']}", flush=True)
                except Exception as err:
                    failed += 1
                    print(f"  [group {gi}: {i}/{len(g)}] {e['task']}/{e['episode']}: upload FAILED: {err!r}", flush=True)
        bad += failed
        if ready:
            inflight += submit_jobs(a, cfg, key, ready, a.thinking_level, tag=f"_g{gi:02d}")
    while inflight:
        bad += len(finish_video_job(a, cfg, key, client, inflight.pop(0)))
    return bad


# ---------------------------------------------------------------- Gemini Files API + file batch
def http(method, url, key, body=None, headers=None, data=None, timeout=600, raw=False):
    h = {"x-goog-api-key": key, **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, data=data, headers=h)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return (r.read(), dict(r.headers)) if raw else json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as ex:
            msg = f"HTTP {ex.code} {method} {url.split('?')[0]}: {ex.read()[:800].decode(errors='replace')}"
            if ex.code not in (429, 500, 502, 503, 504) or hasattr(data, "read"):
                raise RuntimeError(msg)
        except (urllib.error.URLError, TimeoutError) as ex:
            msg = repr(ex)
            if hasattr(data, "read"):
                raise RuntimeError(msg)
        time.sleep(2 ** attempt * 5)
    raise RuntimeError(msg)


def upload_file(key, path, display_name):
    n = path.stat().st_size
    _, hdr = http("POST", f"{GEMINI_ROOT}/upload/v1beta/files", key, body={"file": {"display_name": display_name}},
                  headers={"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                           "X-Goog-Upload-Header-Content-Length": str(n),
                           "X-Goog-Upload-Header-Content-Type": "application/jsonl"}, raw=True)
    url = {k.lower(): v for k, v in hdr.items()}["x-goog-upload-url"]
    with open(path, "rb") as fh:
        r = http("POST", url, key, data=fh, timeout=3600,
                 headers={"Content-Length": str(n), "X-Goog-Upload-Offset": "0",
                          "X-Goog-Upload-Command": "upload, finalize"})
    return r["file"]["name"]


def submit(key, model, file_name, display_name):
    body = {"batch": {"display_name": display_name, "input_config": {"file_name": file_name}}}
    return http("POST", f"{GEMINI}/models/{model}:batchGenerateContent", key, body=body)["name"]


def wait(key, name, poll_s):
    t0 = time.time()
    while True:
        op = http("GET", f"{GEMINI}/{name}", key)
        meta = op.get("metadata") or {}
        state = meta.get("state") or op.get("state")
        if state in DONE_STATES or op.get("done"):
            print(f"  {name}: {state} after {time.time() - t0:.0f} s", flush=True)
            return op, state
        print(f"  {name}: {state} after {time.time() - t0:.0f} s", flush=True)
        time.sleep(poll_s)


def responses_file(op):
    for root in (op.get("response") or {}, (op.get("metadata") or {}).get("output") or {}, op.get("dest") or {}):
        if root.get("responsesFile"):
            return root["responsesFile"]
    return None


def download_results(key, file_name, dest):
    data, _ = http("GET", f"{GEMINI_ROOT}/download/v1beta/{file_name}:download?alt=media", key, raw=True, timeout=3600)
    dest.write_bytes(data)
    out = {}
    for line in data.decode().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r.get("key")] = r
    return out


# ---------------------------------------------------------------- results
def write_result(a, cfg, e, line, batch_name):
    """One vlm_result.json in the episode folder (same fields as run_vlm_repetitions.finish)."""
    d = episode_dir(a, e)
    d.mkdir(parents=True, exist_ok=True)
    w = Path(a.work) / e["task"] / e["episode"]
    if (w / "step_table.json").exists():  # the table this request was built from, next to its result
        shutil.copyfile(w / "step_table.json", d / "step_table.json")
        if (w / "frames").is_dir():
            shutil.rmtree(d / "frames", ignore_errors=True)
            shutil.copytree(w / "frames", d / "frames")
    table = json.loads((d / "step_table.json").read_text())
    if a.debug:
        (d / "raw_response.json").write_text(json.dumps(line, indent=1))
    text, fin, um = R.gemini_text_usage((line or {}).get("response") or {})
    usage = R.gemini_usage(cfg, um, True)
    try:
        resp = R.parse_json(text)
        flags = R.check(resp, len(table), table, grippers=R.CHECKS["require_gripper"])
        for r in resp.get("repetitions", []):
            for k_in, k_out in (("start_step", "start_t_s"), ("end_step", "end_t_s")):
                st = r.get(k_in)
                if isinstance(st, int) and 1 <= st <= len(table):
                    r[k_out] = table[st - 1]["t_s"]
    except Exception as ex:
        resp, flags = None, [f"unparseable response: {ex!r}"]
    result = {"episode_id": e["episode"], "task": e["task"], "video": e["s3_uri"], "views": ["head"],
              "model": cfg["model"], "fps": a.fps, "n_steps": len(table), "mode": "gemini batch (file)",
              "input": getattr(a, "input", "frames"),
              "batch_name": batch_name, "media_resolution": a.media_resolution,
              "thinking_level": getattr(a, "job_thinking_level", None) or "model default",
              "max_output_tokens": getattr(a, "job_max_output_tokens", None) or a.max_output_tokens, "max_side": a.max_side,
              "prompt_versions": R.prompt_versions(False), "usage": usage, "response": resp, "code_flags": flags}
    if (line or {}).get("error") or line is None:
        result["error"] = (line or {}).get("error") or "no line for this episode in the batch output"
    if resp is None:
        result["finish_reason"] = fin
        result["raw_content"] = text
    f = result_file(a, e)
    f.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    return resp is not None, usage["cost_usd"], f


def s3_result_uri(video_uri, suffix, head_suffix):
    """s3://b/.../<task>/<episode>/<name>_head.mp4 -> s3://b/.../<task>/<episode>/<name><suffix> (same folder)."""
    base = video_uri[: -len(head_suffix)] if video_uri.endswith(head_suffix) else video_uri.rsplit(".", 1)[0]
    return base + suffix


def upload_result(client, a, result_file):
    """Copy a parsed vlm_result.json next to its MP4 in S3. Returns the S3 uri, or None when not uploaded."""
    r = json.loads(result_file.read_text())
    if r.get("response") is None or not str(r.get("video", "")).startswith("s3://"):
        return None
    uri = s3_result_uri(r["video"], a.s3_result_suffix, a.head_suffix)
    bucket, _, key = uri[5:].partition("/")
    client.upload_file(str(result_file), bucket, key, ExtraArgs={"ContentType": "application/json"})
    return uri


def upload_all(client, a, files):
    n = 0
    for f in files:
        try:
            uri = upload_result(client, a, f)
        except Exception as ex:
            print(f"  upload FAILED {f}: {ex}")
            continue
        if uri:
            n += 1
            print(f"  -> {uri}")
        else:
            print(f"  not uploaded (no parsed response): {f}")
    print(f"uploaded {n}/{len(files)} result(s) next to their MP4s")


def summarize(results, suffix="_vlm_result.json"):
    rows = []
    for f in sorted(f for f in results.rglob("*" + suffix) if "batches" not in f.relative_to(results).parts):
        r = json.loads(f.read_text())
        resp = r.get("response") or {}
        ct, t = resp.get("canonical_task") or {}, resp.get("task") or {}
        rows.append({"task": "/".join(f.relative_to(results).parts[:-2]), "episode": f.parts[-2], "model": r.get("model"),
                     "prompt_version": (r.get("prompt_versions") or {}).get("repetition_system"),
                     "canonical_task": ct.get("task_text"), "canonical_action": ct.get("action"),
                     "canonical_task_confidence": ct.get("confidence"),
                     "canonical_support": (r.get("canonical_task_consolidation") or {}).get("support"),
                     "canonical_needs_review": (r.get("canonical_task_consolidation") or {}).get("needs_review"),
                     "canonical_outlier": (r.get("canonical_task_consolidation") or {}).get("outlier"),
                     "task_text": t.get("task_text"), "action": t.get("action"), "task_confidence": t.get("confidence"),
                     "n_repetitions": resp.get("n_repetitions"),
                     "n_repetitions_confidence": resp.get("n_repetitions_confidence"),
                     "n_flags": len(r.get("code_flags") or []), "flags": " | ".join(r.get("code_flags") or []),
                     "n_steps": r.get("n_steps"), "fps": r.get("fps"), "cost_usd": (r.get("usage") or {}).get("cost_usd"),
                     "batch_name": r.get("batch_name"), "video": r.get("video")})
    results.mkdir(parents=True, exist_ok=True)
    out = results / "summary.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["task"])
        w.writeheader()
        w.writerows(rows)
    cost = sum(float(r["cost_usd"] or 0) for r in rows)
    print(f"summary: {len(rows)} episode(s), cost ${cost:.4f} -> {out}")


def collect(a, cfg, key, job_dir, client=None):
    """Wait for one submitted job (job_dir/job.json) and write its episodes' results."""
    job = json.loads((job_dir / "job.json").read_text())
    a.job_thinking_level = job.get("thinking_level")  # what this job was actually sent with
    a.job_max_output_tokens = job.get("max_output_tokens")
    op, state = wait(key, job["batch_name"], a.poll_seconds)
    if op.get("error"):
        print(f"  {job['batch_name']}: error {op['error']}")
    rf = responses_file(op)
    lines = download_results(key, rf, job_dir / "responses.jsonl") if rf else {}
    if not rf:
        print(f"  {job['batch_name']} ended in {state} without a responses file: {json.dumps(op)[:600]}")
    ok, cost, written, bad = 0, 0.0, [], []
    for e in job["episodes"]:
        line = lines.get(f"{e['task']}/{e['episode']}")
        good, c, f = write_result(a, cfg, e, line, job["batch_name"])
        ok += good
        cost += c
        written.append(f)
        if not good:
            fin = ((((line or {}).get("response") or {}).get("candidates") or [{}])[0]).get("finishReason")
            bad.append(dict(e, finish_reason=fin or "no response"))
            print(f"  NOT PARSED {e['task']}/{e['episode']}: finish reason {fin or 'no response'}")
    job.update(state=state, n_ok=ok, cost_usd=round(cost, 4), finished=time.strftime("%Y-%m-%d %H:%M:%S"))
    (job_dir / "job.json").write_text(json.dumps(job, indent=1))
    print(f"  {job['batch_name']}: {ok}/{len(job['episodes'])} parsed, ${cost:.4f}")
    # no upload here: results go to S3 only after consolidate_canonical() has given each task folder one canonical_task
    return bad


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


AGG_PROMPT = V2 / "prompts" / "canonical_aggregation" / "canonical_aggregation.json"


def _majority(props):
    """Fallback: exact-wording vote (case and punctuation ignored); ties: higher summed confidence."""
    votes = {}
    for ep, own in props:
        v = votes.setdefault(_norm(own["task_text"]), {"n": 0, "conf": 0.0, "best": None, "eps": []})
        c = float(own.get("confidence") or 0)
        v["n"] += 1
        v["conf"] += c
        v["eps"].append(ep)
        if v["best"] is None or c > float(v["best"].get("confidence") or 0):
            v["best"] = own
    win = max(votes.values(), key=lambda v: (v["n"], v["conf"]))
    chosen = {k: win["best"].get(k) for k in ("task_text", "task_family", "action", "object_categories")}
    return chosen, sorted(ep for ep, _ in props if ep not in set(win["eps"])), len(votes)


TASK_HINTS = Path(__file__).resolve().parents[1] / "task_data" / "task_hints.json"
_HINTS = None


def _task_hint(a, task):
    """Grounding hint for a task folder from task_data/task_hints.json (written by scripts/task_map.py): the operator's
    logged instruction(s) or a by-eye description; no task id. None when the file or the folder is missing or
    canonical_hints is off in the config."""
    global _HINTS
    if not getattr(a, "canonical_hints", True):
        return None
    if _HINTS is None:
        _HINTS = json.loads(TASK_HINTS.read_text()) if TASK_HINTS.exists() else {}
    h = _HINTS.get(task)
    return h if h and h.get("hint") else None


def _aggregate_llm(a, task, props, model, key, mcfg):
    """One text-only Gemini call for a task folder: every episode's proposal in, one canonical_task and the outlier
    episodes out (prompts/canonical_aggregation). Cached in <results>/canonical/<task>.json by an input hash, so a
    re-run with unchanged proposals costs nothing and gives the same answer."""
    import hashlib
    spec = json.loads(AGG_PROMPT.read_text())
    lines = [f"{ep} | {o.get('task_family')} | {o.get('action')} | {', '.join(o.get('object_categories') or [])} | {o.get('task_text')}"
             for ep, o in props]
    hint = _task_hint(a, task)
    user = (f"task_folder: {task.rsplit('/', 1)[-1]}\nn_episodes: {len(props)}\n"
            + (f"operator_hint ({hint['source']}): {' || '.join(hint['hint'])}\n" if hint else "") + "\n".join(lines))
    h = hashlib.sha1((spec["version"] + model + user).encode()).hexdigest()[:16]
    cache = a.results / "canonical" / (task.replace("/", "__") + ".json")
    if cache.exists():
        c = json.loads(cache.read_text())
        if c.get("input_hash") == h:
            return c["output"], c["usage"], spec["version"], True
    req = {"systemInstruction": {"parts": [{"text": spec["system"]}]},
           "contents": [{"role": "user", "parts": [
               {"text": json.dumps({k: spec[k] for k in ("instruction", "vocabulary", "schema", "input_format")}, ensure_ascii=False)},
               {"text": user}]}],
           "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json", "maxOutputTokens": 16384,
                                "thinkingConfig": {"thinkingLevel": "low"}}}
    g = R.gemini_generate(model, key, req, 600)
    text, fin, um = R.gemini_text_usage(g)
    out = R.parse_json(text)
    ct = out.get("canonical_task") or {}
    if not ct.get("task_text"):
        raise ValueError(f"no canonical_task.task_text (finish reason {fin})")
    usage = R.gemini_usage(mcfg, um, False)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"task": task, "input_hash": h, "prompt_version": spec["version"], "model": model,
                                 "input": user, "output": out, "usage": usage,
                                 "created": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1, ensure_ascii=False))
    return out, usage, spec["version"], False


def consolidate_canonical(a, tasks):
    """One canonical_task per task folder (station/[date/]taskNN). Every parsed current-prompt episode proposes one
    (kept in canonical_task_model; its own response.task is untouched). canonical_method 'llm' (default): one text-only
    Gemini call per folder reads all proposals and returns the folder's task plus the episodes that describe a
    different task (outliers); 'majority', or a failed call, falls back to the exact-wording vote.
    support = share of the folder's episodes that are not outliers; it is written as canonical_task.confidence (the
    episodes' self-reported confidence is about 0.95 everywhere and says nothing about agreement). needs_review when
    support < canonical_min_support or the folder has fewer than canonical_min_episodes episodes.
    Re-running is safe: proposals always come from canonical_task_model. Returns the result files of these tasks."""
    method = getattr(a, "canonical_method", "llm")
    model, key, mcfg = a.model_key, None, None
    if method == "llm":
        mcfg = R.model_cfgs([model])[model]
        key = R.load_env_key(mcfg["api_key_env"])
        if not key:
            print(f"  {mcfg['api_key_env']} not set: canonical_task by exact-wording vote")
            method = "majority"
    files_by_task = {}
    for f in result_files(a):
        t = result_task(a, f)
        if t in tasks:
            files_by_task.setdefault(t, []).append(f)
    all_files, n_review, cost = [], 0, 0.0
    for task, files in sorted(files_by_task.items()):
        all_files += files
        rs = {}
        for f in files:
            r = json.loads(f.read_text())
            resp = r.get("response")
            if resp is None or r.get("prompt_versions") != R.prompt_versions(False):
                continue
            own = r.get("canonical_task_model") or resp.get("canonical_task")
            if own and own.get("task_text"):
                rs[f] = (r, own)
        if not rs:
            continue
        props = sorted((r.get("episode_id") or f.parts[-2], own) for f, (r, own) in rs.items())
        eps = {ep for ep, _ in props}
        info = {"task": task, "n_episodes": len(props), "n_distinct_proposals": len({_norm(o["task_text"]) for _, o in props})}
        used = method
        if method == "llm":
            try:
                out, usage, ver, cached = _aggregate_llm(a, task, props, model, key, mcfg)
                chosen = {k: out["canonical_task"].get(k) for k in ("task_text", "task_family", "action", "object_categories")}
                outliers = sorted(set(out.get("outlier_episodes") or []) & eps)
                hint = _task_hint(a, task)
                info.update(method="llm aggregation of episode proposals" + (f" + operator hint ({hint['source']})" if hint else ""),
                            model=model, prompt_version=ver,
                            reason=out.get("reason"), cost_usd=usage.get("cost_usd"), cached=cached)
                cost += 0 if cached else float(usage.get("cost_usd") or 0)
            except Exception as ex:
                print(f"  canonical {task}: LLM aggregation failed ({ex!r}); exact-wording vote instead")
                used = "majority"
        if used == "majority":
            chosen, outliers, _ = _majority(props)
            info.update(method="majority of episode proposals (exact wording)")
        support = round((len(props) - len(outliers)) / len(props), 3)
        review = support < a.canonical_min_support or len(props) < a.canonical_min_episodes
        n_review += review
        chosen["confidence"] = support
        info.update(n_covered=len(props) - len(outliers), support=support, needs_review=review,
                    outlier_episodes=outliers, updated=time.strftime("%Y-%m-%d %H:%M:%S"))
        for f, (r, own) in rs.items():
            r["canonical_task_model"] = own
            r["response"]["canonical_task"] = dict(chosen)
            r["canonical_task_consolidation"] = dict(info, outlier=(r.get("episode_id") or f.parts[-2]) in outliers)
            f.write_text(json.dumps(r, indent=1, ensure_ascii=False))
        print(f"  canonical {task}: {info['n_covered']}/{len(props)} episodes agree ({info['n_distinct_proposals']} distinct, "
              f"{'LLM' if used == 'llm' else 'vote'}{', REVIEW' if review else ''}): {chosen['task_text']}")
    print(f"  canonical_task: {len(files_by_task)} folder(s), {n_review} flagged needs_review, aggregation cost ${cost:.4f}")
    return all_files


def finish_run(a, client, tasks):
    """After all batches and retries: one canonical_task per task folder, then upload (unless --no-upload), summary."""
    print(f"consolidating canonical_task for {len(tasks)} task folder(s)", flush=True)
    files = consolidate_canonical(a, set(tasks))
    if a.upload_s3 and client is not None and files:
        upload_all(client, a, files)
    summarize(a.results, a.s3_result_suffix)


def submit_jobs(a, cfg, key, records, thinking_level, tag=""):
    """records: prepared episodes (task, episode, key, s3_uri, size, request, request_mb). Writes one JSONL per
    group, uploads it, submits a batch job. Returns the job folders.
    Groups follow the task folders: a job holds the whole task folders of ONE station (one or several tasks, packed
    up to max_batch_mb); stations never share a job, and a task is split over jobs only when it alone exceeds
    max_batch_mb. thinking_level and max_output_tokens are set here, not in the cached request, so changing them
    needs no re-sampling."""
    by_task = {}
    for r in sorted(records, key=lambda r: (r["task"], r["episode"])):
        by_task.setdefault(r["task"], []).append(r)
    groups, cur, cur_mb, cur_station = [], [], 0.0, None
    for task, recs in by_task.items():
        station, task_mb = task.split("/", 1)[0], sum(r["request_mb"] for r in recs)
        if cur and (station != cur_station or cur_mb + task_mb > a.max_batch_mb):
            groups.append(cur)
            cur, cur_mb = [], 0.0
        cur_station = station
        for r in recs:  # only a task larger than max_batch_mb on its own is split here
            if cur and cur_mb + r["request_mb"] > a.max_batch_mb:
                groups.append(cur)
                cur, cur_mb = [], 0.0
            cur.append(r)
            cur_mb += r["request_mb"]
    groups.append(cur)
    for gi, g in enumerate(groups, 1):
        tasks = sorted({r["task"] for r in g})
        print(f"[job {gi}/{len(groups)}{tag}] {len(g)} episodes, {sum(r['request_mb'] for r in g):.0f} MB: {', '.join(tasks)}")
    job_dirs = []
    stamp = time.strftime("%Y%m%d-%H%M%S") + tag
    for gi, g in enumerate(groups, 1):
        jd = a.results / "batches" / f"{stamp}_{gi:02d}"
        jd.mkdir(parents=True, exist_ok=True)
        src = jd / "requests.jsonl"
        with open(src, "w") as fh:
            for r in g:
                req = json.loads(Path(r["request"]).read_text())
                req["generationConfig"]["maxOutputTokens"] = a.max_output_tokens
                if thinking_level:
                    req["generationConfig"]["thinkingConfig"] = {"thinkingLevel": thinking_level}
                else:
                    req["generationConfig"].pop("thinkingConfig", None)
                fh.write(json.dumps({"key": f"{r['task']}/{r['episode']}", "request": req}) + "\n")
        name = f"umi-reps-{stamp}-{gi:02d}"
        print(f"[job {gi}/{len(groups)}{tag}] uploading {src.stat().st_size / 1e6:.0f} MB ({len(g)} episodes, "
              f"thinking {thinking_level or 'model default'}, max output {a.max_output_tokens})", flush=True)
        file_name = upload_file(key, src, name)
        batch_name = submit(key, cfg["model"], file_name, name)
        print(f"[job {gi}/{len(groups)}{tag}] submitted {batch_name} (input {file_name})", flush=True)
        (jd / "job.json").write_text(json.dumps({
            "batch_name": batch_name, "input_file": file_name, "submitted": stamp, "model": cfg["model"],
            "fps": a.fps, "media_resolution": a.media_resolution, "thinking_level": thinking_level,
            "max_output_tokens": a.max_output_tokens,
            "input": getattr(a, "input", "frames"),
            "episodes": [{k: r[k] for k in ("task", "episode", "key", "s3_uri", "size", "file_name") if k in r} for r in g]},
            indent=1))
        src.unlink()  # the uploaded copy is what counts; requests stay cached in work_dir
        job_dirs.append(jd)
    return job_dirs


def retry_failed(a, cfg, key, client, bad):
    """One retry pass for episodes without a parsed result (MAX_TOKENS, unparseable, missing): same cached request,
    thinking at retry_thinking_level so the answer fits. Returns the episodes still without a result."""
    if not bad or not a.retry:
        return bad
    recs = []
    for e in bad:
        req = a.work / e["task"] / e["episode"] / "request.json"
        if req.exists():
            recs.append(dict(e, request=str(req), request_mb=req.stat().st_size / 1e6))
    print(f"retry: {len(recs)} episode(s) ({', '.join(e['task'] + '/' + e['episode'] + ' ' + e['finish_reason'] for e in bad)}) "
          f"with thinking {a.retry_thinking_level}", flush=True)
    if not recs:
        return bad
    still = []
    for jd in submit_jobs(a, cfg, key, recs, a.retry_thinking_level, tag="_retry"):
        still += collect(a, cfg, key, jd, client)
    return still + [e for e in bad if not (a.work / e["task"] / e["episode"] / "request.json").exists()]


def main():
    load_env(HERE / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "s3_run.json")
    ap.add_argument("--source", help="s3://bucket/prefix/ (default: config source)")
    ap.add_argument("--task", action="append", help="only these tasks (repeatable): station1/2026-11-21/task01, a prefix such as station1 or station1/2026-11-21, or a bare task01 (every station and date)")
    ap.add_argument("--episode", action="append", help="only these episode ids (repeatable)")
    ap.add_argument("--limit", type=int, help="at most N episodes per task")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--input", choices=["video", "frames"],
                    help="video: the head MP4 itself via the Files API (default, config 'input'); frames: sampled JPEGs")
    ap.add_argument("--video-job-gb", type=float, help="video input: MP4 GB per batch job (config video_job_gb)")
    ap.add_argument("--upload-workers", type=int, help="video input: MP4s downloaded and uploaded in parallel")
    ap.add_argument("--prompts", choices=sorted(k for k in R.PROMPT_SETS if k.startswith("final")),
                    help="prompt set from configs/config.json (default: s3_run.json prompt_set, else the config set)")
    ap.add_argument("--media-resolution", choices=["low", "medium", "high"])
    ap.add_argument("--thinking-level", choices=["minimal", "low", "medium", "high", "default"],
                    help="Gemini thinkingConfig.thinkingLevel (default: config thinking_level; 'default' = send none)")
    ap.add_argument("--workers", type=int, help="episodes prepared in parallel (download + decode)")
    ap.add_argument("--force", action="store_true", help="redo episodes that already have a result")
    ap.add_argument("--debug", action="store_true", help="keep frames/ and raw_response.json per episode")
    ap.add_argument("--keep-videos", action="store_true", help="keep downloaded MP4s in work_dir")
    ap.add_argument("--dry-run", action="store_true", help="prepare requests and print size and cost; no upload")
    ap.add_argument("--list", action="store_true", help="only list the episodes found in S3")
    ap.add_argument("--resume", action="store_true", help="collect the submitted job(s) not yet collected")
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--upload-only", action="store_true",
                    help="only copy the existing parsed local results next to their MP4s in S3")
    ap.add_argument("--no-upload", action="store_true", help="keep results local (no S3 write)")
    ap.add_argument("--canonical-method", choices=["llm", "majority"],
                    help="how one canonical_task per task folder is chosen (default: config canonical_method, llm)")
    ap.add_argument("--consolidate-only", action="store_true",
                    help="only give each task folder one canonical_task from its local results (then upload unless --no-upload)")
    a = ap.parse_args()

    cfg_run = json.loads(a.config.read_text())
    a.model_key = cfg_run["model"]
    cfg = R.model_cfgs([a.model_key])[a.model_key]
    if cfg["provider"] != "gemini":
        sys.exit("the batch runner needs a Gemini model")
    a.fps = a.fps or cfg_run["fps"]
    a.media_resolution = a.media_resolution or cfg_run["media_resolution"]
    a.thinking_level = a.thinking_level or cfg_run.get("thinking_level")
    a.thinking_level = None if a.thinking_level == "default" else a.thinking_level
    a.max_side = cfg_run.get("long_side_px") or R.CFG["frames"]["long_side_px"]
    a.jpeg_quality = cfg_run.get("jpeg_quality") or R.CFG["frames"]["jpeg_quality"]
    a.max_output_tokens = cfg_run.get("max_output_tokens") or cfg["max_output_tokens"]
    a.max_batch_mb = cfg_run.get("max_batch_mb", 1800)
    a.retry = cfg_run.get("retry_failed", True)
    a.retry_thinking_level = cfg_run.get("retry_thinking_level", "low")
    a.given_task = cfg_run.get("given_task")
    a.input = a.input or cfg_run.get("input", "frames")
    a.prompts = a.prompts or (cfg_run.get("prompt_set") if a.input == "video" else cfg_run.get("frames_prompt_set")) \
        or R.CFG["prompt"]["set"]
    if (a.input == "video") != ("video" in a.prompts):
        sys.exit(f"--input {a.input} needs a {'video' if a.input == 'video' else 'frame'} prompt set, not {a.prompts}")
    a.video_job_gb = a.video_job_gb or cfg_run.get("video_job_gb", 8)
    a.video_jobs_in_flight = cfg_run.get("video_jobs_in_flight", 2)
    a.upload_workers = a.upload_workers or cfg_run.get("upload_workers", 8)
    a.region = cfg_run.get("region")
    R.PROMPTS = R.PROMPT_SETS[a.prompts]
    a.workers = a.workers or cfg_run.get("workers", 4)
    a.debug = a.debug or cfg_run.get("debug", False)
    a.keep_videos = a.keep_videos or cfg_run.get("keep_videos", False)
    a.poll_seconds = cfg_run.get("poll_seconds", 60)
    a.work = here_path(cfg_run["work_dir"])
    a.results = here_path(cfg_run["results_dir"])
    batches = a.results / "batches"
    a.head_suffix = cfg_run.get("head_suffix", "_head.mp4")
    a.s3_result_suffix = cfg_run.get("s3_result_suffix", "_vlm_result.json")
    a.upload_s3 = cfg_run.get("upload_results_to_s3", True) and not a.no_upload
    a.canonical_method = a.canonical_method or cfg_run.get("canonical_method", "llm")
    a.canonical_min_support = float(cfg_run.get("canonical_min_support", 0.5))
    a.canonical_min_episodes = int(cfg_run.get("canonical_min_episodes", 5))
    a.canonical_hints = bool(cfg_run.get("canonical_hints", True))
    migrate_legacy(a)

    if a.summary_only:
        summarize(a.results, a.s3_result_suffix)
        return
    if a.upload_only:
        files = result_files(a)
        if a.task:
            files = [f for f in files if task_matches(result_task(a, f), a.task)]
        if a.episode:
            files = [f for f in files if f.parts[-2] in a.episode]
        upload_all(s3_client(cfg_run.get("region")), a, files)
        return
    if a.consolidate_only:
        tasks = {result_task(a, f) for f in result_files(a)}
        if a.task:
            tasks = {t for t in tasks if task_matches(t, a.task)}
        finish_run(a, s3_client(cfg_run.get("region")) if a.upload_s3 else None, tasks)
        return
    key = R.load_env_key(cfg["api_key_env"])
    if not key and not (a.list or a.dry_run):
        sys.exit(f"{cfg['api_key_env']} not set (.env here, the shell, or vlm_run/.env)")
    if a.resume:
        open_jobs = [d for d in sorted(batches.glob("*")) if (d / "job.json").exists()
                     and "state" not in json.loads((d / "job.json").read_text())]
        if not open_jobs:
            sys.exit("no submitted job waiting to be collected")
        client = s3_client(cfg_run.get("region"))
        bad = [e for d in open_jobs for e in collect(a, cfg, key, d, client)]
        if not any(d.name.endswith("_retry_01") or "_retry_" in d.name for d in open_jobs):
            bad = retry_failed(a, cfg, key, client, bad)
        names = [e["file_name"] for d in open_jobs for e in json.loads((d / "job.json").read_text())["episodes"]
                 if e.get("file_name")]
        if names:
            delete_files(key, names)
        finish_run(a, client, {e["task"] for d in open_jobs for e in json.loads((d / "job.json").read_text())["episodes"]})
        sys.exit(f"{len(bad)} episode(s) without a parsed result" if bad else 0)

    bucket, prefix = split_s3(a.source or cfg_run["source"])
    client = s3_client(cfg_run.get("region"))
    try:
        eps = list_episodes(client, bucket, prefix, cfg_run.get("head_suffix", "_head.mp4"))
    except Exception as ex:
        sys.exit(f"S3 listing of s3://{bucket}/{prefix} failed: {ex}\n"
                 f"(AWS_PROFILE={os.environ.get('AWS_PROFILE') or '-'}; on a laptop: aws sso login --profile prod)")
    if a.task:
        eps = [e for e in eps if task_matches(e["task"], a.task)]
    if a.episode:
        eps = [e for e in eps if e["episode"] in a.episode]
    if a.limit:
        per = {}
        eps = [e for e in eps if per.setdefault(e["task"], []).append(e) or len(per[e["task"]]) <= a.limit]
    tasks = sorted({e["task"] for e in eps})
    print(f"s3://{bucket}/{prefix}: {len(tasks)} task(s), {len(eps)} episode(s), {sum(e['size'] for e in eps) / 1e9:.1f} GB; "
          f"{cfg['model']} batch, {a.fps:g} fps, media resolution {a.media_resolution}, "
          f"thinking {a.thinking_level or 'model default'}, input {a.input}, prompts {a.prompts}"
          + ("" if a.input == "video" else f", long side {a.max_side} px"))
    if a.list:
        for e in eps:
            print(f"  {e['task']}/{e['episode']}  {e['size'] / 1e6:.1f} MB  {e['key']}")
        return
    todo = [e for e in eps if a.force or not is_done(a, e)]
    print(f"{len(eps) - len(todo)} already done, {len(todo)} to run")
    if not todo:
        if not a.dry_run:  # a dry run never consolidates or writes to S3
            finish_run(a, client, tasks)
        return

    if a.input == "video":
        if a.dry_run:
            dur = {}
            inv = HERE / "reports" / "s3_head_video_by_episode.csv"
            if inv.exists():
                dur = {r["s3_uri"]: float(r["duration_s"] or 0) for r in csv.DictReader(open(inv))}
            secs = sum(dur.get(e["s3_uri"], 60.0) for e in todo)
            per_frame = {"low": 68, "medium": 68, "high": 258}[a.media_resolution]  # measured, video_token_counts.csv
            est_in = int(secs * a.fps * (per_frame + 15) + 4500 * len(todo))
            for gi, g in enumerate(video_groups(a, todo), 1):
                print(f"[group {gi}] {len(g)} episodes, {sum(e['size'] for e in g) / 1e9:.1f} GB: "
                      f"{', '.join(sorted({e['task'] for e in g}))}")
            print(f"{len(todo)} episode(s), {secs / 3600:.1f} h of video; estimated input {est_in:,} tokens = "
                  f"${R.cost_usd(cfg, est_in, 0, True):.2f} batch input (+ output, typically a few k tokens per episode)")
            return
        bad = run_video(a, cfg, key, client, bucket, todo)
        finish_run(a, client, tasks)
        if bad:
            sys.exit(f"{bad} episode(s) without a parsed result")
        return

    # prepare in parallel processes (decode is CPU bound)
    a_dict = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()}
    ready, failed = [], 0
    with cf.ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(prepare, e, a_dict, bucket, cfg_run.get("region")): e for e in todo}
        for i, f in enumerate(cf.as_completed(futs), 1):
            e = futs[f]
            try:
                r = f.result()
                ready.append(r)
                print(f"  [{i}/{len(todo)}] {e['task']}/{e['episode']}: {r['n_steps']} steps, request {r['request_mb']:.1f} MB"
                      + (" (cached)" if r["cached"] else ""), flush=True)
            except Exception as err:
                failed += 1
                print(f"  [{i}/{len(todo)}] {e['task']}/{e['episode']}: prepare FAILED: {err!r}", flush=True)
    ready.sort(key=lambda r: (r["task"], r["episode"]))
    n_img = sum(r["n_steps"] for r in ready)
    per_img = {"low": 266, "medium": 540, "high": 1120}[a.media_resolution]  # measured on these videos (high: nominal)
    est_in = n_img * per_img + 3500 * len(ready) + 42 * n_img  # text: ~3.5k per episode + ~42 per image (measured)
    total_mb = sum(r["request_mb"] for r in ready)
    print(f"{len(ready)} request(s), {n_img} images, {total_mb:.0f} MB; estimated input {est_in:,} tokens = "
          f"${R.cost_usd(cfg, est_in, 0, True):.2f} batch input (+ output, typically a few k tokens per episode)")
    if a.dry_run or not ready:
        if failed:
            sys.exit(f"{failed} episode(s) failed to prepare")
        return

    job_dirs = submit_jobs(a, cfg, key, ready, a.thinking_level)
    print("waiting for the batch job(s); if interrupted, run again with --resume", flush=True)
    bad = [e for jd in job_dirs for e in collect(a, cfg, key, jd, client)]
    bad = retry_failed(a, cfg, key, client, bad)
    bad = len(bad) + failed
    finish_run(a, client, tasks)
    if bad:
        sys.exit(f"{bad} episode(s) without a parsed result")


if __name__ == "__main__":
    main()
