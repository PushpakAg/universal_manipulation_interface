"""
umi.tag_tracking.session.unsynced_recordings: a recording with a video the audio sync rejected
is left out whole (all videos overlapping it in time), other recordings are kept;
gripper_heads: a head-only clip (no wrist video of every gripper overlapping it) is skipped.

python tests/test_session_sync.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from umi.tag_tracking.session import unsynced_recordings, gripper_heads


def test_unsynced_recordings():
    # station3 task01: recording 3 (head 49 s from 0, wrists 30 s from 21 s, wrists not synced),
    # recording 4 from 91 s, all synced
    v = lambda name, start, length, synced: {'name': name, 'start': start, 'end': start + length, 'synced': synced}
    videos = [v('head3', 0, 49, True), v('right3', 21, 30, False), v('left3', 21, 30, False),
        v('head4', 91, 31, True), v('right4', 93, 33, True), v('left4', 93, 33, True)]
    assert unsynced_recordings(videos) == {'head3', 'right3', 'left3'}
    assert unsynced_recordings([x for x in videos if x['name'].endswith('4')]) == set()


def test_gripper_heads():
    # station4 2026-11-21 task00: a 14 s head-only clip, a head clip with one wrist, then a take
    v = lambda name, serial, start, length: {'name': name, 'camera_serial': serial, 'start_timestamp': start,
        'end_timestamp': start + length}
    videos = [v('head_clip', 'H', 0, 14), v('head_one', 'H', 20, 30), v('right_one', 'R', 22, 20),
        v('head_take', 'H', 60, 600), v('right_take', 'R', 62, 590), v('left_take', 'L', 63, 590)]
    assert [x['name'] for x in gripper_heads(videos, 'H', ['R', 'L'])] == ['head_take']


if __name__ == '__main__':
    test_unsynced_recordings()
    test_gripper_heads()
    print('all passed')
