"""
Tests of tag_tracking_v2: infrastructure (runner, fsutil, s3 helpers), pipeline planning, process_station
logic, MCAP helpers, video chunking and tag detection on a synthetic video.
No network, no real data. Run: .venv/bin/python -m pytest tag_tracking_v2/tests -q
"""
import hashlib
import json
import os
import pathlib
import pickle
import sys
import tempfile
import time

import numpy as np
import pytest

V2 = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V2))
sys.path.insert(0, str(V2 / 'scripts_tag_tracking'))
from tt2.bootstrap import setup_paths
setup_paths(chdir_to_repo=False)

from tt2 import s3, fsutil, runner
from tt2.errors import PipelineError, InputError, require


# ---------- runner
def test_runner_ok_and_log(tmp_path):
    r = runner.run_command('echo', [sys.executable, '-c', 'print("hello"); print("bye")'], tmp_path / 'l' / 'echo.log', console=False)
    assert r.ok and r.returncode == 0
    text = (tmp_path / 'l' / 'echo.log').read_text()
    assert 'hello' in text and 'bye' in text and text.startswith(sys.executable)
    assert r.tail[-1] == 'bye'


def test_runner_child_path_starts_with_own_interpreter(tmp_path):
    code = 'import os,sys; print(os.environ["PATH"].split(os.pathsep)[0] == os.path.dirname(os.path.abspath(sys.executable)))'
    r = runner.run_command('path', [sys.executable, '-c', code], tmp_path / 'p.log', env={'PATH': '/usr/bin'}, console=False)
    assert r.tail[-1] == 'True'


def test_runner_failure_reports_last_line(tmp_path):
    r = runner.run_command('bad', [sys.executable, '-c', 'import sys; print("boom"); sys.exit(3)'], tmp_path / 'bad.log', console=False)
    assert not r.ok and r.returncode == 3
    with pytest.raises(PipelineError) as e:
        r.raise_for_status()
    assert 'boom' in str(e.value) and 'bad.log' in str(e.value)


def test_runner_timeout_terminates(tmp_path):
    t = time.time()
    r = runner.run_command('slow', [sys.executable, '-c', 'import time; time.sleep(60)'], tmp_path / 's.log', timeout=1, console=False)
    assert r.timed_out and not r.ok and time.time() - t < 30
    with pytest.raises(PipelineError):
        r.raise_for_status()


def test_runner_missing_executable(tmp_path):
    r = runner.run_command('none', ['/nonexistent/binary'], tmp_path / 'n.log', console=False)
    assert r.returncode == 127 and not r.ok


def test_runner_progress_bar_chunks(tmp_path):
    code = 'import sys,time\nfor i in range(3):\n    sys.stdout.write("\\rstep %d" % i); sys.stdout.flush()\nprint()'
    r = runner.run_command('bar', [sys.executable, '-c', code], tmp_path / 'b.log', console=False)
    assert r.ok and r.tail[-1] == 'step 2'


# ---------- fsutil
def test_atomic_write_replaces_and_cleans_on_error(tmp_path):
    p = tmp_path / 'a.pkl'
    fsutil.atomic_pickle_dump({'x': 1}, p)
    assert pickle.load(p.open('rb')) == {'x': 1}
    with pytest.raises(RuntimeError):
        with fsutil.atomic_path(p) as tmp:
            tmp.write_bytes(b'partial')
            raise RuntimeError('crash')
    assert pickle.load(p.open('rb')) == {'x': 1}          # old file intact
    assert [x.name for x in tmp_path.iterdir()] == ['a.pkl']  # no temp left
    assert not list(tmp_path.glob('*.pkl.tmp*'))


def test_atomic_temp_not_matched_by_glob(tmp_path):
    with fsutil.atomic_path(tmp_path / 'e.mcap') as tmp:
        tmp.write_bytes(b'x')
        assert not list(tmp_path.glob('*.mcap'))


