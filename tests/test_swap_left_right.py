"""
scripts_tag_tracking/swap_left_right.py on an episode exported by 15_export_episode_videos.py (local
output): left / right mp4s and gripper CSVs swapped, meta.json camera records swapped and marked, the
mosaic rendered again and passing the export check; a second run skips it; the list reading (header,
several files of one episode, episode folder).

python tests/test_swap_left_right.py
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts_tag_tracking'))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import csv
import importlib
import json
import pathlib
import tempfile
import av
from test_mcap_exact_start import read_number
from test_episode_videos import make_session, STARTS, N

videos = importlib.import_module('15_export_episode_videos')
swap = importlib.import_module('swap_left_right')


def first_number(path):
    with av.open(str(path)) as c:
        return read_number(next(c.decode(video=0)).to_ndarray(format='gray'))


def test_list():
    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp, 'list.csv')
        p.write_text("left_right_switch\n"
            "s3://b/mp4/station1/2026-11-21/task01/episode_000005/2026-11-21_task01_episode_000005_mosaic.mp4\n"
            "s3://b/mp4/station1/2026-11-21/task01/episode_000005/2026-11-21_task01_episode_000005_meta.json\n"
            "s3://b/mp4/station1/2026-11-21/task01/episode_000014/\n")
        assert swap.episode_folders(str(p)) == ['s3://b/mp4/station1/2026-11-21/task01/episode_000005',
            's3://b/mp4/station1/2026-11-21/task01/episode_000014'], swap.episode_folders(str(p))


def test_swap():
    with tempfile.TemporaryDirectory() as tmp:
        demos, episode, records = make_session(tmp)
        records = {k: dict(v) for k, v in records.items()}
        records['demo_left/raw_video.mp4']['fx'] = '1111.0'      # tell the camera records apart
        out = pathlib.Path(tmp, 'out')
        e = videos.export_episode(0, episode, demos, 'station1/2026-11-21/task01', str(out), out, records,
            True, 'libx264', 2, False)
        assert e['status'] == 'ok', e
        folder = out.joinpath('station1', '2026-11-21', 'task01', 'episode_000000')
        rec = '2026-11-21_task01_episode_000000'
        mosaic_before = folder.joinpath(f"{rec}_mosaic.mp4").read_bytes()
        p = pathlib.Path(tmp, 'list.csv')
        p.write_text(f"left_right_switch\n{folder.joinpath(rec + '_mosaic.mp4')}\n")

        r = swap.swap_episode(swap.episode_folders(str(p))[0], pathlib.Path(tmp, 'work'), 'libx264', 2, False)
        assert r['status'] == 'swapped' and r['frames'] == N and r['mosaic'], r
        assert first_number(folder.joinpath(f"{rec}_left.mp4")) == STARTS['right']
        assert first_number(folder.joinpath(f"{rec}_right.mp4")) == STARTS['left']
        assert first_number(folder.joinpath(f"{rec}_head.mp4")) == STARTS['head']
        left = list(csv.reader(folder.joinpath(f"{rec}_left_gripper.csv").open()))
        assert left[1] == ['0', '0.05000'], left[:2]          # the former right gripper's widths
        meta = json.loads(folder.joinpath(f"{rec}_meta.json").read_text())
        assert meta['cameras']['right']['fx'] == '1111.0' and meta['cameras']['left']['fx'] == '1200.0', meta['cameras']
        assert meta['left_right_swapped']['note'] == swap.NOTE
        assert folder.joinpath(f"{rec}_mosaic.mp4").read_bytes() != mosaic_before
        assert not list(pathlib.Path(tmp, 'work').rglob('*.mp4'))
        # again: skipped, nothing changed
        r = swap.swap_episode(str(folder), pathlib.Path(tmp, 'work'), 'libx264', 2, False)
        assert r['status'] == 'skipped', r
        assert first_number(folder.joinpath(f"{rec}_left.mp4")) == STARTS['right']


if __name__ == '__main__':
    test_list()
    test_swap()
    print('all passed')
