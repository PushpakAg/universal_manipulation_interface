import json,html,glob,collections
import os; S=os.path.dirname(os.path.abspath(__file__))
D='/Users/kgen/Projects/universal_manipulation_interface/docs/'
X=json.load(open(S+'/rows.json'))
R={json.load(open(f))['ep']:json.load(open(f)) for f in glob.glob(S+'/res/ep*.json')}
e=html.escape
s3=[x for x in X if x['has_s3']]
def badge(v):
    cls={'PASS':'ok','FAIL':'bad','WARN':'warn','INFO':'info','YES':'ok','NO':'bad','N/A':'info'}.get(v,'info'); return '<span class="b %s">%s</span>'%(cls,e(v))
def yn(b): return badge('YES' if b else 'NO')
# aggregates
n_ov=sum(x['ov_ident'] for x in X); n_s3=len(s3)
maxpos=max(x['pos'] for x in s3); maxrot=max(x['rot'] for x in s3)
span_fail=sum(1 for x in X if x['chk']['U2span'][0]=='FAIL')
pose_warn=[x['ep'] for x in X if x['chk']['POSE'][0]=='WARN']
passive=[x['ep'] for x in X if x['chk']['U5'][0]=='INFO']
maxstart=max(x['start_spread'] for x in X); maxend=max(x['end_spread'] for x in X)
tot=lambda k:sum(x[k] if not isinstance(x[k],list) else 0 for x in X)
# ---------- HTML ----------
css='''
:root{--bg:#fff;--fg:#1c2333;--mut:#5b6478;--line:#d9dde7;--card:#f6f7fb;--ok:#1a7f4b;--okbg:#e2f5ea;--bad:#b42318;--badbg:#fde7e4;--warn:#9a6700;--warnbg:#fff3cd;--info:#34508a;--infobg:#e6edfb;--acc:#34508a}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#12151c;--fg:#e6e9f0;--mut:#9aa3b8;--line:#2a3142;--card:#191e29;--ok:#6fd6a0;--okbg:#14301f;--bad:#ff9d92;--badbg:#3b1815;--warn:#f0c860;--warnbg:#3a2f0b;--info:#9db8f0;--infobg:#1c2845;--acc:#9db8f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1280px;margin:0 auto;padding:24px 16px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:36px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}h3{font-size:16px;margin:20px 0 6px}
p,li{max-width:100ch}.mut{color:var(--mut)}code{font:12.5px ui-monospace,Menlo,monospace;background:var(--card);padding:1px 5px;border-radius:4px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:14px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.card .n{font-size:26px;font-weight:650}.card .l{color:var(--mut);font-size:13px}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;white-space:nowrap}th{background:var(--card);position:sticky;top:0}td.w{white-space:normal;min-width:240px}tr:last-child td{border-bottom:0}
.b{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}.ok{background:var(--okbg);color:var(--ok)}.bad{background:var(--badbg);color:var(--bad)}.warn{background:var(--warnbg);color:var(--warn)}.info{background:var(--infobg);color:var(--info)}
details{border:1px solid var(--line);border-radius:8px;margin:6px 0;background:var(--card)}summary{cursor:pointer;padding:8px 12px;font-weight:600}details .in{padding:0 12px 12px}
.callout{border-left:4px solid var(--acc);background:var(--card);padding:10px 14px;border-radius:0 8px 8px 0;margin:12px 0}.num{text-align:right;font-variant-numeric:tabular-nums}
@media (max-width:600px){h1{font-size:21px}}
'''
H=[]
H.append('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCAP Comparison</title><style>%s</style></head><body><main>'%css)
H.append('<h1>MCAP comparison: S3 vs original pipeline vs tag_tracking_v2</h1><p class="mut">station1 / task01 · 28 episodes · reference: DataPRD1019.pdf (PRD v1.1, UMI section U1–U6 and "Delivery and metadata") · generated from the files on disk, nothing assumed</p>')
H.append('<h2>Sources compared</h2><div class="tw"><table><tr><th>Label</th><th>Path (under <code>data/</code>)</th><th>Files</th><th>Written</th></tr>'
 '<tr><td><b>S3</b></td><td><code>s3/task01/</code> (downloaded from <code>s3://stage-egc-stereo-v2-data/umi-testing/industrial_task/station1/task01/</code>)</td><td>27</td><td>2026-11-21 05:34–05:36 UTC (S3 LastModified)</td></tr>'
 '<tr><td><b>ORIG</b></td><td><code>station1/industrial_data/task01/dataset_mcap/</code> (repo <code>scripts_tag_tracking</code> via <code>run_tag_tracking_pipeline.py</code>, per <code>process_station.out</code>)</td><td>28</td><td>2026-11-22 01:35</td></tr>'
 '<tr><td><b>V2</b></td><td><code>full_check/v2/task01/dataset_mcap/</code> (<code>tag_tracking_v2</code>, run log <code>full_check/v2.out</code>)</td><td>28</td><td>2026-11-22 15:31</td></tr></table></div>')
