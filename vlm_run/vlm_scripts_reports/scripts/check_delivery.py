#!/usr/bin/env python3
"""UMI delivery check: PASS / FAIL / REVIEW per recording, against DataPRD1019 v1.1 (UMI section 6).

The checklist, with every rule and threshold, is docs/UMI_delivery_checklist.md; the numbers are in
configs/delivery_check.json. One recording = one episode folder of the delivery (14_export_rhoda.py output):

    <station>/[<date>/]<taskNN>/<episode>/<rec>_head.mp4, _left.mp4, _right.mp4, _meta.json,
                                         _right_gripper.csv, _left_gripper.csv, [_mosaic.mp4], [_vlm_result.json]

HARD checks (any FAIL fails the recording):
  D1 three views present          D2 camera metadata complete     D3 sync method + frame index per file
  D4 gripper width per frame      V1 same frame rate              V2 same span (frame count, duration)
  V3 codec + resolution as meta   V4 synchronized (same sync index)  D5 files: none empty, names match meta  D6 not a duplicate of another recording (same gripper data)
  V5 same start time              V6 constant frame rate             V7 every frame's timestamp (--deep)
  V8 every frame decodes (--decode)
  C1 >= 3 cycles (manual count, else VLM count)                   C2 cycles >= 3 s   C3 duration >= 9 s
WARN / INFO: W1 both grippers move (U5, passive allowed), W2 task is not a setup activity, W3 target 5 cycles,
  W4 duration / count > 30 s, W5 mosaic frame count = head, W6 file naming <date>_<taskNN>_<episode>,
  W7 calibrations match the rest of the station (left / right swapped?), W8 sync refined by wrist motion,
  W9 gripper width without frame-to-frame jumps, W10 gripper width not frozen for long, W11 video bitrate not low.
Videos are probed with ffprobe from the mp4 header only (S3: a presigned URL, no download of the video).

    python scripts/check_delivery.py                                  # config source: every station / date / task
    python scripts/check_delivery.py --task station2/2026-11-22       # a part (prefix or bare task01)
    python scripts/check_delivery.py --source /path/to/local/delivery # a local folder
    python scripts/check_delivery.py --limit 2                        # 2 recordings per task
    python scripts/check_delivery.py --deep                           # + every frame timestamp (reads whole files)
    python scripts/check_delivery.py --decode --task task06 --limit 3 # + full decode of a sample

Output (reports/):
  delivery_check.csv              one row per recording: verdict (PASS / REVIEW / FAIL), reasons, every check and value
  delivery_check_failures.csv     one row per failed or review check: recording, check, the S3 file(s), the reason
  delivery_check_deliverable.csv  the deliverable (PASS) recordings with their length
  delivery_check_summary.csv      per task, per station and overall: recordings and hours deliverable / review / fail
  delivery_check_report.md        the summary and the fail reasons on one page Needs ffprobe
(apt-get install ffmpeg) and, for S3, boto3 with read access to the prefix.
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import hashlib
import json
import math
import os
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
CHECK_IDS = ("D1", "D2", "D3", "D4", "D5", "D6", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "C1", "C2", "C3",
             "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11")
HARD = {"D1", "D2", "D3", "D4", "D5", "D6", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "C1", "C2", "C3"}
CHECK_NAMES = {
    "D1": "three views present", "D2": "camera metadata", "D3": "sync method and frame index", "D4": "gripper width per frame",
    "D5": "files and names", "D6": "not a duplicate", "V1": "same frame rate", "V2": "same frame count and duration", "V3": "codec and resolution",
    "V4": "synchronized start index", "V5": "same start time", "V6": "constant frame rate", "V7": "frame timeline (--deep)",
    "V8": "frames decode (--decode)", "C1": "at least 3 cycles", "C2": "cycles at least 3 s", "C3": "at least 9 s long",
    "W1": "both grippers move", "W2": "task is not setup", "W3": "target 5 cycles", "W4": "cycles up to 30 s",
    "W5": "mosaic", "W6": "file naming", "W7": "calibration matches station", "W8": "sync refined by wrist motion",
    "W9": "gripper width without jumps", "W10": "gripper width not frozen", "W11": "video bitrate"}
CHECK_FILES = {"D1": "video", "V1": "video", "V2": "video", "V3": "video", "V5": "video", "V6": "video", "V7": "video",
               "V8": "video", "D2": "meta", "D3": "meta", "D5": "meta", "V4": "meta", "D4": "gripper", "C1": "recording",
               "C2": "recording", "C3": "head", "W2": "vlm", "D6": "recording"}
REC_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}_)?task\d+_episode_\d{6}$", re.I)


# ---------------------------------------------------------------- storage: local folder or s3:// prefix
class Local:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def list(self):  # (key, size)
        return [(str(p), p.stat().st_size) for p in self.root.rglob("*") if p.is_file()]

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
            keys += [(o["Key"], o["Size"]) for o in page.get("Contents", [])]
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
    sizes = {}
    for key, size in store.list():
        folder, _, fname = key.rpartition("/")
        for role, suf in suffixes.items():
            if fname.endswith(suf):
                by_dir[folder][role] = (key, fname[: -len(suf)])
                sizes[key] = size
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
                     "files": {r: k for r, (k, n) in files.items() if n == rec or r == "vlm"},
                     "sizes": {r: sizes[k] for r, (k, n) in files.items() if n == rec or r == "vlm"},
                     "uris": {r: store.name(k) for r, (k, n) in files.items() if n == rec or r == "vlm"},
                     "stray": sorted(f"{r}:{n}" for r, (k, n) in files.items() if n != rec and r != "vlm")})
    return recs


def task_matches(task, wanted):
    return any(task == w or task.startswith(w.rstrip("/") + "/") or task.rsplit("/", 1)[-1] == w for w in wanted)


# ---------------------------------------------------------------- probes
def ffprobe(url):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,width,height,pix_fmt,r_frame_rate,avg_frame_rate,nb_frames,duration,bit_rate,"
                          "start_time:format=duration",
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
    avg = float(Fraction(s["avg_frame_rate"])) if s.get("avg_frame_rate") not in (None, "0/0") else None
    st = s.get("start_time")
    return {"codec": s.get("codec_name"), "width": s.get("width"), "height": s.get("height"), "pix_fmt": s.get("pix_fmt"),
            "fps": fps, "avg_fps": avg, "start": float(st) if st not in (None, "N/A") else None,
            "duration": dur, "frames": frames, "frames_from_header": nb not in (None, "N/A"),
            "kbps": int(s["bit_rate"]) // 1000 if str(s.get("bit_rate", "")).isdigit() else None}


def packet_times(url):
    """Every video packet's presentation time (reads the whole file): for frame count and timeline gaps."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", url], capture_output=True, text=True, timeout=3600)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[-200:] or "ffprobe packets failed")
    return sorted(float(x) for x in out.stdout.split() if x not in ("", "N/A"))


