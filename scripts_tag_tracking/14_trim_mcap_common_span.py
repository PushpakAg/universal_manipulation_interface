"""
Trim delivery MCAP files to the time span all topics share (PRD U2: same time span,
first and last frame of the three views each within 1 frame = 16.7 ms).

Why: 07_export_mcap.py starts every video at the keyframe before the episode (GoPro:
one keyframe per second), so the three videos start up to ~1 s apart and before the
first pose / gripper / IMU message. This script cuts all topics to one window:

  start = latest of: first gripper message, first message of each video topic
  end   = earliest of: last gripper message, last message of each video topic

  video topics    first frame = the frame nearest to start, last frame = the frame nearest to end
                  (so every camera starts and ends within half a frame of the window)
  other topics    messages in [start - dt/2, end + dt/2]   (dt = 1 / video_fps)
  demo start/end  kept (one message each), time clamped into the window

Video is re-encoded only where it must be. The streams are H.265 with one keyframe per
second and no B-frames:
  - the end is a plain cut (drop trailing frames),
  - the start: if the first kept frame is a keyframe, nothing is re-encoded; otherwise the
    frames from the first kept frame up to the next keyframe (at most 60 frames) are decoded
    and re-encoded (libx265, same size, same colour tags, first frame IDR), everything after
    the next keyframe is copied unchanged.

Metadata: all records are copied. 'recording' episode_length and robot{i}_pose_missing_steps
are recomputed for the window. 'sync' (camera{c}_sync_frame = frame of the episode's first step
in the source recording) is kept unchanged: it still names that source frame. A new 'trim'
record says what was cut. Input files are never modified or deleted; output goes to a new directory.

python scripts_tag_tracking/14_trim_mcap_common_span.py -i data/s3/task01 -o data/s3_trimmed/task01 --episodes 1,10
"""
# %%
import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.append(ROOT_DIR)
os.chdir(ROOT_DIR)

# %%
import base64
import collections
import concurrent.futures
import json
import pathlib
from fractions import Fraction
import av
import click
import numpy as np
from mcap.reader import make_reader
from mcap.writer import Writer, CompressionType

VIDEO = '/cameras/camera{}/video'
SPREAD_LIMIT_MS = 16.7
SOURCE_FPS_DEFAULT = 60000 / 1001


def keyframe(message: dict) -> bool:
    """
    First slice NAL of an Annex B frame is an HEVC IRAP picture (IDR_W_RADL 19, IDR_N_LP 20, CRA 21).
    Parameter sets, AUD and SEI (types >= 32 or non-slice) before it are skipped.
    """
    head = base64.b64decode(message['data'][:10924])
    i = 0
    while True:
        i = head.find(b'\x00\x00\x01', i)
        if i < 0 or i + 3 >= len(head):
            return False
        nal_type = (head[i + 3] >> 1) & 0x3f
        if nal_type < 32:
            return nal_type in (19, 20, 21)
        i += 3


def scan(path: str):
    """
    Returns reader info: per topic list of log times (ns); per video topic keyframe flags;
    metadata records; header.
    """
    times = collections.defaultdict(list)
    keys = collections.defaultdict(list)
    with open(path, 'rb') as stream:
        reader = make_reader(stream)
        header = reader.get_header()
        for schema, channel, message in reader.iter_messages():
            times[channel.topic].append(message.log_time)
            if channel.topic.startswith('/cameras/'):
                keys[channel.topic].append(keyframe(json.loads(message.data)))
        metadata = [(m.name, dict(m.metadata)) for m in reader.iter_metadata()]
    return times, keys, metadata, header


def window(times: dict, dt_ns: int, n_cameras: int):
    """(start, end) ns shared by all gripper and video topics."""
    video = [VIDEO.format(c) for c in range(n_cameras)]
    gripper = [t for t in times if t.endswith('/gripper/state')]
    start = max([times[t][0] for t in video + gripper])
    end = min([times[t][-1] for t in video + gripper])
    assert end > start, f"no common span: start {start} end {end}"
    return start, end


def nearest(times: list, t: int) -> int:
    i = int(np.searchsorted(times, t))
    if i == 0:
        return 0
    if i == len(times):
        return len(times) - 1
    return i if abs(times[i] - t) < abs(times[i - 1] - t) else i - 1


def decode(packets: list):
    context = av.CodecContext.create('hevc', 'r')
    frames = []
    for data in packets:
        frames.extend(context.decode(av.Packet(data)))
    frames.extend(context.decode(None))
    assert len(frames) == len(packets), f"decoded {len(frames)} of {len(packets)} packets"
    return frames, context


def x265_color_params(context) -> str:
    """Carry the source colour tags (VUI) over so the re-encoded part looks the same."""
    parts = []
    for name, value in (('colorprim', context.color_primaries), ('transfer', context.color_trc),
            ('colormatrix', context.colorspace)):
        if value is not None and int(value) not in (0, 2):
            parts.append(f'{name}={int(value)}')
    if context.color_range is not None and int(context.color_range) in (1, 2):
        parts.append('range=' + ('limited' if int(context.color_range) == 1 else 'full'))
    return ':'.join(parts)