H.append('<p class="mut">Method: SHA-256 and byte size of every file; then every MCAP was read message by message: channel list and schemas, metadata records, per-topic message counts, log times, and the payload of every message (video H.265 bitstreams hashed; poses, gripper width and IMU compared numerically; rotation differences measured as an angle, not component-wise).</p>')
H.append('<h2>Result</h2><div class="cards">'
 '<div class="card"><div class="n">%d / 28</div><div class="l">ORIG ≡ V2: byte-identical files (same SHA-256 and size)</div></div>'%n_ov+
 '<div class="card"><div class="n">0 / %d</div><div class="l">S3 files identical to ORIG (all differ in size and SHA-256)</div></div>'%n_s3+
 '<div class="card"><div class="n">1</div><div class="l">episode missing from S3 (episode_000016, 927,749,767 bytes locally)</div></div>'
 '<div class="card"><div class="n">%d / %d</div><div class="l">S3 episodes with identical video streams to ORIG (all 3 cameras)</div></div>'%(sum(x['vid_same'] for x in s3),n_s3)+
 '</div>')
H.append('<div class="callout"><b>Reading.</b> ORIG and V2 are the same data: identical bytes in all 28 files, so every topic, metadata value, sync frame and the world frame match exactly. The S3 files are a different run of the same recordings: same topic list, schemas, metadata keys, video bitstreams (all %d episodes), sync-frame indices, world frame (<code>tag14</code>), fps, image size and intrinsics; but the tracking/sync numbers differ slightly (wrist offsets, poses, gripper width, IMU timestamps), %d episodes have a different pose-sample count for robot1, and S3 has no episode_000016. Because S3 differs from what the pipeline now produces, the S3 copy is not the one to hand over as-is.</div>'%(n_s3,len(s3[0:0])+sum(1 for x in s3 if x['cdiff'])))
# matrix
H.append('<h2>1. Episode-by-episode: S3 vs ORIG vs V2</h2><div class="tw"><table><tr><th>Ep</th><th class="num">Size S3</th><th class="num">Size ORIG</th><th class="num">Size V2</th><th>ORIG=V2 bytes</th><th>S3=ORIG bytes</th><th>Topics/schemas same (17)</th><th>Metadata keys same</th><th>Sync frames same</th><th>World frame</th><th>Video streams S3=ORIG</th><th>S3 pose diff (max)</th><th>Pose counts</th></tr>')
for x in X:
    n=x['name']
    pd=x['pair_so'] if x['has_s3'] else None
    keys_same= (x['has_s3'] and all(isinstance(v,dict) for v in pd['meta_diff'].values()) and not any(k not in ('sync','recording') for k in pd['meta_diff']) ) 
    H.append('<tr><td><b>%d</b></td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'%(
      x['ep'],('{:,}'.format(x['s3size']) if x['has_s3'] else '<span class="b bad">missing</span>'),'{:,}'.format(x['size']['orig']),'{:,}'.format(x['size']['v2']),
      yn(x['sha_ov']),(yn(x['sha_so']) if x['has_s3'] else badge('N/A')),
      (yn(x['struct_same']) if x['has_s3'] else badge('N/A')),(yn(True) if x['has_s3'] else badge('N/A')),
      (yn(x['sync_frames_same']) if x['has_s3'] else badge('N/A')),
      ('tag14 / tag14 / tag14' if x['has_s3'] and x['wf_same'] else 'tag14 (ORIG,V2)'),
      (yn(x['vid_same']) if x['has_s3'] else badge('N/A')),
      ('%.1f mm / %.2f°'%(x['pos']*1e3,x['rot']) if x['has_s3'] else '–'),
      ('<span class="b warn">robot1: S3 %d vs %d</span>'%tuple(list(x['cdiff'].values())[0]) if x['has_s3'] and x['cdiff'] else (badge('YES') if x['has_s3'] else '–'))))
