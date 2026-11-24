import json,glob,html,datetime
import os; S=os.path.dirname(os.path.abspath(__file__))
D='/Users/kgen/Projects/universal_manipulation_interface/docs/'
sha={}
for k,f in [('s3','sha_s3_task01.txt'),('orig','sha_station1_industrial_data_task01_dataset_mcap.txt'),('v2','sha_full_check_v2_task01_dataset_mcap.txt')]:
    sha[k]={l.split()[1]:l.split()[0] for l in open(S+'/'+f)}
R=[json.load(open(f)) for f in sorted(glob.glob(S+'/res/ep*.json'))]
FRAME_MS=1000/59.94005994
e=html.escape
TOPICS=None
rows=[]
for r in R:
    n='episode_%06d.mcap'%r['ep']; ep=r['ep']
    o=r['facts']['orig']; mo=r['meta']['orig']; rc=mo['recording']; sy=mo['sync']; c=o['cams']
    x={'ep':ep,'name':n,'has_s3':'s3' in r['meta']}
    x['size']=r['size']
    x['sha_ov']=sha['orig'][n]==sha['v2'][n]
    x['sha_so']= x['has_s3'] and sha['s3'][n]==sha['orig'][n]
    x['dur']=o['dur_s']
    x['frames']=[c['camera%d'%i]['n'] for i in range(3)]
    x['fps']=sorted({round(c[k]['fps_eff'],2) for k in c})
    x['start_spread']=o['cam_start_spread_ms']; x['end_spread']=o['cam_end_spread_ms']; x['common']=o['common_span_s']
    x['offs']=[float(sy['camera0_offset_ms']),float(sy['camera1_offset_ms'])]
    x['sig']=[float(sy['camera0_sync_sigma_ms']),float(sy['camera1_sync_sigma_ms'])]
    x['syncframes']=[sy['camera%d_sync_frame'%i] for i in range(3)]
    x['method']=sy['method']
    x['miss']=[int(rc['robot0_pose_missing_steps']),int(rc['robot1_pose_missing_steps'])]
    x['plen']=int(rc['episode_length'])
    x['wf']=rc['world_frame']
    g0=o['robot0/gripper/state'];g1=o['robot1/gripper/state']
    x['g']=[(g0['min'],g0['max']),(g1['min'],g1['max'])]
    x['nan']=sum(o[k]['nan'] for k in ('robot0/eef/pose','robot1/eef/pose','/head/pose'))
    x['qn']=max(abs(o[k]['qnorm_max']-1) for k in ('robot0/eef/pose','robot1/eef/pose','/head/pose'))
    x['ntopics']=len(r['schemas']['orig'])
    x['pair_ov']=r['pairs']['orig|v2']
    ov=x['pair_ov']
    x['ov_ident']=(ov['schema_equal'] and not ov['meta_diff'] and all(t['payload_identical']==t['n'][0] and t['n'][0]==t['n'][1] and t['same_logtime'] for t in ov['topics'].values()))
    if x['has_s3']:
        p=r['pairs']['s3|orig']; T=p['topics']; x['pair_so']=p
        x['s3size']=r['size']['s3']
        x['vid_same']=all(T['/cameras/camera%d/video'%i]['payload_identical']==T['/cameras/camera%d/video'%i]['n'][0]==T['/cameras/camera%d/video'%i]['n'][1] for i in range(3))
        x['pos']=max(t.get('max_pos_diff_m',0) for t in T.values()); x['rot']=max(t.get('max_rot_diff_deg',0) for t in T.values()); x['wid']=max(t.get('max_width_diff_m',0) for t in T.values())
        x['cdiff']={t:t_['n'] for t,t_ in T.items() if t_['n'][0]!=t_['n'][1]}
        x['imu_diff']=[t for t in ('robot0/imu','robot1/imu','/head/imu') if T[t].get('payload_identical')!=T[t]['n'][0]]
        x['lt']=max(t.get('max_dt_ns',0) for t in T.values())
        ms=r['meta']['s3']
        x['meta_s3']=p['meta_diff']
        x['sync_frames_same']=all(ms['sync']['camera%d_sync_frame'%i]==sy['camera%d_sync_frame'%i] for i in range(3))
        x['wf_same']=ms['recording']['world_frame']==rc['world_frame']
        x['struct_same']=p['schema_equal'] and not p['topics_only_a'] and not p['topics_only_b']
        x['s3miss']=[int(ms['recording']['robot0_pose_missing_steps']),int(ms['recording']['robot1_pose_missing_steps'])]
        x['s3sync']=ms['sync']
    # PRD checks (orig==v2 package)
    chk={}
    chk['U1']=('PASS',"3 video topics; roles %s"%', '.join(mo['camera%d'%i]['role'] for i in range(3)))
    chk['U2fps']=('PASS',"all 3 streams %.2f fps"%x['fps'][0]) if len(x['fps'])==1 else ('FAIL',str(x['fps']))
    ok_span=x['start_spread']<=FRAME_MS and x['end_spread']<=FRAME_MS
    chk['U2span']=('PASS' if ok_span else 'FAIL',"first-frame spread %.0f ms, last-frame spread %.0f ms (limit %.1f ms)"%(x['start_spread'],x['end_spread'],FRAME_MS))
    mo_off=max(abs(v) for v in x['offs']); mo_sig=max(x['sig'])
    chk['U2sync']=('PASS' if mo_off<=FRAME_MS and mo_sig<=FRAME_MS else 'FAIL',"applied wrist offset max %.2f ms, residual sigma max %.2f ms (limit %.1f ms)"%(mo_off,mo_sig,FRAME_MS))
    camok=all(all(k in mo['camera%d'%i] for k in ('model','fov_horizontal_deg','resolution','frame_rate_hz','fx','fy','cx','cy','k1','k2','k3','k4','intrinsics_model')) for i in range(3))
    chk['META_cam']=('PASS' if camok else 'FAIL','model, FOV, resolution, fps, intrinsics present for camera0..2')
    syok=all(k in sy for k in ('method','camera0_sync_frame','camera1_sync_frame','camera2_sync_frame'))
    chk['META_sync']=('PASS' if syok else 'FAIL',"method '%s'; frame indices %s"%(sy['method'],'/'.join(x['syncframes'])))
    gw=g0['n']==x['plen'] and g1['n']==x['plen'] and g0['nan']==0 and g1['nan']==0
    chk['GRIP']=('PASS' if gw else 'FAIL',"width per frame, %d samples/gripper, unit m, no NaN"%x['plen'])
    mm=sum(x['miss'])
    chk['POSE']=('PASS' if mm==0 and x['nan']==0 else 'WARN',"missing pose steps R/L: %d/%d of %d%s"%(x['miss'][0],x['miss'][1],x['plen'],'' if mm==0 else ' (%.1f%%)'%(100*max(x['miss'])/x['plen'])))
    chk['WORLD']=('PASS' if x['wf']=='tag14' else 'FAIL',"world_frame=%s, units %s"%(x['wf'],rc['units']))
    act=[ (g[1]-g[0])>=0.02 for g in x['g']]
    chk['U5']=('PASS' if all(act) else 'INFO',"width range R %.3f-%.3f m, L %.3f-%.3f m%s"%(x['g'][0]+x['g'][1]+('' if all(act) else ' (one gripper passive)',)))
    x['chk']=chk
    rows.append(x)
json.dump(rows,open(S+'/rows.json','w'),default=str)
print(len(rows),sum(1 for x in rows if x['ov_ident']),sum(1 for x in rows if x['sha_ov']))