def test_swap_directory_keeps_and_restores(tmp_path):
    old, new = tmp_path / 'dataset_mcap', tmp_path / 'dataset_mcap.tmp'
    old.mkdir(); (old / 'a.mcap').write_bytes(b'old')
    new.mkdir(); (new / 'b.mcap').write_bytes(b'new')
    archived = fsutil.swap_directory(new, old, str(old))
    assert (old / 'b.mcap').read_bytes() == b'new' and (pathlib.Path(archived) / 'a.mcap').read_bytes() == b'old'
    # failure: new dir missing -> old restored
    with pytest.raises(OSError):
        fsutil.swap_directory(tmp_path / 'missing', old, str(old))
    assert (old / 'b.mcap').read_bytes() == b'new'


def test_fingerprint_changes_with_content_and_values(tmp_path):
    f = tmp_path / 'c.yaml'; f.write_text('a: 1')
    a = fsutil.fingerprint([f], ['x'])
    assert a == fsutil.fingerprint([f], ['x'])
    f.write_text('a: 2')
    assert a != fsutil.fingerprint([f], ['x'])
    assert fsutil.fingerprint([f], ['x']) != fsutil.fingerprint([f], ['y'])


# ---------- s3 helpers (no network)
def test_split_and_errors():
    assert s3.split('s3://b/p/q/') == ('b', 'p/q')
    with pytest.raises(PipelineError):
        s3.split('http://x')


def _manual_multipart_etag(data: bytes, part: int) -> str:
    digests = [hashlib.md5(data[i:i + part]).digest() for i in range(0, len(data), part)]
    return f"{hashlib.md5(b''.join(digests)).hexdigest()}-{len(digests)}"


def test_md5_etag_single_and_multipart(tmp_path):
    f = tmp_path / 'f.bin'
    data = os.urandom(1000)
    f.write_bytes(data)
    assert s3.md5_etag(f) == hashlib.md5(data).hexdigest()
    for size, part in [(1000, 300), (900, 300), (1, 300)]:
        f.write_bytes(data[:size])
        assert s3.md5_etag(f, part_size=part, threshold=1) == _manual_multipart_etag(data[:size], part), (size, part)


class FakeClient:
    def __init__(self, objects, etag_wrong=False, kms=False):
        self.objects, self.etag_wrong, self.kms = objects, etag_wrong, kms
    def upload_file(self, path, bucket, key, Config=None):
        self.objects[key] = pathlib.Path(path).read_bytes()
    def head_object(self, Bucket, Key):
        data = self.objects[Key]
        out = {'ContentLength': len(data), 'ETag': '"%s"' % ('0' * 32 if self.etag_wrong else hashlib.md5(data).hexdigest())}
        if self.kms:
            out['ServerSideEncryption'] = 'aws:kms'
        return out


def test_upload_verified(tmp_path, monkeypatch):
    f = tmp_path / 'e.mcap'; f.write_bytes(b'abc' * 100)
    monkeypatch.setattr(s3, 'make_client', lambda profile=None: FakeClient({}))
    assert s3.upload_verified(f, 's3://b/x/e.mcap') == 'md5'
    monkeypatch.setattr(s3, 'make_client', lambda profile=None: FakeClient({}, etag_wrong=True))
    with pytest.raises(PipelineError):
        s3.upload_verified(f, 's3://b/x/e.mcap')
    monkeypatch.setattr(s3, 'make_client', lambda profile=None: FakeClient({}, etag_wrong=True, kms=True))
    assert 'size only' in s3.upload_verified(f, 's3://b/x/e.mcap')