def reencode_head(packets: list, first_kept: int, crf: int, preset: str):
    """
    packets: Annex B frames [keyframe .. next keyframe) of one camera; first_kept: index inside
    packets of the first frame to keep (> 0). Returns (Annex B frames for packets[first_kept:], min PSNR dB).
    """
    frames, source_context = decode(packets)
    frames = frames[first_kept:]
    encoder = av.CodecContext.create('libx265', 'w')
    encoder.width, encoder.height, encoder.pix_fmt = frames[0].width, frames[0].height, frames[0].format.name   # yuvj420p = full range, no level conversion
    encoder.time_base = Fraction(1001, 60000)
    encoder.framerate = Fraction(60000, 1001)
    params = ['log-level=error', 'bframes=0', 'rc-lookahead=0', 'repeat-headers=1', 'aud=1', 'info=0',
        'keyint=100000', 'min-keyint=100000', 'scenecut=0', x265_color_params(source_context)]
    encoder.options = {'preset': preset, 'crf': str(crf), 'x265-params': ':'.join(p for p in params if p)}
    out = []
    for i, frame in enumerate(frames):
        frame.pts = i
        frame.pict_type = av.video.frame.PictureType.NONE
        out.extend(bytes(p) for p in encoder.encode(frame))
    out.extend(bytes(p) for p in encoder.encode(None))
    assert len(out) == len(frames), f"encoded {len(out)} packets for {len(frames)} frames"
    new, _ = decode(out)
    psnr = []
    for a, b in zip(frames, new):
        ya, yb = a.to_ndarray(format='gray').astype(np.float64), b.to_ndarray(format='gray').astype(np.float64)
        mse = max(float(np.mean((ya - yb) ** 2)), 1e-9)
        psnr.append(10 * np.log10(255 ** 2 / mse))
    return out, min(psnr)


def trim_episode(src: str, dst: str, crf: int, preset: str) -> dict:
    times, keys, metadata, header = scan(src)
    records = dict(metadata)
    recording = records['recording']
    n_cameras = int(recording['n_cameras'])
    dt_ns = int(round(1e9 / float(recording['video_fps'])))
    start, end = window(times, dt_ns, n_cameras)
    lo, hi = start - dt_ns // 2, end + dt_ns // 2

    # per camera: kept frame range [first, last], keyframe before it, next keyframe after first
    plan = {}
    for c in range(n_cameras):
        topic = VIDEO.format(c)
        first, last = nearest(times[topic], start), nearest(times[topic], end)
        kf = np.flatnonzero(keys[topic])
        before = int(kf[kf <= first][-1])
        after = kf[kf > first]
        stop = int(min(after[0], last + 1)) if len(after) else last + 1
        plan[topic] = dict(first=first, last=last, before=before, stop=stop, recode=first != before)

    # frames to re-encode: Annex B data of [before, stop) for cameras whose first kept frame is not a keyframe
    recoded = {}
    stats = {}
    need = {t: p for t, p in plan.items() if p['recode']}
    if need:
        data = collections.defaultdict(list)
        counter = collections.Counter()
        with open(src, 'rb') as stream:
            for schema, channel, message in make_reader(stream).iter_messages(topics=list(need)):
                i = counter[channel.topic]
                counter[channel.topic] += 1
                p = need[channel.topic]
                if p['before'] <= i < p['stop']:
                    data[channel.topic].append(base64.b64decode(json.loads(message.data)['data']))
        for topic, p in need.items():
            out, psnr = reencode_head(data[topic], p['first'] - p['before'], crf, preset)
            recoded[topic] = out
            stats[topic] = {'reencoded_frames': len(out), 'min_psnr_db': round(psnr, 2)}

    counts = collections.Counter()
    kept = collections.Counter()
    with open(src, 'rb') as fin, open(dst, 'wb') as fout:
        reader = make_reader(fin)
        writer = Writer(fout, compression=CompressionType.ZSTD)
        writer.start(profile=header.profile, library=header.library + ' + 14_trim_mcap_common_span')
        summary = reader.get_summary()
        schema_ids = {s.id: writer.register_schema(name=s.name, encoding=s.encoding, data=s.data)
            for s in summary.schemas.values()}
        channel_ids = {ch.id: writer.register_channel(topic=ch.topic, message_encoding=ch.message_encoding,
            schema_id=schema_ids[ch.schema_id], metadata=dict(ch.metadata)) for ch in summary.channels.values()}
        for schema, channel, message in reader.iter_messages():
            topic = channel.topic
            i = counts[topic]
            counts[topic] += 1
            data, log_time = message.data, message.log_time
            if topic in plan:
                p = plan[topic]
                if i < p['first'] or i > p['last']:
                    continue
                if topic in recoded and i < p['stop']:
                    body = json.loads(data)
                    body['data'] = base64.b64encode(recoded[topic][i - p['first']]).decode()
                    data = json.dumps(body).encode()
            elif 'demo_' in topic:
                log_time = min(max(log_time, start), end)
            elif not lo <= log_time <= hi:
                continue
            kept[topic] += 1
            writer.add_message(channel_ids[channel.id], log_time=log_time, publish_time=log_time, data=data)
        steps = kept['robot0/gripper/state']
        trim = {
            'window_start_ns': str(start), 'window_end_ns': str(end),
            'original_episode_length': recording['episode_length'], 'episode_length': str(steps),
            'rule': 'start = latest first gripper/video message, end = earliest last gripper/video message; '
                'video nearest frame, other topics within half a frame',
        }
        for c in range(n_cameras):
            p = plan[VIDEO.format(c)]
            trim[f'camera{c}_frames_dropped_start'] = str(p['first'])
            trim[f'camera{c}_frames_dropped_end'] = str(len(times[VIDEO.format(c)]) - 1 - p['last'])
            trim[f'camera{c}_reencoded_frames'] = str(stats.get(VIDEO.format(c), {}).get('reencoded_frames', 0))
        recording = dict(recording, episode_length=str(steps))
        for g in range(int(recording['n_grippers'])):
            recording[f'robot{g}_pose_missing_steps'] = str(steps - kept[f'robot{g}/eef/pose'])
        records['recording'] = recording
        for name, record in records.items():          # same order as the source
            writer.add_metadata(name, record)
        writer.add_metadata('trim', trim)
        writer.finish()
    return {'plan': plan, 'stats': stats, 'steps': steps}