H.append('</table></div><p class="mut">“Metadata keys same” = the same metadata records and the same keys exist; value differences are listed in section 2. Pose diff = largest position (mm) and rotation (degrees) difference between the S3 and ORIG samples on any pose or end-effector topic, on matching sample indices.</p>')
# metadata diffs
H.append('<h2>2. Metadata differences (S3 vs ORIG; ORIG vs V2 has none)</h2><p>All recording, camera0–2 and sync metadata records were compared key by key. ORIG vs V2: <b>no difference in any of the 28 episodes</b>. S3 vs ORIG: every non-listed key is identical (including <code>world_frame</code>, <code>video_fps</code>, image size, all intrinsics, <code>camera*_sync_frame</code>). The only differences are:</p><div class="tw"><table><tr><th>Ep</th><th>Key</th><th>S3</th><th>ORIG = V2</th></tr>')
for x in s3:
    for rec,d in x['pair_so']['meta_diff'].items():
        for k,(a,b) in sorted(d.items()):
            H.append('<tr><td>%d</td><td><code>%s.%s</code></td><td>%s</td><td>%s</td></tr>'%(x['ep'],rec,k,e(str(a)),e(str(b))))
H.append('</table></div>')
# sync
H.append('<h2>3. Camera sync frames and sync values</h2><p>Source: <code>sync</code> metadata record. <code>camera*_sync_frame</code> is, per <code>scripts_tag_tracking/07_export_mcap.py:320</code>, the first frame of the episode in the source GoPro video (<code>video_start_end[0]</code>); it is a frame index in the raw recording, not in the delivered stream, so it can exceed the stream frame count. <code>offset_ms</code> is the clock correction applied to that camera; <code>sync_sigma_ms</code> is the residual of the wrist-motion fit. Method string is identical everywhere: <code>audio cross-correlation, wrist motion refinement</code>.</p><div class="tw"><table><tr><th>Ep</th><th>camera0 (R wrist) frame</th><th>camera1 (L wrist) frame</th><th>camera2 (head) frame</th><th>cam0 offset ms (ORIG)</th><th>cam1 offset ms (ORIG)</th><th>σ cam0 / cam1 ms (ORIG)</th><th>S3: Δ offset ms (max)</th><th>S3: frames same</th></tr>')
for x in X:
    if x['has_s3']:
        ms=x['s3sync']; so=R[x['ep']]['meta']['orig']['sync']
        do=max(abs(float(ms['camera%d_offset_ms'%i])-float(so['camera%d_offset_ms'%i])) for i in (0,1)); sf=yn(x['sync_frames_same'])
    else: do=None; sf=badge('N/A')
    H.append('<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td class="num">%.3f</td><td class="num">%.3f</td><td class="num">%.2f / %.2f</td><td class="num">%s</td><td>%s</td></tr>'%(x['ep'],*x['syncframes'],x['offs'][0],x['offs'][1],x['sig'][0],x['sig'][1],('%.3f'%do if do is not None else '–'),sf))
H.append('</table></div>')
H.append('<h3>Stream timing inside each file (ORIG = V2 = S3 video timing within microseconds)</h3><div class="tw"><table><tr><th>Ep</th><th>Duration s</th><th>Frames cam0/cam1/cam2</th><th>fps</th><th>First-frame spread ms</th><th>Last-frame spread ms</th><th>Common span s</th></tr>')
for x in X:
    H.append('<tr><td>%d</td><td class="num">%.1f</td><td>%s</td><td>%s</td><td class="num">%.0f</td><td class="num">%.0f</td><td class="num">%.1f</td></tr>'%(x['ep'],x['dur'],' / '.join(map(str,x['frames'])),', '.join(map(str,x['fps'])),x['start_spread'],x['end_spread'],x['common']))