# ---------- pipeline planning
def test_pipeline_plan_cascade(tmp_path):
    import run_tag_tracking_pipeline as P
    session = tmp_path / 's'; (session / 'raw_videos').mkdir(parents=True); (session / 'logs').mkdir()
    (session / 'raw_videos' / 'a.MP4').write_bytes(b'v')
    cfg = tmp_path / 'c.yaml'; cfg.write_text('x: 1')
    script = tmp_path / 'step.py'; script.write_text('pass')
    steps = {n: (script, [n]) for n in P.STEP_NAMES}
    order = list(enumerate(P.STEP_NAMES))
    skip = {'render': '--no_render'}
    log_dir = session / 'logs'
    plan = P.plan_execution(order, steps, skip, True, log_dir, [cfg], session)
    assert all(v[0] in ('run', 'skip') for v in plan.values())
    for n in P.STEP_NAMES:                     # mark all done with their fingerprints
        if plan[n][0] == 'run':
            P.mark_done(log_dir, n, plan[n][1])
    plan2 = P.plan_execution(order, steps, skip, True, log_dir, [cfg], session)
    assert all(v[0] in ('cached', 'skip') for v in plan2.values())
    # a config change makes the FIRST step run and then every later one (cascade)
    cfg.write_text('x: 2')
    plan3 = P.plan_execution(order, steps, skip, True, log_dir, [cfg], session)
    assert all(plan3[n][0] == 'run' for n in P.STEP_NAMES if n != 'render')
    # without --resume everything runs
    plan4 = P.plan_execution(order, steps, skip, False, log_dir, [cfg], session)
    assert all(plan4[n][0] == 'run' for n in P.STEP_NAMES if n != 'render')


def test_pipeline_cascade_from_middle(tmp_path):
    import run_tag_tracking_pipeline as P
    session = tmp_path / 's'; (session / 'raw_videos').mkdir(parents=True); (session / 'logs').mkdir()
    cfg = tmp_path / 'c.yaml'; cfg.write_text('x')
    script = tmp_path / 'step.py'; script.write_text('pass')
    steps = {n: (script, [n]) for n in P.STEP_NAMES}
    order = list(enumerate(P.STEP_NAMES))
    plan = P.plan_execution(order, steps, {}, True, session / 'logs', [cfg], session)
    for n in P.STEP_NAMES:
        P.mark_done(session / 'logs', n, plan[n][1])
    # one step's state removed: it and everything after run, everything before is cached
    P.state_path(session / 'logs', 'track_bodies').unlink()
    plan = P.plan_execution(order, steps, {}, True, session / 'logs', [cfg], session)
    i = P.STEP_NAMES.index('track_bodies')
    assert all(plan[n][0] == 'cached' for n in P.STEP_NAMES[:i])
    assert all(plan[n][0] == 'run' for n in P.STEP_NAMES[i:])


def test_pipeline_skip_reasons():
    import run_tag_tracking_pipeline as P
    s = P.skip_reasons({'setup_calibration': 1, 'episodes': 1, 'gripper_imu': 1, 'head_imu': 1}, True)
    assert s['use_setup'] is None and s['calibrate_bodies'] and s['gripper_tcp'] and s['render'] == '--no_render'
    assert s['sync_wrists'] is None and s['trim_docking'] is None
    s = P.skip_reasons({}, False)
    assert s['use_setup'] and s['calibrate_bodies'] is None and s['sync_wrists'] and s['fuse_grippers']


