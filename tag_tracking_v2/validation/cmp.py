import sys, json, hashlib, os, numpy as np
from mcap.reader import make_reader
from multiprocessing import Pool
B='/Users/kgen/Projects/universal_manipulation_interface/data/'
DIRS={'s3':B+'s3/task01/','orig':B+'station1/industrial_data/task01/dataset_mcap/','v2':B+'full_check/v2/task01/dataset_mcap/'}
OUT=sys.argv[1]
def flat(o,pre=''):
    if isinstance(o,dict):
        for k,v in o.items(): yield from flat(v,pre+'/'+k)
    elif isinstance(o,list):
        for i,v in enumerate(o): yield from flat(v,pre+'/%d'%i)
    elif isinstance(o,(int,float)): yield pre,float(o)
def load(p):
    r=make_reader(open(p,'rb')); s=r.get_summary()
    d={'size':os.path.getsize(p),'schemas':{},'topics':{},'meta':{}}
    for ch in s.channels.values():
        sc=s.schemas.get(ch.schema_id)
        d['schemas'][ch.topic]=[ch.message_encoding,sc.name if sc else None,sc.encoding if sc else None,dict(ch.metadata),(sc.data.decode() if sc else None)]
    for m in r.iter_metadata(): d['meta'][m.name]=dict(m.metadata)
    d['attach']=len(list(r.iter_attachments()))
    d['header']=(s.statistics.message_count,s.statistics.message_start_time,s.statistics.message_end_time)
    T={}
    for sch,ch,m in r.iter_messages():
        t=T.setdefault(ch.topic,{'lt':[],'pt':[],'h':[],'seq':[],'vals':{}})
        t['lt'].append(m.log_time); t['pt'].append(m.publish_time); t['seq'].append(m.sequence)
        if 'video' in ch.topic:
            j=json.loads(m.data); t['h'].append(hashlib.md5(j['data'].encode()).hexdigest())
            t['bytes']=t.get('bytes',0)+len(j['data'])*3//4
            t.setdefault('fmt',set()).add(j['format']); t.setdefault('fid',set()).add(j['frame_id'])
        else:
            t['h'].append(hashlib.md5(m.data).hexdigest())
            j=json.loads(m.data)
            for k,v in flat(j): t['vals'].setdefault(k,[]).append(v)
    for k,t in T.items():
        t['lt']=np.array(t['lt'],dtype=np.int64); t['pt']=np.array(t['pt'],dtype=np.int64)
        t['vals']={a:np.array(b) for a,b in t['vals'].items()}
    d['T']=T; return d
def facts(d):
    f={}
    m=d['meta']; rec=m.get('recording',{}); 
    f['header_msgs'],f['t0'],f['t1']=d['header']
    f['dur_s']=(f['t1']-f['t0'])/1e9
    cams={}
    for c in ['camera0','camera1','camera2']:
        t=d['T'].get('/cameras/%s/video'%c)
        if t is None: continue
        lt=t['lt']; dt=np.diff(lt)/1e9
        cams[c]={'n':len(lt),'first':int(lt[0]),'last':int(lt[-1]),'span_s':(lt[-1]-lt[0])/1e9,'fps_eff':(len(lt)-1)/((lt[-1]-lt[0])/1e9),'dt_med_ms':float(np.median(dt)*1e3),'dt_max_ms':float(dt.max()*1e3),'mono':bool((dt>0).all()),'fmt':sorted(t['fmt']),'bytes':t['bytes']}
    f['cams']=cams
    if cams:
        f['cam_start_spread_ms']=(max(c['first'] for c in cams.values())-min(c['first'] for c in cams.values()))/1e6
        f['cam_end_spread_ms']=(max(c['last'] for c in cams.values())-min(c['last'] for c in cams.values()))/1e6
        f['common_span_s']=(min(c['last'] for c in cams.values())-max(c['first'] for c in cams.values()))/1e9
    for tp in ['robot0/eef/pose','robot1/eef/pose','/head/pose']:
        t=d['T'].get(tp)
        if t is None: f[tp]=None; continue
        v=t['vals']; q=np.stack([v['/quat_xyzw/%d'%i] for i in range(4)],1); p=np.stack([v['/pos/%d'%i] for i in range(3)],1)
        f[tp]={'n':len(q),'nan':int(np.isnan(q).sum()+np.isnan(p).sum()),'qnorm_min':float(np.linalg.norm(q,axis=1).min()),'qnorm_max':float(np.linalg.norm(q,axis=1).max()),'pos_min':p.min(0).round(3).tolist(),'pos_max':p.max(0).round(3).tolist(),'max_step_m':float(np.linalg.norm(np.diff(p,axis=0),axis=1).max()) if len(p)>1 else 0,'hz':(len(q)-1)/((t['lt'][-1]-t['lt'][0])/1e9)}
    for tp in ['robot0/gripper/state','robot1/gripper/state']:
        t=d['T'].get(tp)
        if t is None: f[tp]=None; continue
        w=t['vals']['/width']; f[tp]={'n':len(w),'min':float(w.min()),'max':float(w.max()),'nan':int(np.isnan(w).sum())}
    for tp in ['robot0/imu','robot1/imu','/head/imu']:
        t=d['T'].get(tp)
        f[tp]=None if t is None else {'n':len(t['lt']),'hz':(len(t['lt'])-1)/((t['lt'][-1]-t['lt'][0])/1e9)}
    return f