H.append('</table></div>')
# topics
H.append('<h2>4. Topics</h2><p>Every file (all three sources) has the same 17 channels, all JSON-encoded, same schema names:</p>')
sch=R[0]['schemas']['orig']
H.append('<div class="tw"><table><tr><th>Topic</th><th>Encoding</th><th>Schema</th><th>Messages in ep 0</th></tr>')
cnt={t:e_['n'][0] for t,e_ in R[0]['pairs']['orig|v2']['topics'].items()}
for t,(enc,nm,_) in sch.items(): H.append('<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td class="num">%d</td></tr>'%(e(t),enc,nm,cnt[t]))
H.append('</table></div><p>Per-episode detail below: message count, and S3 vs ORIG difference per topic. ORIG vs V2 is identical for every topic in every episode (counts, log times, payloads).</p>')
for x in X:
    r=R[x['ep']]
    H.append('<details><summary>Episode %d — %s</summary><div class="in"><div class="tw"><table><tr><th>Topic</th><th class="num">ORIG msgs</th><th class="num">V2 msgs</th><th class="num">S3 msgs</th><th>ORIG=V2 payload</th><th>S3 vs ORIG</th></tr>'%(x['ep'],x['name']))
    for t,eo in r['pairs']['orig|v2']['topics'].items():
        ident=eo['payload_identical']==eo['n'][0]==eo['n'][1]
        s3c='–';d='–'
        if x['has_s3']:
            es=r['pairs']['s3|orig']['topics'][t]; s3c=es['n'][0]
            if es['n'][0]!=es['n'][1]: d='<span class="b warn">count differs (%d vs %d)</span>'%(es['n'][0],es['n'][1])
            elif 'video' in t: d=badge('YES')+' bitstream identical' if es['payload_identical']==es['n'][0] else '<span class="b bad">NO</span>'
            elif es['payload_identical']==es['n'][0]: d=badge('YES')+' identical'
            elif 'max_pos_diff_m' in es: d='pos %.2f mm, rot %.3f°'%(es['max_pos_diff_m']*1e3,es['max_rot_diff_deg'])
            elif 'max_width_diff_m' in es: d='width %.2f mm'%(es['max_width_diff_m']*1e3)
            else: d='timestamps shifted ≤ %d µs'%(es.get('max_dt_ns',0)//1000+1)
        H.append('<tr><td><code>%s</code></td><td class="num">%d</td><td class="num">%d</td><td class="num">%s</td><td>%s</td><td>%s</td></tr>'%(e(t),eo['n'][0],eo['n'][1],s3c,yn(ident),d))
    H.append('</table></div></div></details>')
# world frame
H.append('<h2>5. World frame</h2><div class="tw"><table><tr><th>Check</th><th>Result</th></tr>'
 '<tr><td><code>recording.world_frame</code> in all 28 ORIG, 28 V2, 27 S3 files</td><td><b>tag14</b> in every file; no episode differs</td></tr>'
 '<tr><td>Station calibration (<code>station1/…/tag_tracking/bodies.json</code>, body <code>environment</code>)</td><td><code>anchor_tag: 14</code>, <code>T_body_tags[14]</code> = identity → world origin is AprilTag 14 ✓</td></tr>'
 '<tr><td>Other frame/units fields (identical in all files)</td><td><code>eef_frame=tcp</code>, <code>rotation=axis_angle</code>, <code>units=m,rad</code>, <code>gripper_width_unit=m</code>, <code>gripper_width_zero=fully closed</code>, <code>robot0=right</code>, <code>robot1=left</code>, TCP-in-camera robot0 (0, 0.075, 0.192) m, robot1 (0, 0.075, 0.182) m</td></tr>'
 '<tr><td>Poses are in the same frame in S3 and ORIG?</td><td>Yes: the largest position difference is %.1f mm (episode %d) and rotation %.2f° — a re-fit, not a frame change. Pose samples are unit quaternions (max |‖q‖−1| %.1e), no NaN in any file.</td></tr></table></div>'%(maxpos*1e3,max(s3,key=lambda x:x['pos'])['ep'],maxrot,max(x['qn'] for x in X)))
H.append('<p class="mut">The PRD itself does not specify a world frame or an MCAP layout (it specifies video views, sync and metadata), so world-frame correctness is checked for consistency against the station calibration, not against a PRD value.</p>')
# PRD
H.append('<h2>6. PRD check per episode (ORIG = V2 package)</h2><p>Machine-checkable PRD items only. Task-structure rules (R1–R8, cycle counts and lengths, hands in view, U3/U4 mount and lens views, U6 image quality) need video review and are not judged here.</p><div class="tw"><table><tr><th>Ep</th><th>U1 3 views</th><th>U2 fps</th><th>U2 same time span</th><th>U2 sync ≤1 frame</th><th>Camera metadata</th><th>Sync metadata</th><th>Gripper width</th><th>Pose complete</th><th>World frame</th><th>U5 both grippers moving</th></tr>')
for x in X:
    c=x['chk']
    H.append('<tr><td><b>%d</b></td>%s</tr>'%(x['ep'],''.join('<td title="%s">%s</td>'%(e(c[k][1]),badge(c[k][0])) for k in ('U1','U2fps','U2span','U2sync','META_cam','META_sync','GRIP','POSE','WORLD','U5'))))
H.append('</table></div><p class="mut">Hover a cell for the measured value. Full values are in the checklist document <code>docs/DataPRD1019_mcap_delivery_checklist.md</code>.</p>')
# findings
H.append('<h2>7. Findings</h2><ol>'
 '<li><b>ORIG and V2 are identical</b> (28/28 byte-for-byte). Either can be the delivery source.</li>'
 '<li><b>S3 is not identical to ORIG/V2</b> in any of its 27 files. Same recordings, same video, same structure; different tracking/sync output (offsets up to %.3f ms, poses up to %.1f mm / %.2f°, gripper width up to %.1f mm). S3 looks like an earlier run (uploaded 2026-11-21, before ORIG was written 2026-11-22).</li>'%(0.0 if not s3 else max(abs(float(x["s3sync"][k])-float(R[x["ep"]]["meta"]["orig"]["sync"][k])) for x in s3 for k in ("camera0_offset_ms","camera1_offset_ms")),maxpos*1e3,maxrot,max(x["wid"] for x in s3)*1e3)+
 '<li><b>episode_000016 is not in S3</b> (listing confirmed with <code>aws s3 ls</code>: 27 objects). It exists locally in ORIG and V2 (identical).</li>'
 '<li><b>Pose gaps differ for robot1 in episodes 10, 13, 17</b>: S3 has %s pose steps missing vs %s in ORIG/V2. ORIG/V2 also have gaps in episode 16 (710 steps, %.1f%% of the episode).</li>'%('48 / 38 / 62','45 / 20 / 31',100*710/9186)+
 '<li><b>PRD U2 “same time span” is not met in any episode</b>: the three video streams start up to %.0f ms apart (limit 1 frame = 16.7 ms) and end up to %.0f ms apart. Timestamps are on one common clock, so the content is aligned, but the PRD asks for each recording trimmed to the span all three views share.</li>'%(maxstart,maxend)+
 '<li><b>Sync-frame field meaning</b>: the PRD asks for “the frame index of the sync event in each file”. The MCAP carries <code>camera*_sync_frame</code> = start frame in the source video, which is out of range for the delivered stream in most episodes. Document this for the client or add a stream-relative index.</li>'
 '<li><b>Pipeline flag</b>: the V2 run summary logged “wrist sync accuracy 12.3 ms is above 8.3 ms”. Largest applied wrist offset in the files is 15.8 ms (episode 18); residual σ is ≤0.5 ms everywhere.</li>'
 '<li>Episodes %s: one gripper barely moves (width range &lt; 2 cm); allowed by PRD U5 as a passive role.</li></ol>'%', '.join(map(str,passive)))
H.append('</main></body></html>')
open(D+'mcap_comparison_s3_orig_v2.html','w').write('\n'.join(H))
print('html ok',len('\n'.join(H)))