def test_pipeline_run_stages_overlap_and_failure(tmp_path):
    import run_tag_tracking_pipeline as P
    log_dir = tmp_path / 'logs'; log_dir.mkdir()
    # each step records when it started and ended; overlap is checked from those intervals, not from elapsed time
    ok = tmp_path / 'ok.py'
    ok.write_text('import sys, time\nt0 = time.time(); time.sleep(1.0)\n'
        'open(sys.argv[1], "w").write(f"{t0} {time.time()}")')
    bad = tmp_path / 'bad.py'; bad.write_text('import sys; print("nope"); sys.exit(2)')
    steps = {'imu': (ok, [tmp_path / 'imu.t']), 'wrist_tags': (ok, [tmp_path / 'wrist.t']), 'gripper_range': (bad, [])}
    order = [(1, 'imu'), (2, 'wrist_tags'), (3, 'gripper_range')]
    plan = {n: ('run', 'fp') for _, n in order}
    records = {}
    with pytest.raises(PipelineError) as e:
        P.run_stages(tmp_path, order, steps, plan, log_dir, 60, True, tmp_path / 't.json', records)
    assert 'gripper_range' in str(e.value) and 'nope' in str(e.value)
    (a0, a1), (b0, b1) = [tuple(map(float, (tmp_path / f).read_text().split())) for f in ('imu.t', 'wrist.t')]
    assert max(a0, b0) < min(a1, b1)                    # the two intervals overlap: they ran at the same time
    assert records['imu']['returncode'] == 0 and records['gripper_range']['returncode'] == 2
    assert json.loads((tmp_path / 't.json').read_text())
    assert P.is_done(log_dir, 'imu', 'fp') and not P.is_done(log_dir, 'gripper_range', 'fp')
    # without overlap the intervals are disjoint
    records = {}
    with pytest.raises(PipelineError):
        P.run_stages(tmp_path, order, steps, plan, log_dir, 60, False, tmp_path / 't2.json', records)
    (a0, a1), (b0, b1) = [tuple(map(float, (tmp_path / f).read_text().split())) for f in ('imu.t', 'wrist.t')]
    assert a1 <= b0 or b1 <= a0


# ---------- process_station
def make_session(root: pathlib.Path) -> pathlib.Path:
    s = root.joinpath('task01')
    for d in ['raw_videos/gripper_calibration', 'demos/demo_A', 'demos/gripper_calibration_A', 'dataset_mcap', 'tag_tracking', 'logs']:
        s.joinpath(d).mkdir(parents=True)
    s.joinpath('demos/demo_A/raw_video.mp4').write_bytes(b'v' * 100)
    s.joinpath('demos/demo_A/tag_corners.pkl').write_bytes(b'x')
    s.joinpath('demos/gripper_calibration_A/raw_video.mp4').write_bytes(b'v' * 50)
    s.joinpath('raw_videos/GX01.MP4').symlink_to('../demos/demo_A/raw_video.mp4')
    s.joinpath('raw_videos/gripper_calibration/GX02.MP4').symlink_to('../../demos/gripper_calibration_A/raw_video.mp4')
    s.joinpath('raw_videos/pairs.csv').write_text('type\n')
    s.joinpath('dataset_mcap/episode_000000.mcap').write_bytes(b'm' * 10)
    s.joinpath('dataset_mcap/episode_000001.mcap').write_bytes(b'm' * 20)
    s.joinpath('dataset_plan.pkl').write_bytes(b'p')
    return s


def test_cleanup(tmp_path):
    import process_station
    s = make_session(tmp_path)
    process_station.s3_sizes = lambda url: {'episode_000000.mcap': 10}
    assert 'skipped' in process_station.cleanup(s, 's3://b/x/task01')
    process_station.s3_sizes = lambda url: {'episode_000000.mcap': 10, 'episode_000001.mcap': 19}
    assert 'skipped' in process_station.cleanup(s, 's3://b/x/task01')
    assert s.joinpath('demos/demo_A/raw_video.mp4').is_file() and len(list(s.rglob('*.mcap'))) == 2
    process_station.s3_sizes = lambda url: {'episode_000000.mcap': 10, 'episode_000001.mcap': 20, 'other': 1}
    done = process_station.cleanup(s, 's3://b/x/task01')
    assert 'deleted 2 videos, 2 raw_videos entries, 2 MCAP files' in done, done
    assert not list(s.rglob('*.mp4')) and not list(s.rglob('*.MP4')) and not list(s.rglob('*.mcap'))
    for kept in ['raw_videos/pairs.csv', 'demos/demo_A/tag_corners.pkl', 'dataset_plan.pkl']:
        assert s.joinpath(kept).is_file(), kept
    assert 'skipped' in process_station.cleanup(s, 's3://b/x/task01')


