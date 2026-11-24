#!/usr/bin/env python3
"""UMI delivery check: PASS / FAIL / REVIEW per recording, against DataPRD1019 v1.1 (UMI section 6).

The checklist, with every rule and threshold, is docs/UMI_delivery_checklist.md; the numbers are in
configs/delivery_check.json. One recording = one episode folder of the delivery (14_export_rhoda.py output):

    <station>/[<date>/]<taskNN>/<episode>/<rec>_head.mp4, _left.mp4, _right.mp4, _meta.json,
                                         _right_gripper.csv, _left_gripper.csv, [_mosaic.mp4], [_vlm_result.json]

HARD checks (any FAIL fails the recording):
  D1 three views present          D2 camera metadata complete     D3 sync method + frame index per file
  D4 gripper width per frame      V1 same frame rate              V2 same span (frame count, duration)
  V3 codec + resolution as meta   V4 synchronized (same sync index)
  C1 >= 3 cycles (manual count, else VLM count)                   C2 cycles >= 3 s   C3 duration >= 9 s
WARN / INFO: W1 both grippers move (U5, passive allowed), W2 task is not a setup activity, W3 target 5 cycles,
  W4 duration / count > 30 s, W5 mosaic present.
Videos are probed with ffprobe from the mp4 header only (S3: a presigned URL, no download of the video).

    python scripts/check_delivery.py                                  # config source: every station / date / task
    python scripts/check_delivery.py --task station2/2026-11-22       # a part (prefix or bare task01)
    python scripts/check_delivery.py --source /path/to/local/delivery # a local folder
    python scripts/check_delivery.py --limit 2                        # 2 recordings per task

Output: reports/delivery_check.csv (one row per recording: verdict, reasons, every check and its value) and
reports/delivery_check_summary.csv (per task: recordings, PASS / FAIL / REVIEW, top fail reasons). Needs ffprobe
(apt-get install ffmpeg) and, for S3, boto3 with read access to the prefix.
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]  # project root vlm_scripts_reports/ (scripts live in scripts/)
STATION = re.compile(r"^station\d+$", re.I)
TASK_DIR = re.compile(r"^task\d+$", re.I)
VIDEO_ROLES = ("head", "left", "right")
GRIPPERS = ("right", "left")
CHECK_IDS = ("D1", "D2", "D3", "D4", "V1", "V2", "V3", "V4", "C1", "C2", "C3", "W1", "W2", "W3", "W4", "W5")
HARD = {"D1", "D2", "D3", "D4", "V1", "V2", "V3", "V4", "C1", "C2", "C3"}


# ---------------------------------------------------------------- storage: local folder or s3:// prefix
class Local:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def list(self):
        return [str(p) for p in self.root.rglob("*") if p.is_file()]

    def parts(self, key):  # full path components, for the station / task split
        return Path(key).parts

    def read_text(self, key):
        return Path(key).read_text()

    def url(self, key):
        return key

    def name(self, key):
        return key


class S3:
    def __init__(self, uri, region=None):
        import boto3  # only needed for S3
        self.bucket, _, self.prefix = uri[5:].partition("/")
        self.client = boto3.Session(region_name=region or None).client("s3")

    def list(self):
        keys = []
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix):
            keys += [o["Key"] for o in page.get("Contents", [])]
        return keys

    def parts(self, key):
        return key.split("/")

    def read_text(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode()

    def url(self, key):
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key},
                                                  ExpiresIn=3600)

    def name(self, key):
        return f"s3://{self.bucket}/{key}"


def recordings(store, suffixes):
    """Group the files into recordings: one per folder that holds any of head / left / right / meta."""
    by_dir = collections.defaultdict(dict)
    for key in store.list():
        folder, _, fname = key.rpartition("/")
        for role, suf in suffixes.items():
            if fname.endswith(suf):
                by_dir[folder][role] = (key, fname[: -len(suf)])
                break
    recs = []
    for folder, files in sorted(by_dir.items()):
        if not any(r in files for r in (*VIDEO_ROLES, "meta")):
            continue  # e.g. a folder with only a VLM result
        names = collections.Counter(n for r, (_, n) in files.items() if r in (*VIDEO_ROLES, "meta"))
        rec = names.most_common(1)[0][0]
        parts = [p for p in store.parts(folder + "/x")[:-1] if p]
        st = next((i for i, p in enumerate(parts) if STATION.match(p)), None)
        ti = next((i for i, p in enumerate(parts) if TASK_DIR.match(p) and (st is None or i > st)), None)
        if ti is None:
            task, episode = (parts[-2] if len(parts) > 1 else ""), parts[-1]
        else:
            task = "/".join(parts[(st if st is not None else ti): ti + 1])
            episode = "__".join(parts[ti + 1:]) or rec
        recs.append({"task": task, "episode": episode, "rec": rec, "folder": store.name(folder),
                     "files": {r: k for r, (k, n) in files.items() if n == rec or r == "vlm"}})
    return recs


def task_matches(task, wanted):
    return any(task == w or task.startswith(w.rstrip("/") + "/") or task.rsplit("/", 1)[-1] == w for w in wanted)


# ---------------------------------------------------------------- probes
def ffprobe(url):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,width,height,r_frame_rate,nb_frames,duration:format=duration",
                          "-of", "json", url], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "ffprobe failed")
    j = json.loads(out.stdout)
    s = (j.get("streams") or [{}])[0]
    if not s:
        raise RuntimeError("no video stream")
    fps = float(Fraction(s["r_frame_rate"])) if s.get("r_frame_rate") not in (None, "0/0") else None
    dur = s.get("duration") or (j.get("format") or {}).get("duration")
    dur = float(dur) if dur not in (None, "N/A") else None
    nb = s.get("nb_frames")
    frames = int(nb) if nb not in (None, "N/A") else (round(dur * fps) if dur and fps else None)
    return {"codec": s.get("codec_name"), "width": s.get("width"), "height": s.get("height"), "fps": fps,
            "duration": dur, "frames": frames, "frames_from_header": nb not in (None, "N/A")}


def read_widths(text):
    rows = list(csv.DictReader(text.splitlines()))
    vals = []
    for r in rows:
        try:
            vals.append(float(r.get("width_m")))
        except (TypeError, ValueError):
            vals.append(float("nan"))
    return vals


def parse_resolution(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return int(v[0]), int(v[1])
    m = re.match(r"^\s*(\d+)\s*[x×X,]\s*(\d+)\s*$", str(v or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


# ---------------------------------------------------------------- the checklist
def check(store, rec, cfg, manual):
    res = {k: ("", "") for k in CHECK_IDS}  # id -> (status, value)
    files = rec["files"]
    put = lambda k, status, value="": res.__setitem__(k, (status, str(value)))

    # D1 three views
    missing = [r for r in VIDEO_ROLES if r not in files]
    probes, bad = {}, []
    for r in VIDEO_ROLES:
        if r in files:
            try:
                probes[r] = ffprobe(store.url(files[r]))
            except Exception as ex:
                bad.append(f"{r}: {ex}"[:120])
    put("D1", "FAIL" if missing or bad else "PASS",
        "; ".join([f"missing {', '.join(missing)}"] * bool(missing) + bad) or "head, left, right")

    # D2 / D3 metadata
    meta = None
    if "meta" in files:
        try:
            meta = json.loads(store.read_text(files["meta"]))
        except Exception as ex:
            put("D2", "FAIL", f"meta.json unreadable: {ex}"[:120])
    if meta is None and not res["D2"][0]:
        put("D2", "FAIL", "meta.json missing")
    cams = (meta or {}).get("cameras") or {}
    if meta is not None and not res["D2"][0]:
        gaps = []
        for r in VIDEO_ROLES:
            c = cams.get(r)
            if not isinstance(c, dict):
                gaps.append(f"{r}: no entry")
                continue
            need = [k for k in cfg["camera_keys_required"] if c.get(k) in (None, "")]
            if not any(c.get(k) not in (None, "") for k in cfg["camera_lens_keys_any"]):
                need.append("lens/fov")
            if "kannala" in str(c.get("intrinsics_model", "")).lower():
                need += [k for k in cfg["kannala_brandt_keys"] if c.get(k) is None]
            if need:
                gaps.append(f"{r}: {', '.join(need)}")
        put("D2", "FAIL" if gaps else "PASS", "; ".join(gaps) or
            ", ".join(sorted({str(cams[r].get('model')) for r in VIDEO_ROLES})))
    sync = (meta or {}).get("sync") or {}
    idx = sync.get("frame_index") or {}
    if meta is None:
        put("D3", "FAIL", "meta.json missing")
    else:
        gaps = [] if isinstance(sync.get("method"), str) and sync["method"].strip() else ["no sync.method"]
        for r in VIDEO_ROLES:
            v = idx.get(r)
            n = (probes.get(r) or {}).get("frames")
            if not isinstance(v, int) or isinstance(v, bool):
                gaps.append(f"{r}: no frame index")
            elif v < 0 or (n is not None and v >= n):
                gaps.append(f"{r}: frame index {v} outside 0..{n}")
        put("D3", "FAIL" if gaps else "PASS", "; ".join(gaps) or f"{sync['method']}; index {[idx[r] for r in VIDEO_ROLES]}")

    # D4 gripper widths (+ W1 both grippers in use)
    lo, hi = cfg["gripper_width_m"]
    n_ref = (probes.get("head") or {}).get("frames")
    gaps, ranges = [], {}
    for g in GRIPPERS:
        key = files.get(f"{g}_gripper")
        if not key:
            gaps.append(f"{g}: csv missing")
            continue
        try:
            w = read_widths(store.read_text(key))
        except Exception as ex:
            gaps.append(f"{g}: unreadable ({ex})"[:80])
            continue
        n_g = (probes.get(g) or {}).get("frames") or n_ref
        if not w:
            gaps.append(f"{g}: empty")
            continue
        if n_g is not None and abs(len(w) - n_g) > cfg["gripper_rows_tolerance"]:
            gaps.append(f"{g}: {len(w)} rows, {n_g} frames")
        if any(math.isnan(x) for x in w):
            gaps.append(f"{g}: NaN widths")
        fin = [x for x in w if not math.isnan(x)]
        if fin and (min(fin) < lo or max(fin) > hi):
            gaps.append(f"{g}: width {min(fin):.3f}..{max(fin):.3f} m outside {lo}..{hi}")
        if fin:
            ranges[g] = (min(fin), max(fin))
    put("D4", "FAIL" if gaps else "PASS", "; ".join(gaps) or
        "; ".join(f"{g} {a:.3f}-{b:.3f} m" for g, (a, b) in ranges.items()))
    if len(ranges) == 2:
        idle = [g for g, (a, b) in ranges.items() if b - a < cfg["gripper_active_range_m"]]
        put("W1", "WARN" if idle else "PASS",
            (f"{', '.join(idle)} gripper barely moves (passive role allowed)" if idle else "both grippers open and close"))
    else:
        put("W1", "INFO", "gripper widths missing")

    # V1 frame rate, V2 span, V3 codec / resolution, V4 sync index
    got = {r: p for r, p in probes.items()}
    if len(got) == 3:
        fps = {r: p["fps"] for r, p in got.items()}
        meta_fps = {r: (cams.get(r) or {}).get("frame_rate_hz") for r in VIDEO_ROLES}
        tol = cfg["fps_tolerance"]
        msgs = []
        if None in fps.values() or max(fps.values()) - min(fps.values()) > tol:
            msgs.append(f"rates differ {fps}")
        for r in VIDEO_ROLES:
            try:
                if meta_fps[r] is not None and abs(float(meta_fps[r]) - fps[r]) > tol:
                    msgs.append(f"{r}: {fps[r]:.3f} fps vs meta {meta_fps[r]}")
            except (TypeError, ValueError):
                msgs.append(f"{r}: meta frame_rate_hz {meta_fps[r]!r}")
        f0 = fps["head"] or 0
        if msgs:
            put("V1", "FAIL", "; ".join(msgs))
        elif abs(f0 - cfg["expected_fps"]) > tol:
            put("V1", "PASS", f"{f0:.3f} fps on all three (expected {cfg['expected_fps']}: check camera mode)")
        else:
            put("V1", "PASS", f"{f0:.3f} fps on all three")
        frames = {r: p["frames"] for r, p in got.items()}
        durs = {r: p["duration"] for r, p in got.items()}
        msgs = []
        if None in frames.values():
            msgs.append(f"frame count unknown {frames}")
        elif max(frames.values()) - min(frames.values()) > cfg["max_frame_count_diff"]:
            msgs.append(f"frame counts {frames}")
        if None not in durs.values() and f0:
            if (max(durs.values()) - min(durs.values())) * f0 > cfg["max_duration_diff_frames"] + 1e-6:
                msgs.append("durations " + ", ".join(f"{r} {d:.3f}s" for r, d in durs.items()))
        put("V2", "FAIL" if msgs else "PASS", "; ".join(msgs) or f"{frames['head']} frames, {durs['head']:.2f} s")
        msgs = []
        for r, p in got.items():
            if p["codec"] not in cfg["video_codecs"]:
                msgs.append(f"{r}: codec {p['codec']}")
            want = parse_resolution((cams.get(r) or {}).get("resolution"))
            if want and (p["width"], p["height"]) != want:
                msgs.append(f"{r}: {p['width']}x{p['height']} vs meta {want[0]}x{want[1]}")
        put("V3", "FAIL" if msgs else "PASS", "; ".join(msgs) or
            f"{got['head']['codec']} {got['head']['width']}x{got['head']['height']}")
    else:
        for k in ("V1", "V2", "V3"):
            put(k, "FAIL", "not all three videos readable")
    if all(isinstance(idx.get(r), int) for r in VIDEO_ROLES):
        same = len({idx[r] for r in VIDEO_ROLES}) == 1
        put("V4", "PASS" if same else "FAIL", f"sync frame index {[idx[r] for r in VIDEO_ROLES]}"
            + ("" if same else " (files do not start at the same instant)"))
    else:
        put("V4", "FAIL", "no sync frame index per file")

    # C1-C3 cycles, W2-W5
    vlm = {}
    if files.get("vlm"):
        try:
            vlm = (json.loads(store.read_text(files["vlm"])).get("response") or {})
        except Exception:
            vlm = {}
    dur = (got.get("head") or {}).get("duration")
    m = manual.get((rec["task"], rec["episode"]))
    if m is not None:
        n, src, conf = m, "manual", None
    elif isinstance(vlm.get("n_repetitions"), int):
        n, src, conf = vlm["n_repetitions"], "vlm", vlm.get("n_repetitions_confidence")
    else:
        n, src, conf = None, "", None
    mc, (cmin, cmax) = cfg["min_cycles"], cfg["cycle_s"]
    if n is None:
        put("C1", "REVIEW", "no cycle count (manual or VLM)")
    elif n >= mc:
        put("C1", "PASS", f"{n} cycles ({src})")
    elif src == "manual" or (isinstance(conf, (int, float)) and conf >= cfg["vlm_fail_confidence"]):
        put("C1", "FAIL", f"{n} cycles ({src}{'' if conf is None else f', confidence {conf}'}), {mc} needed")
    else:
        put("C1", "REVIEW", f"{n} cycles (vlm, confidence {conf}): count by hand")
    if n and dur:
        if dur < cmin * n - 0.1:  # 0.1 s: rounding of the container duration
            put("C2", "FAIL" if src == "manual" else "REVIEW",
                f"{dur:.1f} s for {n} cycles: some cycle < {cmin} s")
        else:
            put("C2", "PASS", f"{dur / n:.1f} s per cycle incl. idle")
        put("W4", "WARN" if dur / n > cmax else "PASS", f"{dur / n:.1f} s per cycle incl. idle (max {cmax} s)")
    elif n == 0:
        put("C2", "N/A", "0 cycles")
    else:
        put("C2", "REVIEW" if dur else "FAIL", "no count" if dur else "no duration")
    if dur is None:
        put("C3", "FAIL", "no head duration")
    else:
        put("C3", "PASS" if dur >= mc * cmin else "FAIL", f"{dur:.1f} s (min {mc * cmin} s)")
    if n is not None:
        put("W3", "INFO" if mc <= n < cfg["target_cycles"] else ("PASS" if n >= cfg["target_cycles"] else ""),
            f"{n} cycles (target {cfg['target_cycles']})")
    ct, t = vlm.get("canonical_task") or {}, vlm.get("task") or {}
    text = " ".join(str(x.get(k, "")) for x in (ct, t) for k in ("task_text", "action"))
    if not vlm:
        put("W2", "INFO", "no VLM result")
    elif re.search(cfg["setup_task_regex"], text, re.I):
        put("W2", "REVIEW", f"VLM names a setup activity: {t.get('task_text') or ct.get('task_text')}"[:150])
    else:
        put("W2", "PASS", (ct.get("task_text") or t.get("task_text") or "")[:150])
    put("W5", "INFO", "mosaic present" if files.get("mosaic") else "no mosaic (optional)")

    fails = [f"{k}: {v}" for k, (s, v) in res.items() if s == "FAIL" and k in HARD]
    reviews = [f"{k}: {v}" for k, (s, v) in res.items() if s == "REVIEW"]
    verdict = "FAIL" if fails else ("REVIEW" if reviews else "PASS")
    row = {"task": rec["task"], "episode": rec["episode"], "verdict": verdict,
           "reasons": " | ".join(fails or reviews), "n_cycles": "" if n is None else n, "count_source": src,
           "duration_s": "" if dur is None else round(dur, 2), "folder": rec["folder"]}
    for k in CHECK_IDS:
        row[k], row[f"{k}_value"] = res[k]
    return row


def load_manual(path):
    out = {}
    if path.exists():
        for r in csv.DictReader(open(path)):
            v = (r.get("n_repetitions_manual") or "").strip()
            if v:
                try:
                    out[(r["task"], r["episode"])] = int(float(v))
                except ValueError:
                    pass
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "delivery_check.json")
    ap.add_argument("--source", help="s3://bucket/prefix/ or a local folder (default: config source)")
    ap.add_argument("--task", action="append", help="station1, station1/2026-11-21, station1/2026-11-21/task01 or task01")
    ap.add_argument("--limit", type=int, help="at most N recordings per task")
    ap.add_argument("--out", type=Path, help="per-recording CSV (default: config out_csv)")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    if not shutil.which("ffprobe"):
        sys.exit("ffprobe not found: apt-get install ffmpeg (or brew install ffmpeg)")
    src = a.source or cfg["source"]
    store = S3(src, cfg.get("region")) if src.startswith("s3://") else Local(src)
    recs = recordings(store, cfg["suffixes"])
    if a.task:
        recs = [r for r in recs if task_matches(r["task"], a.task)]
    if a.limit:
        per = collections.defaultdict(int)
        recs = [r for r in recs if (per.__setitem__(r["task"], per[r["task"]] + 1) or per[r["task"]] <= a.limit)]
    if not recs:
        sys.exit(f"no recordings under {src}")
    manual = load_manual(HERE / cfg["manual_counts"])
    print(f"{src}: {len(recs)} recordings in {len({r['task'] for r in recs})} tasks; "
          f"{len(manual)} manual counts", flush=True)

    rows = []
    with cf.ThreadPoolExecutor(max_workers=cfg.get("workers", 16)) as ex:
        futs = {ex.submit(check, store, r, cfg, manual): r for r in recs}
        for i, f in enumerate(cf.as_completed(futs), 1):
            r = futs[f]
            try:
                row = f.result()
            except Exception as err:
                row = {"task": r["task"], "episode": r["episode"], "verdict": "FAIL",
                       "reasons": f"check crashed: {err!r}"[:300], "folder": r["folder"]}
            rows.append(row)
            if i % 50 == 0 or i == len(recs):
                print(f"  {i}/{len(recs)}", flush=True)
    rows.sort(key=lambda r: (r["task"], r["episode"]))

    out = a.out or HERE / cfg["out_csv"]
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["task", "episode", "verdict", "reasons", "n_cycles", "count_source", "duration_s"] + \
           [c for k in CHECK_IDS for c in (k, f"{k}_value")] + ["folder"]
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    summ = []
    for task in sorted({r["task"] for r in rows}):
        sub = [r for r in rows if r["task"] == task]
        v = collections.Counter(r["verdict"] for r in sub)
        why = collections.Counter(k for r in sub for k in CHECK_IDS if r.get(k) == "FAIL" and k in HARD)
        summ.append({"task": task, "recordings": len(sub), "PASS": v["PASS"], "FAIL": v["FAIL"], "REVIEW": v["REVIEW"],
                     "fail_checks": ", ".join(f"{k} x{c}" for k, c in why.most_common())})
    tot = collections.Counter(r["verdict"] for r in rows)
    summ.append({"task": "ALL", "recordings": len(rows), "PASS": tot["PASS"], "FAIL": tot["FAIL"],
                 "REVIEW": tot["REVIEW"], "fail_checks": ", ".join(
                     f"{k} x{c}" for k, c in collections.Counter(
                         k for r in rows for k in CHECK_IDS if r.get(k) == "FAIL" and k in HARD).most_common())})
    sout = HERE / cfg["out_summary_csv"] if not a.out else a.out.with_name(a.out.stem + "_summary.csv")
    with open(sout, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)
    print(f"{'task':32s} {'n':>5s} {'PASS':>5s} {'FAIL':>5s} {'REVIEW':>6s}  fail checks")
    for s in summ:
        print(f"{s['task']:32s} {s['recordings']:5d} {s['PASS']:5d} {s['FAIL']:5d} {s['REVIEW']:6d}  {s['fail_checks']}")
    print(f"-> {out}\n-> {sout}")


if __name__ == "__main__":
    main()
