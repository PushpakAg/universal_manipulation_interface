# MCAP delivery checklist against the PRD (DataPRD1019, v1.1)

Station 1 · task01 · 28 episodes · package checked: `dataset_mcap/` from the original pipeline, which is byte-identical to the `tag_tracking_v2` output (SHA-256 equal in 28/28). The copy in S3 is a different, earlier run and should not be sent (see "Open items").

Scope: the PRD defines video, sync and metadata requirements for UMI data (section "UMI data: head + two wrist cameras", rules U1–U6, and "Delivery and metadata"). It does not define an MCAP layout or a world frame, so those rows are marked "internal consistency" rather than "PRD".

## 1. What must be in each MCAP, and the expected value

| # | PRD ref | What to send | Where in the MCAP | Expected value |
|---|---|---|---|---|
| 1 | U1 | Three synchronized views: head, left wrist, right wrist | topics `/cameras/camera0/video` (right wrist), `/cameras/camera1/video` (left wrist), `/cameras/camera2/video` (head); metadata `recording.camera0..2` | 3 video topics, encoding `foxglove.CompressedVideo`, `h265`, roles `right_wrist`, `left_wrist`, `head` |
| 2 | U2 | Same frame rate on all three views | metadata `camera0..2.frame_rate_hz`, `recording.video_fps` | 59.94 fps on all three |
| 3 | U2 | Same time span, trimmed to what all three views share | first/last message time of the 3 video topics | first-frame spread and last-frame spread each ≤ 1 frame = 16.7 ms at 59.94 fps |
| 4 | U2 | Synchronization within 1 frame | metadata `sync.camera0_offset_ms`, `camera1_offset_ms`, `camera0/1_sync_sigma_ms` | applied offset and residual σ each ≤ 16.7 ms |
| 5 | Delivery | Sync method and the frame index of the sync event in each file | metadata `sync.method`, `sync.camera0/1/2_sync_frame` | method string present; one frame index per camera |
| 6 | Delivery | Per camera: model, lens / field of view, resolution, frame rate, intrinsic calibration | metadata `camera0..2`: `model`, `fov_horizontal/vertical/diagonal_deg`, `resolution`, `frame_rate_hz`, `intrinsics_model`, `fx fy cx cy k1..k4` | GoPro HERO12 Black, 2704x2028, 59.94 Hz, Kannala-Brandt, all 13 values present for each camera |
| 7 | Delivery, U6 | Gripper-width value per frame | topics `robot0/gripper/state`, `robot1/gripper/state` (`width`); metadata `gripper_width_unit`, `gripper_width_zero` | one sample per pose step, metres, 0 = fully closed, no NaN |
| 8 | U5 | Both grippers in use | width range per gripper | both grippers open and close in the episode; a passive gripper is allowed (e.g. holding a basket) |
| 9 | Internal | Gripper and head poses in a stated world frame | topics `robot0/eef/pose`, `robot1/eef/pose`, `/head/pose`, `robot*/eef/state`; metadata `recording.world_frame`, `eef_frame`, `rotation`, `units` | `world_frame = tag14` (station anchor tag 14), `eef_frame = tcp`, axis-angle in rad, metres; same sample count as `episode_length`; unit quaternions; no NaN |
| 10 | Internal | Pose completeness | metadata `recording.robot0/1_pose_missing_steps` | 0 missing steps (report the number otherwise) |
| 11 | Internal | Same 17 channels in every file | channel list | `robot0/*`, `robot1/*` (eef/state, eef/pose, gripper/state, eef_demo_start/end, imu), `/head/pose`, `/head/imu`, 3 camera video topics |
| 12 | R1–R8, U3, U4, U6 | Task structure: ≥3 complete cycles (3–30 s per cycle), fixed spot, hands in view, no side tasks, rigid wrist mount, grasp visible, image quality | video content | not machine-checkable from the MCAP; needs video review |
| 13 | Delivery | Three separate original files per recording (`<session>_head.mp4`, `_left.mp4`, `_right.mp4`) | outside the MCAP | the MCAP embeds the three H.265 streams; confirm with the client that the MCAP replaces the separate MP4s, or send both |

## 2. Result per episode

Legend: PASS = meets the expected value; FAIL = does not; WARN = delivered but incomplete; INFO = allowed by the PRD, shown for awareness. Values are measured from the files.