def test_station_job_local_and_errors(tmp_path):
    import process_station
    root = tmp_path / 'station3' / 'industrial_data'
    for t in ['task01', 'task02']:
        root.joinpath(t, 'raw_videos').mkdir(parents=True)
    root.joinpath('notes').mkdir()
    config = tmp_path / 'config.yaml'; config.write_text('x: 1')
    job = process_station.station_job(str(root), str(config), None, None, False, None, False)
    assert job['names'] == ['task01', 'task02'] and job['name'] == 'station3'
    assert process_station.station_job(str(root), str(config), None, 'task02', False, None, False)['names'] == ['task02']
    with pytest.raises(InputError):
        process_station.station_job(str(root), str(config), None, 'task09', False, None, False)
    with pytest.raises(InputError):
        process_station.station_job(str(root), str(config), None, None, False, 's3://b/x', False)   # upload without mcap
    with pytest.raises(InputError):
        process_station.station_job(str(root), str(config), None, None, True, 's3://b/x', True)     # cleanup on local sessions
    with pytest.raises(PipelineError):
        process_station.station_job(str(root), str(tmp_path / 'missing.yaml'), None, None, False, None, False)


def test_plan_yield_and_gates(tmp_path):
    import process_station
    s = tmp_path / 'task'; (s / 'tag_tracking').mkdir(parents=True)
    plan = [{'episode_timestamps': np.arange(0, 10, 0.1)}, {'episode_timestamps': np.arange(0, 20, 0.1)}]
    pickle.dump(plan, (s / 'dataset_plan.pkl').open('wb'))
    y = process_station.plan_yield(s)
    assert y['episodes'] == 2 and abs(y['seconds'] - (9.9 + 19.9)) < 1e-6
    (s / 'tag_tracking' / 'episodes.json').write_text(json.dumps({'videos': {'v': {'episodes': [{'start': 0, 'end': 100}], 'idle': [{'end': 200}]}}}))
    assert process_station.recorded_seconds(s) == 200
    (s / 'tag_tracking' / 'wrist_sync.json').write_text(json.dumps({'videos': {'h': {'w1': {'accuracy_ms': 1.5}, 'w2': {'accuracy_ms': 12.0}}}}))
    flags = process_station.quality_gates(s, y, 3, 0.3, 8.3)
    assert any('yield' in f for f in flags)          # 29.8 / 200 = 15% < 30%
    assert any('3 MCAP files for 2' in f for f in flags)
    assert any('12.0 ms' in f for f in flags)
    assert process_station.quality_gates(s, {'episodes': 0, 'seconds': 0.0}, None, 0.0, 99)[0] == 'no episodes in the plan'
    ok = process_station.quality_gates(s, {'episodes': 2, 'seconds': 120.0}, 2, 0.3, 99)
    assert ok == []


def test_quality_gates_tolerate_missing_files(tmp_path):
    import process_station
    s = tmp_path / 'task'; s.mkdir()
    assert process_station.sync_accuracies(s) == [] and process_station.recorded_seconds(s) is None
    assert process_station.plan_yield(s) == {'episodes': 0, 'seconds': 0.0}


def test_after_compute_upload_cleanup(tmp_path, monkeypatch):
    import process_station
    s = make_session(tmp_path)
    store = {}
    monkeypatch.setattr(process_station, 'AWS_PROFILE', None)
    monkeypatch.setattr(s3, 'make_client', lambda profile=None: FakeClient(store))
    monkeypatch.setattr(process_station, 's3_sizes', lambda url: {k.split('/')[-1]: len(v) for k, v in store.items()})
    text = process_station.after_compute(s, 's3://b/up/task01', True)
    assert 'uploaded 2 files' in text and 'verified: md5' in text and 'deleted 2 videos' in text
    assert set(store) == {'up/task01/episode_000000.mcap', 'up/task01/episode_000001.mcap'}