def cmp(a,b):
    r={'size_a':a['size'],'size_b':b['size'],'schema_equal':a['schemas']==b['schemas'],'topics_only_a':sorted(set(a['T'])-set(b['T'])),'topics_only_b':sorted(set(b['T'])-set(a['T'])),'attach':[a['attach'],b['attach']]}
    r['schema_diff']=[k for k in a['schemas'] if k in b['schemas'] and a['schemas'][k]!=b['schemas'][k]]
    md={}
    for n in sorted(set(a['meta'])|set(b['meta'])):
        x=a['meta'].get(n); y=b['meta'].get(n)
        if x is None or y is None: md[n]='missing in '+('a' if x is None else 'b'); continue
        dd={k:[x.get(k),y.get(k)] for k in set(x)|set(y) if x.get(k)!=y.get(k)}
        if dd: md[n]=dd
    r['meta_diff']=md
    tp={}
    for k in sorted(set(a['T'])&set(b['T'])):
        x,y=a['T'][k],b['T'][k]
        e={'n':[len(x['lt']),len(y['lt'])]}
        if len(x['lt'])==len(y['lt']):
            e['same_logtime']=bool((x['lt']==y['lt']).all()); e['max_dt_ns']=int(np.abs(x['lt']-y['lt']).max())
            e['payload_identical']=int(sum(1 for p,q in zip(x['h'],y['h']) if p==q))
            if 'video' not in k:
                from scipy.spatial.transform import Rotation as Rr
                def rot(t):
                    v=t['vals']
                    if '/quat_xyzw/0' in v: return Rr.from_quat(np.stack([v['/quat_xyzw/%d'%i] for i in range(4)],1))
                    if '/rot_axis_angle/0' in v: return Rr.from_rotvec(np.stack([v['/rot_axis_angle/%d'%i] for i in range(3)],1))
                if '/pos/0' in x['vals']:
                    e['max_pos_diff_m']=float(np.linalg.norm(np.stack([x['vals']['/pos/%d'%i]-y['vals']['/pos/%d'%i] for i in range(3)],1),axis=1).max())
                    e['max_rot_diff_deg']=float(np.degrees((rot(x).inv()*rot(y)).magnitude().max()))
                if '/width' in x['vals']: e['max_width_diff_m']=float(np.abs(x['vals']['/width']-y['vals']['/width']).max())
                mx=0.0; worst=None
                for fld in x['vals']:
                    if fld in y['vals']:
                        dv=float(np.nanmax(np.abs(x['vals'][fld]-y['vals'][fld]))) if len(x['vals'][fld]) else 0.0
                        if dv>mx: mx=dv; worst=fld
                e['max_abs_diff']=mx; e['worst_field']=worst
        else:
            e['same_logtime']=False
        tp[k]=e
    r['topics']=tp
    return r
def work(i):
    n='episode_%06d.mcap'%i
    D={}
    for k,p in DIRS.items():
        if os.path.exists(p+n): D[k]=load(p+n)
    res={'ep':i,'present':sorted(D),'facts':{k:facts(v) for k,v in D.items()},'meta':{k:v['meta'] for k,v in D.items()},'schemas':{k:{t:s[:3] for t,s in v['schemas'].items()} for k,v in D.items()},'size':{k:v['size'] for k,v in D.items()},'pairs':{}}
    for a,b in [('s3','orig'),('orig','v2'),('s3','v2')]:
        if a in D and b in D: res['pairs'][a+'|'+b]=cmp(D[a],D[b])
    json.dump(res,open(OUT+'/ep%02d.json'%i,'w'),default=lambda o:list(o) if isinstance(o,set) else str(o))
    return i
if __name__=='__main__':
    os.makedirs(OUT,exist_ok=True)
    eps=[int(x) for x in sys.argv[2:]] or range(28)
    with Pool(5) as p:
        for i in p.imap_unordered(work,eps): print('done',i,flush=True)