def decode_errors(url):
    """Full decode (CPU heavy): the decoder's error lines, empty when every frame decodes."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", url, "-map", "0:v:0", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=7200)
    return [l for l in out.stderr.splitlines() if l.strip()] + ([f"exit {out.returncode}"] if out.returncode else [])


def read_widths(text):
    """(frame numbers, widths) of a gripper csv (frame, width_m); unparseable values become None / NaN."""
    rows = list(csv.DictReader(text.splitlines()))
    frames, vals = [], []
    for r in rows:
        try:
            frames.append(int(r.get("frame")))
        except (TypeError, ValueError):
            frames.append(None)
        try:
            vals.append(float(r.get("width_m")))
        except (TypeError, ValueError):
            vals.append(float("nan"))
    return frames, vals


def parse_resolution(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return int(v[0]), int(v[1])
    m = re.match(r"^\s*(\d+)\s*[x×X,]\s*(\d+)\s*$", str(v or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


# ---------------------------------------------------------------- the checklist
def odd_ones(values):
    """The roles whose value differs from the value most roles share (all of them when no two agree)."""
    common, n = collections.Counter(values.values()).most_common(1)[0]
    return [r for r, v in values.items() if v != common] if n > 1 else list(values)


def check(store, rec, cfg, manual):
    res = {k: ("", "") for k in CHECK_IDS}  # id -> (status, value)
    culprits = {}  # id -> roles whose file is at fault (for the failures report)
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
    culprits["D1"] = missing + [b.split(":")[0] for b in bad]
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

    # D5 files: none empty, meta.files names the delivered files, one recording name per folder (+ W6 naming)
    gaps = [f"{r}: empty file" for r, n in rec.get("sizes", {}).items() if not n]
    if meta is not None:
        mf = meta.get("files") or {}
        for r in VIDEO_ROLES:
            actual = files[r].rsplit("/", 1)[-1] if r in files else None
            if mf.get(r) != actual:
                gaps.append(f"meta.files.{r} = {mf.get(r)!r}, delivered {actual!r}")
        for g in GRIPPERS:
            want = (meta.get("gripper_width") or {}).get(g)
            actual = files[f"{g}_gripper"].rsplit("/", 1)[-1] if f"{g}_gripper" in files else None
            if want is not None and want != actual:
                gaps.append(f"meta.gripper_width.{g} = {want!r}, delivered {actual!r}")
    if rec.get("stray"):
        gaps.append("files of another recording name in the folder: " + ", ".join(rec["stray"]))
    put("D5", "FAIL" if gaps else "PASS", "; ".join(gaps) or f"{len(files)} files, names match meta")
    ok_name = bool(REC_NAME.match(rec["rec"])) and rec["rec"].endswith(rec["episode"])
    put("W6", "PASS" if ok_name else "WARN", rec["rec"] + ("" if ok_name else
        " (expected <date>_<taskNN>_<episode>, or <taskNN>_<episode> without a date folder)"))

    # D4 gripper widths (+ W1 both grippers in use)
    lo, hi = cfg["gripper_width_m"]
    n_ref = (probes.get("head") or {}).get("frames")
    gaps, ranges, widths, texts = [], {}, {}, {}
    for g in GRIPPERS:
        key = files.get(f"{g}_gripper")
        if not key:
            gaps.append(f"{g}: csv missing")
            continue
        try:
            texts[g] = store.read_text(key)
            fr, w = read_widths(texts[g])
        except Exception as ex:
            gaps.append(f"{g}: unreadable ({ex})"[:80])
            continue
        n_g = (probes.get(g) or {}).get("frames") or n_ref
        if not w:
            gaps.append(f"{g}: empty")
            continue
        if n_g is not None and abs(len(w) - n_g) > cfg["gripper_rows_tolerance"]:
            gaps.append(f"{g}: {len(w)} rows, {n_g} video frames")
        if fr != list(range(len(fr))):
            gaps.append(f"{g}: frame column is not 0, 1, 2 ... without gaps")
        if any(math.isnan(x) for x in w):
            gaps.append(f"{g}: NaN widths")
        fin = [x for x in w if not math.isnan(x)]
        if fin and (min(fin) < lo or max(fin) > hi):
            gaps.append(f"{g}: width {min(fin):.3f}..{max(fin):.3f} m outside {lo}..{hi}")
        if fin:
            ranges[g] = (min(fin), max(fin))
            widths[g] = fin
    put("D4", "FAIL" if gaps else "PASS", "; ".join(gaps) or
        "; ".join(f"{g} {a:.3f}-{b:.3f} m" for g, (a, b) in ranges.items()))
    if len(ranges) == 2:
        idle = [g for g, (a, b) in ranges.items() if b - a < cfg["gripper_active_range_m"]]
        put("W1", "WARN" if idle else "PASS",
            (f"{', '.join(idle)} gripper barely moves (passive role allowed)" if idle else "both grippers open and close"))
    else:
        put("W1", "INFO", "gripper widths missing")

    # W9 jumps / W10 frozen stretches in the gripper widths (marker-tracking glitches or held values)
    jump_m, jump_n, flat_s = cfg["gripper_jump_m"], cfg["gripper_jump_count"], cfg["gripper_flat_s"]
    jmsg, fmsg, jbad, fbad = [], [], [], []
    for g, w in widths.items():
        steps = [abs(b - a) for a, b in zip(w, w[1:])]
        nj = sum(x > jump_m for x in steps)
        jmsg.append(f"{g} {nj} jumps > {jump_m * 1000:.0f} mm (max {max(steps, default=0) * 1000:.1f} mm)")
        if nj >= jump_n:
            jbad.append(g)
        run = best = 1
        for a, b in zip(w, w[1:]):
            run = run + 1 if a == b else 1
            best = max(best, run)
        fps_g = (probes.get(g) or {}).get("fps") or cfg["expected_fps"]
        fmsg.append(f"{g} longest unchanged {best / fps_g:.1f} s")
        if best / fps_g > flat_s:
            fbad.append(g)
    if widths:
        put("W9", "WARN" if jbad else "PASS", "; ".join(jmsg))
        put("W10", "WARN" if fbad else "PASS", "; ".join(fmsg) + (
            f" (over {flat_s} s: tracking lost and value held, or a passive gripper)" if fbad else ""))
        culprits["W9"], culprits["W10"] = [f"{g}_gripper" for g in jbad], [f"{g}_gripper" for g in fbad]
    else:
        put("W9", "INFO", "gripper widths missing")
        put("W10", "INFO", "gripper widths missing")

    # W8 sync method: the export's full sync (audio + wrist motion refinement), not audio alone
    want = cfg["sync_method_expected"]
    if meta is not None and isinstance(sync.get("method"), str):
        put("W8", "PASS" if want.lower() in sync["method"].lower() else "WARN", sync["method"]
            + ("" if want.lower() in sync["method"].lower() else f" (no {want}: sync less certain)"))

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
            culprits["V2"] = odd_ones(frames)
        if None not in durs.values() and f0:
            if (max(durs.values()) - min(durs.values())) * f0 > cfg["max_duration_diff_frames"] + 1e-6:
                msgs.append("durations " + ", ".join(f"{r} {d:.3f}s" for r, d in durs.items()))
        put("V2", "FAIL" if msgs else "PASS", "; ".join(msgs) or
            f"{frames['head']} frames in each, {durs['head']:.3f} s")
        starts = {r: p["start"] for r, p in got.items()}
        if None in starts.values() or not f0:
            put("V5", "FAIL", f"start time unknown {starts}")
        else:
            spread = (max(starts.values()) - min(starts.values())) * f0
            culprits["V5"] = odd_ones({r: round(v * f0) for r, v in starts.items()})
            put("V5", "FAIL" if spread > cfg["max_start_diff_frames"] + 1e-6 else "PASS",
                "start " + ", ".join(f"{r} {v:.3f}s" for r, v in starts.items()) + f" (spread {spread:.2f} frames)")
        msgs = []
        for r, p in got.items():
            if p["avg_fps"] is None or p["fps"] is None or abs(p["avg_fps"] - p["fps"]) > cfg["vfr_tolerance_fps"]:
                msgs.append(f"{r}: average {p['avg_fps']} vs nominal {p['fps']} fps")
            elif p["frames"] and p["duration"] and abs(p["frames"] / p["duration"] - p["fps"]) > cfg["vfr_tolerance_fps"]:
                msgs.append(f"{r}: {p['frames']} frames / {p['duration']:.3f} s = {p['frames'] / p['duration']:.3f} fps")
        put("V6", "FAIL" if msgs else "PASS", "; ".join(msgs) or "constant frame rate (header)")
        msgs = []
        for r, p in got.items():
            if p["codec"] not in cfg["video_codecs"]:
                msgs.append(f"{r}: codec {p['codec']}")
            want = parse_resolution((cams.get(r) or {}).get("resolution"))
            if want and (p["width"], p["height"]) != want:
                msgs.append(f"{r}: {p['width']}x{p['height']} vs meta {want[0]}x{want[1]}")
        put("V3", "FAIL" if msgs else "PASS", "; ".join(msgs) or
            f"{got['head']['codec']} {got['head']['width']}x{got['head']['height']}")
        kb = {r: p.get("kbps") for r, p in got.items()}
        low = [r for r, v in kb.items() if v is not None and v < cfg["min_video_kbps"]]
        culprits["W11"] = low
        put("W11", "WARN" if low else "PASS", ", ".join(f"{r} {v / 1000:.1f}" if v else f"{r} ?" for r, v in kb.items())
            + " Mbit/s" + (f" ({', '.join(low)} below {cfg['min_video_kbps'] / 1000:.0f}: lens blocked or dark?)" if low else ""))
    else:
        unreadable = [r for r in VIDEO_ROLES if r not in got]
        for k in ("V1", "V2", "V3", "V5", "V6"):
            put(k, "FAIL", f"{', '.join(unreadable)} missing or unreadable (see D1)")
            culprits[k] = unreadable
    if all(isinstance(idx.get(r), int) for r in VIDEO_ROLES):
        same = len({idx[r] for r in VIDEO_ROLES}) == 1
        put("V4", "PASS" if same else "FAIL", f"sync frame index {[idx[r] for r in VIDEO_ROLES]}"
            + ("" if same else " (files do not start at the same instant)"))
    else:
        put("V4", "FAIL", "no sync frame index per file")

    # V7 every packet read (--deep): count = header count, same in all three, no timeline gap, same first time
    if not cfg.get("_deep"):
        put("V7", "SKIP", "header only (run with --deep to read every frame's timestamp)")
    elif len(got) < 3:
        put("V7", "FAIL", "not all three videos readable (see D1)")
        culprits["V7"] = [r for r in VIDEO_ROLES if r not in got]
    else:
        msgs, info = [], {}
        f0 = got["head"]["fps"] or cfg["expected_fps"]
        for r in VIDEO_ROLES:
            try:
                t = packet_times(store.url(files[r]))
            except Exception as ex:
                msgs.append(f"{r}: {ex}"[:120])
                continue
            info[r] = t
            if got[r]["frames"] is not None and len(t) != got[r]["frames"]:
                msgs.append(f"{r}: {len(t)} packets, header says {got[r]['frames']}")
            gaps_ = [b - a for a, b in zip(t, t[1:])]
            if gaps_ and max(gaps_) * f0 > cfg["max_pts_gap_frames"]:
                msgs.append(f"{r}: timeline gap {max(gaps_) * 1000:.1f} ms (dropped frames)")
            if gaps_ and min(gaps_) <= 0:
                msgs.append(f"{r}: repeated timestamps")
        if len(info) == 3:
            if len({len(t) for t in info.values()}) != 1:
                msgs.append("packet counts " + ", ".join(f"{r} {len(t)}" for r, t in info.items()))
                culprits["V7"] = odd_ones({r: len(t) for r, t in info.items()})
            firsts = [t[0] for t in info.values() if t]
            if firsts and (max(firsts) - min(firsts)) * f0 > cfg["max_start_diff_frames"] + 1e-6:
                culprits["V7"] = sorted(set(culprits.get("V7", [])) | set(
                    odd_ones({r: round(t[0] * f0) for r, t in info.items() if t})))
                msgs.append("first timestamps " + ", ".join(f"{r} {t[0]:.3f}s" for r, t in info.items() if t))
        put("V7", "FAIL" if msgs else "PASS", "; ".join(msgs) or
            f"{len(info['head'])} packets each, no gaps, same first time")
    # V8 full decode (--decode): every frame of every view decodes without an error
    if not cfg.get("_decode"):
        put("V8", "SKIP", "not decoded (run with --decode)")
    elif len(got) < 3:
        put("V8", "FAIL", "not all three videos readable (see D1)")
        culprits["V8"] = [r for r in VIDEO_ROLES if r not in got]
    else:
        errs = {r: decode_errors(store.url(files[r])) for r in VIDEO_ROLES}
        bad = {r: e for r, e in errs.items() if e}
        culprits["V8"] = list(bad)
        put("V8", "FAIL" if bad else "PASS", "; ".join(f"{r}: {len(e)} errors, e.g. {e[0][:80]}" for r, e in bad.items())
            or "all frames decode")

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
    if files.get("mosaic"):
        try:
            mz = ffprobe(store.url(files["mosaic"]))
            nh = (got.get("head") or {}).get("frames")
            ok = nh is None or mz["frames"] == nh
            put("W5", "PASS" if ok else "WARN", f"mosaic {mz['codec']} {mz['frames']} frames"
                + ("" if ok else f", head {nh} (review video does not match)"))
        except Exception as ex:
            put("W5", "WARN", f"mosaic unreadable: {ex}"[:120])
    else:
        put("W5", "INFO", "no mosaic (optional)")

    row = {"task": rec["task"], "episode": rec["episode"], "n_cycles": "" if n is None else n, "count_source": src,
           "duration_s": "" if dur is None else round(dur, 2), "folder": rec["folder"], "_uris": rec.get("uris", {}),
           "_culprits": culprits,
           # for the checks across recordings (D6, W7)
           "_grip_key": hashlib.sha1("\0".join(texts.get(g, "") for g in GRIPPERS).encode()).hexdigest()
           if len(texts) == 2 else None,
           "_calib": {r: tuple(str((cams.get(r) or {}).get(k)) for k in ("fx", "fy", "cx", "cy")) for r in VIDEO_ROLES}}
    for k in CHECK_IDS:
        row[k], row[f"{k}_value"] = res[k]
    return set_verdict(row)


def set_verdict(row):
    fails = [f"{k}: {row[f'{k}_value']}" for k in CHECK_IDS if row.get(k) == "FAIL" and k in HARD]
    reviews = [f"{k}: {row[f'{k}_value']}" for k in CHECK_IDS if row.get(k) == "REVIEW"]
    row["verdict"] = "FAIL" if fails else ("REVIEW" if reviews else "PASS")
    row["reasons"] = " | ".join(fails or reviews)
    return row


def station_of(row):
    return row["task"].split("/")[0]


def cross_checks(rows):
    """Checks that compare recordings: D6 duplicate recordings, W7 calibration against the rest of the station."""
    rows = [r for r in rows if "D1" in r]  # skip crashed checks
    # D6: identical left + right gripper csv = the same recording delivered twice. The copy in a station folder
    # (first by path) is the original; every other copy fails.
    groups = collections.defaultdict(list)
    for r in rows:
        if r.get("_grip_key"):
            groups[r["_grip_key"]].append(r)
    for r in rows:
        r["D6"], r["D6_value"] = "PASS", "no other recording with the same gripper data"
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda r: (not STATION.match(station_of(r)), r["task"], r["episode"]))
        orig = g[0]
        orig["D6_value"] = "original; copies at " + ", ".join(f"{r['task']}/{r['episode']}" for r in g[1:])
        for r in g[1:]:
            r["D6"], r["D6_value"] = "FAIL", f"copy of {orig['task']}/{orig['episode']} (same gripper data): do not deliver twice"
    # W7: each wrist / head calibration against the one most recordings of the station use
    by_station = collections.defaultdict(list)
    for r in rows:
        by_station[station_of(r)].append(r)
    for sub in by_station.values():
        common = {v: collections.Counter(r["_calib"][v] for r in sub).most_common(1)[0][0] for v in VIDEO_ROLES}
        for r in sub:
            c = r["_calib"]
            if c["left"] == common["right"] and c["right"] == common["left"] and common["left"] != common["right"]:
                r["W7"], r["W7_value"] = "WARN", (f"left / right calibrations swapped vs the rest of the station "
                                                  f"(left fx {c['left'][0]}, right fx {c['right'][0]}): cameras or labels swapped?")
            elif any(c[v] != common[v] for v in VIDEO_ROLES):
                odd = [v for v in VIDEO_ROLES if c[v] != common[v]]
                r["W7"], r["W7_value"] = "INFO", f"{', '.join(odd)} calibration differs from the rest of the station"
            else:
                r["W7"], r["W7_value"] = "PASS", "same calibration as the rest of the station"
    for r in rows:
        set_verdict(r)


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


def load_env(path):
    """KEY=value lines of .env into os.environ (AWS_PROFILE, region), without overriding what the shell already set."""
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


def main():
    load_env(HERE / ".env")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, default=HERE / "configs" / "delivery_check.json")
    ap.add_argument("--source", help="s3://bucket/prefix/ or a local folder (default: config source)")
    ap.add_argument("--task", action="append", help="station1, station1/2026-11-21, station1/2026-11-21/task01 or task01")
    ap.add_argument("--limit", type=int, help="at most N recordings per task")
    ap.add_argument("--out", type=Path, help="per-recording CSV (default: config out_csv)")
    ap.add_argument("--deep", action="store_true",
                    help="V7: read every frame's timestamp of the three videos (reads the whole files; on S3 a download)")
    ap.add_argument("--decode", action="store_true", help="V8: decode every frame (CPU heavy; use with --task/--limit)")
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text())
    cfg["_deep"], cfg["_decode"] = a.deep, a.decode
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
                       "reasons": f"check crashed: {err!r}"[:300], "folder": r["folder"], "_uris": r.get("uris", {})}
            rows.append(row)
            if i % 50 == 0 or i == len(recs):
                print(f"  {i}/{len(recs)}", flush=True)
    rows.sort(key=lambda r: (r["task"], r["episode"]))
    cross_checks(rows)

    out = a.out or HERE / cfg["out_csv"]
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["task", "episode", "verdict", "reasons", "n_cycles", "count_source", "duration_s"] + \
           [c for k in CHECK_IDS for c in (k, f"{k}_value")] + ["folder"]
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    stem = out.with_suffix("")
    files_out = {k: Path(f"{stem}_{k}.csv") for k in ("summary", "failures", "deliverable")}
    files_out["report"] = Path(f"{stem}_report.md")

    # failures: one row per (recording, failed or review check), with the file(s) concerned and the reason
    def concerned(row, k, value):
        uris, kind = row.get("_uris", {}), CHECK_FILES.get(k, "recording")
        if row.get("_culprits", {}).get(k):
            roles = row["_culprits"][k]
        elif kind == "video":
            roles = [r for r in VIDEO_ROLES if re.search(rf"\b{r}\b", value)] or list(VIDEO_ROLES)
        elif kind == "gripper":
            roles = [f"{g}_gripper" for g in GRIPPERS if re.search(rf"\b{g}\b", value)] or [f"{g}_gripper" for g in GRIPPERS]
        elif kind in ("meta", "head", "vlm"):
            roles = [kind]
        else:
            return row["folder"] + "/"
        return " ".join(uris.get(r, f"{row['folder']}/<missing {r}>") for r in roles)
    fail_rows = []
    for row in rows:
        if row["verdict"] == "PASS":
            continue
        if "D1" not in row:  # the check itself crashed
            fail_rows.append({"task": row["task"], "episode": row["episode"], "verdict": row["verdict"], "check": "",
                              "check_name": "check crashed", "status": "FAIL", "files": row["folder"] + "/",
                              "reason": row["reasons"]})
            continue
        for k in CHECK_IDS:
            st = row.get(k)
            if (st == "FAIL" and k in HARD) or st == "REVIEW":
                fail_rows.append({"task": row["task"], "episode": row["episode"], "verdict": row["verdict"], "check": k,
                                  "check_name": CHECK_NAMES[k], "status": st,
                                  "files": concerned(row, k, row.get(f"{k}_value", "")), "reason": row.get(f"{k}_value", "")})
    with open(files_out["failures"], "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task", "episode", "verdict", "check", "check_name", "status", "files", "reason"])
        w.writeheader()
        w.writerows(fail_rows)

    # deliverable: every PASS recording, with its length
    hours = lambda rs: sum(float(r.get("duration_s") or 0) for r in rs) / 3600
    deliver = [r for r in rows if r["verdict"] == "PASS"]
    with open(files_out["deliverable"], "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task", "episode", "duration_s", "n_cycles", "count_source", "folder"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(deliver)

    # summary per task, per station and overall: recordings and hours by verdict
    def summary_row(level, name, sub):
        v = {x: [r for r in sub if r["verdict"] == x] for x in ("PASS", "REVIEW", "FAIL")}
        why = collections.Counter(k for r in sub for k in CHECK_IDS if r.get(k) == "FAIL" and k in HARD)
        return {"level": level, "name": name, "recordings": len(sub), "hours": round(hours(sub), 3),
                "deliverable": len(v["PASS"]), "deliverable_hours": round(hours(v["PASS"]), 3),
                "review": len(v["REVIEW"]), "review_hours": round(hours(v["REVIEW"]), 3),
                "fail": len(v["FAIL"]), "fail_hours": round(hours(v["FAIL"]), 3),
                "deliverable_pct": round(100 * len(v["PASS"]) / len(sub), 1) if sub else 0,
                "fail_checks": ", ".join(f"{k} {CHECK_NAMES[k]} x{c}" for k, c in why.most_common())}
    summ = [summary_row("task", t, [r for r in rows if r["task"] == t]) for t in sorted({r["task"] for r in rows})]
    stations = sorted({r["task"].split("/")[0] for r in rows})
    summ += [summary_row("station", st, [r for r in rows if r["task"].split("/")[0] == st]) for st in stations]
    summ.append(summary_row("all", "ALL", rows))
    with open(files_out["summary"], "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)

    # report: the same in one readable page
    tot = summ[-1]
    md = [f"# UMI delivery check: {src}", "",
          f"Checked against DataPRD1019 v1.1 (docs/UMI_delivery_checklist.md); "
          f"{'header + every frame timestamp' if a.deep else 'header only'}{', full decode' if a.decode else ''}.",
          *([] if a.deep else ["Not checked in this run: dropped frames inside a file (V7, run with --deep)."]),
          *([] if a.decode else ["Not checked in this run: corrupt frames (V8, run with --decode). "
                                 "Deliverable means: passes every check that ran."]), "",
          f"**Deliverable: {tot['deliverable']} of {tot['recordings']} recordings, {tot['deliverable_hours']:.2f} h "
          f"of {tot['hours']:.2f} h** ({tot['deliverable_pct']}%). Review: {tot['review']} ({tot['review_hours']:.2f} h). "
          f"Fail: {tot['fail']} ({tot['fail_hours']:.2f} h).", "",
          "| Level | Name | Recordings | Hours | Deliverable | Deliverable h | Review | Review h | Fail | Fail h | Fail checks |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {x['level']} | {x['name']} | {x['recordings']} | {x['hours']:.2f} | {x['deliverable']} | "
           f"{x['deliverable_hours']:.2f} | {x['review']} | {x['review_hours']:.2f} | {x['fail']} | {x['fail_hours']:.2f} | "
           f"{x['fail_checks']} |" for x in summ]
    reasons = collections.Counter((f["check"], f["check_name"], f["status"]) for f in fail_rows)
    md += ["", "## Why recordings are not deliverable", "", "| Check | What | Status | Recordings |", "|---|---|---|---|"]
    md += [f"| {k} | {n} | {st} | {c} |" for (k, n, st), c in reasons.most_common()]
    md += ["", f"Every failed or review check, with the S3 file and the reason: `{files_out['failures'].name}`. "
           f"Deliverable recordings: `{files_out['deliverable'].name}`. All checks per recording: `{out.name}`.", ""]
    files_out["report"].write_text("\n".join(md))

    print(f"{'level':8s} {'name':32s} {'n':>5s} {'hours':>7s} {'deliv':>6s} {'deliv_h':>8s} {'review':>6s} {'fail':>5s}  fail checks")
    for x in summ:
        print(f"{x['level']:8s} {x['name']:32s} {x['recordings']:5d} {x['hours']:7.2f} {x['deliverable']:6d} "
              f"{x['deliverable_hours']:8.2f} {x['review']:6d} {x['fail']:5d}  {x['fail_checks'][:80]}")
    print("-> " + "\n-> ".join(str(x) for x in (out, *files_out.values())))


if __name__ == "__main__":
    main()