def test_export_mcap_failure_keeps_previous(tmp_path, monkeypatch):
    """A failing export step leaves the previous dataset_mcap untouched."""
    import process_station
    s = make_session(tmp_path)
    class R:
        ok = False
        log_path = 'x.log'
        def raise_for_status(self):
            raise PipelineError('exit 1', 'mcap')
    monkeypatch.setattr(process_station, 'run_command', lambda *a, **k: R())
    with pytest.raises(PipelineError):
        process_station.export_mcap(s, 'cfg.yaml', 4, s / 'logs', 10)
    assert sorted(p.name for p in (s / 'dataset_mcap').glob('*.mcap')) == ['episode_000000.mcap', 'episode_000001.mcap']


def test_export_mcap_success_swaps(tmp_path, monkeypatch):
    import process_station
    s = make_session(tmp_path)
    class R:
        ok = True
        log_path = 'x.log'
        def raise_for_status(self):
            pass
    def fake_run(name, cmd, *a, **k):
        out = pathlib.Path(cmd[cmd.index('-o') + 1]); out.mkdir()
        (out / 'episode_000000.mcap').write_bytes(b'n' * 5)
        return R()
    monkeypatch.setattr(process_station, 'run_command', fake_run)
    assert process_station.export_mcap(s, 'cfg.yaml', 4, s / 'logs', 10) == 1
    assert [p.name for p in (s / 'dataset_mcap').glob('*.mcap')] == ['episode_000000.mcap']
    assert len(list(s.glob('dataset_mcap_*'))) == 1    # earlier export kept aside


# ---------- parallel chunking
def test_chunk_bounds_cover_all_frames():
    from tt2.parallel import chunk_bounds
    frames = [{'sequence': 0 if i < 50 else 1} for i in range(100)]
    for n in (1, 3, 7, 100, 500):
        b = chunk_bounds(frames, n)
        assert b[0][0] == 0 and b[-1][1] == 100
        assert all(x[1] == y[0] for x, y in zip(b[:-1], b[1:]))
        assert all(lo <= start and stop <= hi for start, stop, lo, hi in b)


# ---------- synthetic video: video chunking + detection
@pytest.fixture(scope='module')
def tag_video(tmp_path_factory):
    import av
    import cv2
    path = tmp_path_factory.mktemp('vid') / 'v.mp4'
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(d, 7, 160)
    with av.open(str(path), 'w') as out:
        stream = out.add_stream('mpeg4', rate=30)
        stream.width, stream.height, stream.pix_fmt = 640, 480, 'yuv420p'
        stream.options = {'g': '10'}
        for i in range(60):
            img = np.full((480, 640), 255, np.uint8)
            x = 100 + i * 4
            img[100:260, x:x + 160] = marker
            frame = av.VideoFrame.from_ndarray(img, format='gray')
            for p in stream.encode(frame):
                out.mux(p)
        for p in stream.encode():
            out.mux(p)
    return str(path), d


def test_detect_video_all_frames_and_pool_reuse(tag_video):
    from tt2.tag_detection import detect_video_tag_corners
    from tt2.video_chunk import make_pool
    path, d = tag_video
    pool = make_pool(2)
    try:
        for _ in range(2):   # the same pool serves several videos
            res = detect_video_tag_corners(path, d, {7}, executor=pool)
            assert len(res) == 60 and [r['frame_idx'] for r in res] == list(range(60))
            assert all(7 in r['corners'] for r in res)
            times = [r['time'] for r in res]
            assert all(a < b for a, b in zip(times[:-1], times[1:]))
    finally:
        pool.shutdown()