def check(path: str) -> dict:
    """First/last time spread of the three views (U2), time span of every topic, decode of every video."""
    times, keys, metadata, _ = scan(path)
    n_cameras = int(dict(metadata)['recording']['n_cameras'])
    video = [VIDEO.format(c) for c in range(n_cameras)]
    first = [times[t][0] for t in video]
    last = [times[t][-1] for t in video]
    result = {
        'first_spread_ms': (max(first) - min(first)) / 1e6,
        'last_spread_ms': (max(last) - min(last)) / 1e6,
        'first_is_keyframe': all(keys[t][0] for t in video),
        'topic_span_ms': {t: ((v[0] - min(first)) / 1e6, (v[-1] - min(last)) / 1e6) for t, v in times.items()},
        'frames': {t: len(times[t]) for t in video},
    }
    decoded = {}
    for c, topic in enumerate(video):
        context = av.CodecContext.create('hevc', 'r')
        n = 0
        with open(path, 'rb') as stream:
            for schema, channel, message in make_reader(stream).iter_messages(topics=[topic]):
                for _ in context.decode(av.Packet(base64.b64decode(json.loads(message.data)['data']))):
                    n += 1
        n += sum(1 for _ in context.decode(None))
        decoded[topic] = n
    result['decoded_frames'] = decoded
    result['ok'] = (result['first_spread_ms'] <= SPREAD_LIMIT_MS and result['last_spread_ms'] <= SPREAD_LIMIT_MS
        and result['first_is_keyframe'] and decoded == result['frames'])
    return result


def run(src, dst, crf, preset):
    info = trim_episode(src, dst, crf, preset)
    return src, dst, info, check(dst)


@click.command()
@click.option('-i', '--input', required=True, help='directory with episode_*.mcap')
@click.option('-o', '--output', required=True, help='new directory for the trimmed files (existing files are not overwritten)')
@click.option('--episodes', default=None, help='comma separated episode numbers, default all')
@click.option('--crf', default=18, show_default=True, help='x265 quality of the re-encoded head of each video')
@click.option('--preset', default='medium', show_default=True)
@click.option('-j', '--jobs', default=1, show_default=True, help='episodes in parallel (x265 already uses several cores)')
def main(input, output, episodes, crf, preset, jobs):
    input, output = pathlib.Path(input), pathlib.Path(output)
    files = sorted(input.glob('episode_*.mcap'))
    if episodes:
        wanted = {int(e) for e in episodes.split(',')}
        files = [f for f in files if int(f.stem.split('_')[1]) in wanted]
    assert files, f"no episodes in {input}"
    output.mkdir(parents=True, exist_ok=True)
    todo = []
    for f in files:
        if output.joinpath(f.name).exists():
            print(f"skip {f.name}: output exists")
        else:
            todo.append(f)
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run, str(f), str(output.joinpath(f.name)), crf, preset) for f in todo]
        for future in concurrent.futures.as_completed(futures):
            src, dst, info, result = future.result()
            re = {t.split('/')[2]: s for t, s in info['stats'].items()}
            print(f"{pathlib.Path(src).name}: {'OK' if result['ok'] else 'FAIL'}  steps {info['steps']}  "
                f"first spread {result['first_spread_ms']:.1f} ms  last spread {result['last_spread_ms']:.1f} ms  "
                f"frames {list(result['frames'].values())}  re-encoded {re or 'none'}")


if __name__ == '__main__':
    main()