| Ep | Size (bytes) | Dur s | 1 Views | 2 fps | 3 Span spread first/last ms | 4 Sync offset / σ ms | 5 Sync frames c0/c1/c2 | 6 Cam meta | 7 Width | 9 World | 10 Missing pose steps R/L | 8 Grippers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 173,366,617 | 28.0 | PASS | PASS | FAIL 515 / 20 | PASS 5.66 / 0.21 | 169/168/257 | PASS | PASS | PASS tag14 | PASS 0 / 0 | INFO |
| 1 | 148,691,120 | 27.0 | PASS | PASS | FAIL 515 / 20 | PASS 5.66 / 0.21 | 2556/2555/2644 | PASS | PASS | PASS tag14 | PASS 0 / 0 | INFO |
| 2 | 343,764,519 | 55.7 | PASS | PASS | FAIL 57 / 7 | PASS 10.16 / 0.11 | 1563/1626/1743 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 3 | 167,355,287 | 29.7 | PASS | PASS | FAIL 849 / 17 | PASS 7.00 / 0.50 | 302/303/472 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 4 | 649,697,732 | 101.1 | PASS | PASS | FAIL 849 / 17 | PASS 7.64 / 0.50 | 4501/4502/4671 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 5 | 258,888,730 | 34.9 | PASS | PASS | FAIL 187 / 17 | PASS 8.15 / 0.50 | 11494/11495/11664 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 6 | 232,679,190 | 32.7 | PASS | PASS | FAIL 848 / 17 | PASS 8.41 / 0.50 | 14044/14045/14214 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 7 | 242,406,119 | 33.1 | PASS | PASS | FAIL 187 / 17 | PASS 8.66 / 0.50 | 16546/16547/16716 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 8 | 150,573,637 | 20.4 | PASS | PASS | FAIL 187 / 18 | PASS 8.90 / 0.50 | 19251/19252/19421 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 9 | 109,918,167 | 16.0 | PASS | PASS | FAIL 188 / 18 | PASS 9.07 / 0.50 | 21025/21026/21195 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 10 | 224,933,549 | 30.0 | PASS | PASS | FAIL 188 / 18 | PASS 9.29 / 0.50 | 22735/22736/22905 | PASS | PASS | PASS tag14 | WARN 0 / 45 | PASS |
| 11 | 267,195,294 | 38.4 | PASS | PASS | FAIL 171 / 21 | PASS 11.03 / 0.35 | 217/214/447 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 12 | 317,754,589 | 47.5 | PASS | PASS | FAIL 171 / 21 | PASS 11.03 / 0.35 | 2901/2898/3131 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 13 | 363,605,016 | 54.7 | PASS | PASS | FAIL 592 / 8 | PASS 2.90 / 0.42 | 428/343/561 | PASS | PASS | PASS tag14 | WARN 0 / 20 | PASS |
| 14 | 176,190,360 | 29.1 | PASS | PASS | FAIL 592 / 8 | PASS 3.19 / 0.42 | 4218/4133/4351 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 15 | 244,256,320 | 39.0 | PASS | PASS | FAIL 592 / 8 | PASS 3.45 / 0.42 | 6605/6520/6738 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 16 | 927,749,767 | 154.0 | PASS | PASS | FAIL 593 / 9 | PASS 4.07 / 0.42 | 9610/9525/9743 | PASS | PASS | PASS tag14 | WARN 0 / 710 | PASS |
| 17 | 1,162,838,450 | 187.3 | PASS | PASS | FAIL 632 / 10 | PASS 5.14 / 0.42 | 19711/19626/19844 | PASS | PASS | PASS tag14 | WARN 0 / 31 | PASS |
| 18 | 251,845,771 | 43.8 | PASS | PASS | FAIL 214 / 6 | PASS 15.81 / 0.28 | 284/214/451 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 19 | 274,773,413 | 45.8 | PASS | PASS | FAIL 214 / 6 | PASS 15.45 / 0.28 | 3556/3486/3723 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 20 | 46,055,498 | 14.2 | PASS | PASS | FAIL 215 / 6 | PASS 14.99 / 0.28 | 8871/8801/9038 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 21 | 160,392,601 | 25.0 | PASS | PASS | FAIL 841 / 6 | PASS 14.52 / 0.28 | 12969/12899/13136 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 22 | 230,395,268 | 37.6 | PASS | PASS | FAIL 215 / 7 | PASS 14.25 / 0.28 | 15154/15084/15321 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 23 | 183,764,515 | 27.5 | PASS | PASS | FAIL 215 / 12 | PASS 13.96 / 0.28 | 18105/18036/18272 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 24 | 230,418,367 | 34.0 | PASS | PASS | FAIL 215 / 12 | PASS 13.72 / 0.28 | 20182/20113/20349 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 25 | 297,337,764 | 43.6 | PASS | PASS | FAIL 841 / 11 | PASS 13.39 / 0.28 | 22988/22919/23155 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 26 | 157,050,091 | 25.9 | PASS | PASS | FAIL 841 / 11 | PASS 13.12 / 0.28 | 26104/26035/26271 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |
| 27 | 174,933,874 | 24.8 | PASS | PASS | FAIL 945 / 11 | PASS 12.89 / 0.28 | 28331/28262/28498 | PASS | PASS | PASS tag14 | PASS 0 / 0 | PASS |