def test_scaled_detection_matches_full_on_clean_tag(tag_video):
    import av
    import cv2
    from tt2.tag_detection import detect_tag_corners, detect_tag_corners_scaled, make_parameters
    path, d = tag_video
    with av.open(path) as c:
        gray = next(c.decode(video=0)).to_ndarray(format='gray')
    full = detect_tag_corners(gray, d, {7})
    fast = detect_tag_corners_scaled(gray, d, {7}, 0.5, make_parameters(subpix=False))
    assert set(full) == set(fast) == {7}
    assert np.abs(full[7] - fast[7]).max() < 1.0      # a clean 160 px tag: sub-pixel agreement


def test_video_chunk_failure_names_video(tag_video):
    from tt2.video_chunk import process_video_chunked
    path, d = tag_video
    with pytest.raises(PipelineError):
        process_video_chunked(path + '.missing', None, (), num_workers=1)


def test_run_pipelined_order_lookahead_and_failures():
    from tt2.video_chunk import run_pipelined
    events = []
    def submit(i):
        events.append(('submit', i))
        if i == 2:
            raise PipelineError('cannot submit 2')
        return i * 10
    def finish(i, h):
        events.append(('finish', i))
        if i == 3:
            raise PipelineError('cannot finish 3')
    failures = run_pipelined(range(6), submit, finish, lookahead=2)
    assert [(i, str(e)) for i, e in failures] == [(2, 'cannot submit 2'), (3, 'cannot finish 3')]
    assert [e for e in events if e[0] == 'finish'] == [('finish', 0), ('finish', 1), ('finish', 3), ('finish', 4), ('finish', 5)]
    # lookahead: item 0 is only finished after items 1 and 2 were submitted
    assert events.index(('finish', 0)) > events.index(('submit', 2))


def test_wrist_mask_identical_to_draw_predefined_mask():
    from umi.common.cv_util import draw_predefined_mask
    from tt2.wrist_detection import build_keep_mask, apply_mask
    rng = np.random.default_rng(0)
    for shape in [(2028, 2704), (1080, 1920), (480, 640)]:
        img = rng.integers(0, 256, size=(*shape, 3), dtype=np.uint8)
        expected = draw_predefined_mask(img.copy(), color=(0, 0, 0), mirror=True, gripper=False, finger=False)
        got = apply_mask(img, build_keep_mask(shape))
        assert np.array_equal(expected, got), shape
        assert not np.array_equal(img, got)      # the mask does paint something


# ---------- MCAP helpers
def test_to_annexb_roundtrip_and_params():
    import importlib.util
    spec = importlib.util.spec_from_file_location('export_mcap', V2 / 'scripts_tag_tracking' / '07_export_mcap.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    nal1, nal2 = bytes([0x46, 0x01, 0xAA]), bytes([0x26, 0x01, 0xBB, 0xCC])   # AUD (type 35), IDR slice
    packet = len(nal1).to_bytes(4, 'big') + nal1 + len(nal2).to_bytes(4, 'big') + nal2
    out = m.to_annexb(packet, 4, [b'\x40\x01VPS'], keyframe=True)
    assert out == m.START_CODE + nal1 + m.START_CODE + b'\x40\x01VPS' + m.START_CODE + nal2
    assert m.to_annexb(packet, 4, [b'x'], keyframe=False) == m.START_CODE + nal1 + m.START_CODE + nal2
    assert m.stamp(1.5) == {'sec': 1, 'nsec': 500000000}


def test_write_imu_and_missing_pose_vectorised():
    import importlib.util
    spec = importlib.util.spec_from_file_location('export_mcap2', V2 / 'scripts_tag_tracking' / '07_export_mcap.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    got = []
    m.write_imu(lambda ch, t, msg: got.append((ch, t, msg)), 5, lambda t: {'sec': 0, 'nsec': int(t * 1e9)},
        np.array([0.0, 0.1]), np.array([[1, 2, 3], [4, 5, 6]]), np.array([[0, 0, 1], [0, 1, 0]]))
    assert len(got) == 2 and got[1][2]['linear_acceleration'] == [4.0, 5.0, 6.0] and isinstance(got[0][2]['angular_velocity'][0], float)


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
