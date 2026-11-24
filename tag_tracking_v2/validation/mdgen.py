import json
import os; S=os.path.dirname(os.path.abspath(__file__))
X=json.load(open(S+'/rows.json'))
FR=1000/59.94005994
L=[]
A=L.append
A('# MCAP delivery checklist against the PRD (DataPRD1019, v1.1)\n')
A('Station 1 · task01 · 28 episodes · package checked: `dataset_mcap/` from the original pipeline, which is byte-identical to the `tag_tracking_v2` output (SHA-256 equal in 28/28). The copy in S3 is a different, earlier run and should not be sent (see "Open items").\n')
A('Scope: the PRD defines video, sync and metadata requirements for UMI data (section "UMI data: head + two wrist cameras", rules U1–U6, and "Delivery and metadata"). It does not define an MCAP layout or a world frame, so those rows are marked "internal consistency" rather than "PRD".\n')
A('## 1. What must be in each MCAP, and the expected value\n')
A('| # | PRD ref | What to send | Where in the MCAP | Expected value |\n|---|---|---|---|---|')
rows=[
('1','U1','Three synchronized views: head, left wrist, right wrist','topics `/cameras/camera0/video` (right wrist), `/cameras/camera1/video` (left wrist), `/cameras/camera2/video` (head); metadata `recording.camera0..2`','3 video topics, encoding `foxglove.CompressedVideo`, `h265`, roles `right_wrist`, `left_wrist`, `head`'),
('2','U2','Same frame rate on all three views','metadata `camera0..2.frame_rate_hz`, `recording.video_fps`','59.94 fps on all three'),
('3','U2','Same time span, trimmed to what all three views share','first/last message time of the 3 video topics','first-frame spread and last-frame spread each ≤ 1 frame = 16.7 ms at 59.94 fps'),
('4','U2','Synchronization within 1 frame','metadata `sync.camera0_offset_ms`, `camera1_offset_ms`, `camera0/1_sync_sigma_ms`','applied offset and residual σ each ≤ 16.7 ms'),
('5','Delivery','Sync method and the frame index of the sync event in each file','metadata `sync.method`, `sync.camera0/1/2_sync_frame`','method string present; one frame index per camera'),
('6','Delivery','Per camera: model, lens / field of view, resolution, frame rate, intrinsic calibration','metadata `camera0..2`: `model`, `fov_horizontal/vertical/diagonal_deg`, `resolution`, `frame_rate_hz`, `intrinsics_model`, `fx fy cx cy k1..k4`','GoPro HERO12 Black, 2704x2028, 59.94 Hz, Kannala-Brandt, all 13 values present for each camera'),
('7','Delivery, U6','Gripper-width value per frame','topics `robot0/gripper/state`, `robot1/gripper/state` (`width`); metadata `gripper_width_unit`, `gripper_width_zero`','one sample per pose step, metres, 0 = fully closed, no NaN'),
('8','U5','Both grippers in use','width range per gripper','both grippers open and close in the episode; a passive gripper is allowed (e.g. holding a basket)'),
('9','Internal','Gripper and head poses in a stated world frame','topics `robot0/eef/pose`, `robot1/eef/pose`, `/head/pose`, `robot*/eef/state`; metadata `recording.world_frame`, `eef_frame`, `rotation`, `units`','`world_frame = tag14` (station anchor tag 14), `eef_frame = tcp`, axis-angle in rad, metres; same sample count as `episode_length`; unit quaternions; no NaN'),
('10','Internal','Pose completeness','metadata `recording.robot0/1_pose_missing_steps`','0 missing steps (report the number otherwise)'),
('11','Internal','Same 17 channels in every file','channel list','`robot0/*`, `robot1/*` (eef/state, eef/pose, gripper/state, eef_demo_start/end, imu), `/head/pose`, `/head/imu`, 3 camera video topics'),
('12','R1–R8, U3, U4, U6','Task structure: ≥3 complete cycles (3–30 s per cycle), fixed spot, hands in view, no side tasks, rigid wrist mount, grasp visible, image quality','video content','not machine-checkable from the MCAP; needs video review'),
('13','Delivery','Three separate original files per recording (`<session>_head.mp4`, `_left.mp4`, `_right.mp4`)','outside the MCAP','the MCAP embeds the three H.265 streams; confirm with the client that the MCAP replaces the separate MP4s, or send both'),
]
for r in rows: A('| '+' | '.join(r)+' |')
A('\n## 2. Result per episode\n')
A('Legend: PASS = meets the expected value; FAIL = does not; WARN = delivered but incomplete; INFO = allowed by the PRD, shown for awareness. Values are measured from the files.\n')
A('| Ep | Size (bytes) | Dur s | 1 Views | 2 fps | 3 Span spread first/last ms | 4 Sync offset / σ ms | 5 Sync frames c0/c1/c2 | 6 Cam meta | 7 Width | 9 World | 10 Missing pose steps R/L | 8 Grippers |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for x in X:
    c=x['chk']
    A('| %d | %s | %.1f | %s | %s | %s %.0f / %.0f | %s %.2f / %.2f | %s | %s | %s | %s tag14 | %s %d / %d | %s |'%(
      x['ep'],'{:,}'.format(x['size']['orig']),x['dur'],c['U1'][0],c['U2fps'][0],c['U2span'][0],x['start_spread'],x['end_spread'],
      c['U2sync'][0],max(abs(v) for v in x['offs']),max(x['sig']),'/'.join(x['syncframes']),c['META_cam'][0],c['GRIP'][0],c['WORLD'][0],c['POSE'][0],x['miss'][0],x['miss'][1],c['U5'][0]))
A('\nGripper width ranges (m), right R / left L, from `robot0/gripper/state` and `robot1/gripper/state`:\n')
A('| Ep | R min–max | L min–max |\n|---|---|---|')
for x in X: A('| %d | %.3f–%.3f | %.3f–%.3f |'%(x['ep'],*x['g'][0],*x['g'][1]))
n=len(X)
ps=lambda k:sum(1 for x in X if x['chk'][k][0]=='PASS')
A('\n## 3. Summary for the client\n')
A('Do the MCAP files pass the checklist? **Not yet in full: every metadata and structure item passes in all 28 episodes, except one PRD item (U2, same time span) that fails in all 28, and a few episodes with pose gaps.**\n')
A('| Item | Episodes passing | Note |\n|---|---|---|')
A('| 1 Three views (U1) | %d / 28 | head + left + right wrist in every file |'%ps('U1'))
A('| 2 Same frame rate (U2) | %d / 28 | 59.94 fps on all streams |'%ps('U2fps'))
A('| 3 Same time span (U2) | %d / 28 | **fails everywhere**: first-frame spread %d–%d ms, last-frame spread up to %d ms, limit 16.7 ms. Trim each episode to the common span. |'%(ps('U2span'),min(x['start_spread'] for x in X),max(x['start_spread'] for x in X),max(x['end_spread'] for x in X)))
A('| 4 Sync within 1 frame (U2) | %d / 28 | largest applied wrist offset %.1f ms (episode 18), residual σ ≤ %.2f ms |'%(ps('U2sync'),max(max(abs(v) for v in x['offs']) for x in X),max(max(x['sig']) for x in X)))
A('| 5 Sync method and frame index | %d / 28 | method: audio cross-correlation, wrist motion refinement. `camera*_sync_frame` is the episode start frame in the source recording, not an index into the delivered stream (can exceed the stream frame count). |'%ps('META_sync'))
A('| 6 Camera model, FOV, resolution, fps, intrinsics | %d / 28 | GoPro HERO12 Black, 2704x2028, FOV ≈120° horizontal, Kannala-Brandt intrinsics |'%ps('META_cam'))
A('| 7 Gripper width per frame | %d / 28 | metres, 0 = fully closed |'%ps('GRIP'))
A('| 9 World frame | %d / 28 | `tag14`, matches `anchor_tag: 14` in the station calibration |'%ps('WORLD'))
A('| 10 Complete poses | %d / 28 | gaps in episodes %s (robot1 left gripper: 45, 20, 710 and 31 steps; episode 16 is 7.7%% of the episode) |'%(ps('POSE'),', '.join(str(x['ep']) for x in X if x['chk']['POSE'][0]=='WARN')))
A('| 8 Both grippers moving (U5) | %d / 28 | episodes %s: right gripper barely moves (passive role, allowed) |'%(ps('U5'),', '.join(str(x['ep']) for x in X if x['chk']['U5'][0]=='INFO')))
A('\n### Open items before sending\n')
A('1. **Which files to send.** The `dataset_mcap/` set (original pipeline = `tag_tracking_v2`, byte-identical, 28 files). Do not send the S3 copy: none of its 27 files match (sizes and SHA-256 differ; same video streams, different sync offsets and pose values; up to 33 mm / 2.3° pose difference in episode 12).')
A('2. **episode_000016 is missing in S3** (it exists locally, 927,749,767 bytes) and must be uploaded.')
A('3. **Trim to the common span** (item 3), or tell the client the streams are aligned by timestamp and not trimmed.')
A('4. **Explain `camera*_sync_frame`** to the client, or add a delivered-stream index (item 5).')
A('5. **Pose gaps** in episodes 10, 13, 16, 17: decide whether to send, fix, or drop them (item 10).')
A('6. **Task-structure rules and the separate head/left/right MP4s** (items 12–13) are not covered by this automated check.')
A('7. The V2 run logged a pipeline flag: "wrist sync accuracy 12.3 ms is above 8.3 ms". Worth a look before sending.\n')
open('/Users/kgen/Projects/universal_manipulation_interface/docs/DataPRD1019_mcap_delivery_checklist.md','w').write('\n'.join(L))
print('ok')