Gripper width ranges (m), right R / left L, from `robot0/gripper/state` and `robot1/gripper/state`:

| Ep | R min–max | L min–max |
|---|---|---|
| 0 | 0.077–0.086 | 0.007–0.091 |
| 1 | 0.079–0.086 | 0.007–0.090 |
| 2 | 0.006–0.086 | 0.006–0.091 |
| 3 | 0.007–0.087 | 0.008–0.087 |
| 4 | 0.005–0.087 | 0.010–0.091 |
| 5 | 0.008–0.087 | 0.010–0.090 |
| 6 | 0.005–0.087 | 0.011–0.089 |
| 7 | 0.004–0.086 | 0.009–0.088 |
| 8 | 0.008–0.086 | 0.013–0.089 |
| 9 | 0.006–0.087 | 0.011–0.089 |
| 10 | 0.010–0.086 | 0.009–0.090 |
| 11 | 0.008–0.086 | 0.010–0.090 |
| 12 | 0.004–0.087 | 0.006–0.091 |
| 13 | 0.004–0.086 | 0.011–0.088 |
| 14 | 0.006–0.086 | 0.010–0.088 |
| 15 | 0.008–0.086 | 0.009–0.087 |
| 16 | 0.004–0.086 | 0.008–0.090 |
| 17 | 0.005–0.086 | 0.005–0.090 |
| 18 | 0.002–0.086 | 0.012–0.089 |
| 19 | 0.004–0.086 | 0.014–0.091 |
| 20 | 0.036–0.086 | 0.039–0.089 |
| 21 | 0.008–0.086 | 0.009–0.087 |
| 22 | 0.004–0.086 | 0.010–0.090 |
| 23 | 0.004–0.086 | 0.012–0.087 |
| 24 | 0.006–0.086 | 0.011–0.087 |
| 25 | 0.005–0.086 | 0.009–0.087 |
| 26 | 0.004–0.085 | 0.010–0.090 |
| 27 | 0.008–0.086 | 0.011–0.089 |

## 3. Summary for the client

Do the MCAP files pass the checklist? **Not yet in full: every metadata and structure item passes in all 28 episodes, except one PRD item (U2, same time span) that fails in all 28, and a few episodes with pose gaps.**

| Item | Episodes passing | Note |
|---|---|---|
| 1 Three views (U1) | 28 / 28 | head + left + right wrist in every file |
| 2 Same frame rate (U2) | 28 / 28 | 59.94 fps on all streams |
| 3 Same time span (U2) | 0 / 28 | **fails everywhere**: first-frame spread 56–945 ms, last-frame spread up to 20 ms, limit 16.7 ms. Trim each episode to the common span. |
| 4 Sync within 1 frame (U2) | 28 / 28 | largest applied wrist offset 15.8 ms (episode 18), residual σ ≤ 0.50 ms |
| 5 Sync method and frame index | 28 / 28 | method: audio cross-correlation, wrist motion refinement. `camera*_sync_frame` is the episode start frame in the source recording, not an index into the delivered stream (can exceed the stream frame count). |
| 6 Camera model, FOV, resolution, fps, intrinsics | 28 / 28 | GoPro HERO12 Black, 2704x2028, FOV ≈120° horizontal, Kannala-Brandt intrinsics |
| 7 Gripper width per frame | 28 / 28 | metres, 0 = fully closed |
| 9 World frame | 28 / 28 | `tag14`, matches `anchor_tag: 14` in the station calibration |
| 10 Complete poses | 24 / 28 | gaps in episodes 10, 13, 16, 17 (robot1 left gripper: 45, 20, 710 and 31 steps; episode 16 is 7.7% of the episode) |
| 8 Both grippers moving (U5) | 26 / 28 | episodes 0, 1: right gripper barely moves (passive role, allowed) |

### Open items before sending

1. **Which files to send.** The `dataset_mcap/` set (original pipeline = `tag_tracking_v2`, byte-identical, 28 files). Do not send the S3 copy: none of its 27 files match (sizes and SHA-256 differ; same video streams, different sync offsets and pose values; up to 33 mm / 2.3° pose difference in episode 12).
2. **episode_000016 is missing in S3** (it exists locally, 927,749,767 bytes) and must be uploaded.
3. **Trim to the common span** (item 3), or tell the client the streams are aligned by timestamp and not trimmed.
4. **Explain `camera*_sync_frame`** to the client, or add a delivered-stream index (item 5).
5. **Pose gaps** in episodes 10, 13, 16, 17: decide whether to send, fix, or drop them (item 10).
6. **Task-structure rules and the separate head/left/right MP4s** (items 12–13) are not covered by this automated check.
7. The V2 run logged a pipeline flag: "wrist sync accuracy 12.3 ms is above 8.3 ms". Worth a look before sending.
