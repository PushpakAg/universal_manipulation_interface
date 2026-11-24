"""
Process all (or some) sessions of a station, one after the other (v2 of process_station.py).
Per session
1. download it if the sessions are on S3 (boto3, files already there with the same size are skipped);
2. run_tag_tracking_pipeline.py (all steps, no render);
3. the dataset plan again with --keep_gaps (episodes with a short tracking gap kept, pose not
   available there), unless --no_keep_gaps;
4. with --mcap: the episode MCAP files (07_export_mcap.py -c), written to <session>/dataset_mcap.tmp
   and swapped into <session>/dataset_mcap only when ALL episodes were written; an earlier export is
   moved to dataset_mcap_<date>_<time>/ and is put back if the swap fails (a failed export never
   leaves the session without its previous MCAP files);
5. quality gates (see below);
6. with --upload: the MCAP files to <upload>/<session>/, each verified by size and MD5/ETag;
7. with --cleanup (sessions on S3 and --upload): after the verified upload the local videos
   (demos/*/raw_video.mp4 and raw_videos/: the originals stay in the S3 session) and the local MCAP
   files are deleted; logs, pairs.csv, tag tracking outputs and dataset_plan.pkl are kept.

Changes against the original
- stages overlap: the next session downloads while this one is processed, and the upload (and
  cleanup) of a session runs while the next is processed (--no_prefetch for one stage at a time).
  Disk need: current + next session + the MCAP files being uploaded;
- S3 through boto3 (retries, timeouts, connection reuse), not aws-cli subprocesses; an expired SSO login
  is reported with the fix;
- every external command has a time limit (--step_timeout_min) and its own log file;
- the yield (episodes, seconds used) is read from dataset_plan.pkl, not parsed from stdout;
- quality gates: no episodes, yield below --min_yield, MCAP count differs from the plan,
  wrist sync accuracy above --max_sync_ms; a flagged session is reported as "ok, flagged" (or
  failed with --fail_on_flags) instead of plain "ok";
- per session <session>/logs/process_station_result.json with status, steps, timings, flags;
- a session that fails does not stop the others; exit code 1 if any failed.

Sessions: the sub-folders of SESSIONS with raw_videos/ (from sort_recordings.py --tasks), local or
s3:// (then -w, the local folder to download to). The station's tag tracking config must have its
setup calibration (README, step 2).

python tag_tracking_v2/scripts_tag_tracking/process_station.py s3://my-bucket/UMI_Collection/station3/industrial_data \\
    -c example/tag_tracking/tag_tracking_station3.yaml -w ~/umi_data/station3/industrial_data \\
    --tasks task02,task03,task04 --mcap --upload s3://my-bucket/mcaps/station3

Several stations one after the other (--jobs, e.g. example/tag_tracking/process_jobs.yaml):
    - sessions: s3://my-bucket/UMI_Collection/station1/industrial_data
      config: example/tag_tracking/tag_tracking_station1.yaml
      workdir: ~/umi_data/station1/industrial_data
      tasks: [task03, task04, task05]      # optional, default all
      upload: s3://my-bucket/mcaps/station1
    - sessions: ...
python tag_tracking_v2/scripts_tag_tracking/process_station.py --jobs jobs.yaml --mcap --cleanup
All stations are checked (configs, sessions found) before the first starts; one summary at the end.
"""
# %%
import sys
import os
import pathlib

V2_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V2_ROOT))
from tt2.bootstrap import setup_paths, user_path, find_script, REPO_ROOT
setup_paths(chdir_to_repo=False)

# %%
import concurrent.futures
import json
import pickle
import time
import click
import yaml
from tt2 import s3
from tt2.errors import PipelineError, InputError, TransferError, ConfigError, require
from tt2.fsutil import atomic_json_dump, swap_directory
from tt2.log import setup_logging, set_log_file, get_logger
from tt2.runner import run_command

log = get_logger(__name__)
HALF_FRAME_MS = 1000 / 60 / 2   # 8.3 ms at 60 fps
AWS_PROFILE = None              # set from --aws_profile


def s3_sizes(url: str) -> dict:
    """File name -> size of the objects directly under an s3:// prefix."""
    return s3.list_sizes(url, AWS_PROFILE)


def s3_sessions(url: str) -> list:
    """Session names under an s3:// prefix: sub-folders with raw_videos/ (Delimiter listing, one request per level)."""
    names = s3.list_folders(url, AWS_PROFILE)
    bucket, prefix = s3.split(url)
    return sorted(n for n in names if s3.list_folders(f"s3://{bucket}/{prefix}/{n}", AWS_PROFILE).count('raw_videos'))


def cleanup(session: pathlib.Path, upload_url: str) -> str:
    """
    Delete the local videos and MCAP files of a session whose MCAP files are all on S3
    (same names and sizes). Returns what was done.
    """
    local = {p.name: p.stat().st_size for p in session.joinpath('dataset_mcap').glob('*.mcap')}
    remote = s3_sizes(upload_url)
    mismatch = sorted(n for n, size in local.items() if remote.get(n) != size)
    if not local or mismatch:
        return f"cleanup skipped: MCAP files not all on {upload_url} with the same size: {mismatch or 'no local MCAP files'}"
    videos = [p for p in session.joinpath('demos').glob('*/raw_video.mp4') if p.is_file() and not p.is_symlink()]
    links = [p for p in session.joinpath('raw_videos').rglob('*') if p.suffix.lower() == '.mp4']
    mcaps = list(session.joinpath('dataset_mcap').glob('*.mcap'))
    freed = sum(p.stat().st_size for p in videos + mcaps) + sum(p.stat().st_size for p in links
        if p.is_file() and not p.is_symlink())
    for p in videos + links + mcaps:
        p.unlink()
    return f"cleanup: deleted {len(videos)} videos, {len(links)} raw_videos entries, {len(mcaps)} MCAP files " \
        f"({freed / 1e9:.1f} GB); videos stay in the S3 session, MCAP files on {upload_url}"


def station_job(sessions: str, config: str, workdir, tasks, mcap: bool, upload, cleanup_after: bool, name=None) -> dict:
    """
    One station's run, checked before anything starts: its sessions (all, or tasks), config,
    local folder, upload prefix. Raises InputError / ConfigError with what to fix.
    """
    config = str(user_path(config))
    require(os.path.isfile(config), f"config not found: {config}", ConfigError)
    on_s3 = sessions.startswith('s3://')
    sessions = sessions.rstrip('/')
    if on_s3:
        require(workdir, f"{sessions}: a local folder (-w / workdir) is needed for sessions on S3")
        names = s3_sessions(sessions)
        root = user_path(workdir)
    else:
        root = user_path(sessions)
        require(root.is_dir(), f"sessions folder not found: {root}")
        names = sorted(p.name for p in root.iterdir() if p.joinpath('raw_videos').is_dir())
    if tasks:
        wanted = tasks.split(',') if isinstance(tasks, str) else [str(t) for t in tasks]
        missing = [t for t in wanted if t not in names]
        require(not missing, f"not found in {sessions}: {missing} (sessions: {names})")
        names = wanted
    require(names, f"no sessions (folders with raw_videos/) in {sessions}")
    require(upload is None or mcap, "upload uploads the MCAP files: needs --mcap")
    require(upload is None or str(upload).startswith('s3://'), f"upload must be an s3:// prefix: {upload}")
    # the videos are deleted only where they can be downloaded again
    require(not cleanup_after or (on_s3 and upload), f"{sessions}: --cleanup needs sessions on s3:// and an upload")
    if name is None:   # station name: the folder above the sessions folder, e.g. station3/industrial_data
        parts = sessions.split('/')
        name = parts[-2] if len(parts) > 1 and parts[-1] == 'industrial_data' else parts[-1]
    return {'name': name, 'sessions': sessions, 'config': config, 'on_s3': on_s3, 'root': root, 'names': names,
        'upload': upload}


# %%
def plan_yield(session: pathlib.Path) -> dict:
    """Episodes and seconds used of dataset_plan.pkl (structured, not parsed from output)."""
    path = session.joinpath('dataset_plan.pkl')
    if not path.is_file():
        return {'episodes': 0, 'seconds': 0.0}
    plan = pickle.load(path.open('rb'))
    seconds = sum(float(e['episode_timestamps'][-1] - e['episode_timestamps'][0]) for e in plan if len(e['episode_timestamps']) > 1)
    return {'episodes': len(plan), 'seconds': seconds}


def recorded_seconds(session: pathlib.Path):
    """
    Length of the recording in seconds, estimated from the episode segmentation (tag_tracking/episodes.json):
    per head video the end of its last episode / idle / rejected span. None if the file is missing or
    has another layout. The yield gate compares the plan against this.
    """
    try:
        videos = json.loads(session.joinpath('tag_tracking', 'episodes.json').read_text())['videos']
        total = 0.0
        for v in videos.values():
            spans = [*v.get('episodes', []), *v.get('idle', []), *v.get('rejected', [])]
            total += max((float(x['end']) for x in spans if isinstance(x, dict) and 'end' in x), default=0.0)
        return total or None
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return None


def sync_accuracies(session: pathlib.Path) -> list:
    """accuracy_ms of every wrist sync fit (03s_sync_wrists.py), [] if the file or field is missing."""
    try:
        videos = json.loads(session.joinpath('tag_tracking', 'wrist_sync.json').read_text())['videos']
        return [float(f['accuracy_ms']) for fits in videos.values() for f in fits.values()
            if isinstance(f, dict) and f.get('accuracy_ms') is not None]
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return []


def quality_gates(session: pathlib.Path, yield_: dict, n_mcap, min_yield: float, max_sync_ms: float) -> list:
    """List of flags (strings); empty = nothing to review."""
    flags = []
    if yield_['episodes'] == 0:
        flags.append("no episodes in the plan")
    total = recorded_seconds(session)
    if total and yield_['seconds'] / total < min_yield:
        flags.append(f"yield {yield_['seconds'] / total:.0%} of {total:.0f} s is below {min_yield:.0%}")
    if n_mcap is not None and n_mcap != yield_['episodes']:
        flags.append(f"{n_mcap} MCAP files for {yield_['episodes']} planned episodes")
    worst = max(sync_accuracies(session), default=None)
    if worst is not None and worst > max_sync_ms:
        flags.append(f"wrist sync accuracy {worst:.1f} ms is above {max_sync_ms:.1f} ms")
    return flags


def export_mcap(session: pathlib.Path, config: str, workers, log_dir, timeout) -> int:
    """
    07_export_mcap.py into dataset_mcap.tmp, then swap. Returns the number of MCAP files.
    The previous dataset_mcap is kept (moved aside) and restored if anything fails.
    """
    tmp = session.joinpath('dataset_mcap.tmp')
    if tmp.exists():   # left by an interrupted run
        stale = session.joinpath(f"dataset_mcap.tmp_stale_{time.strftime('%Y%m%d_%H%M%S')}")
        os.rename(tmp, stale)
        log.warning("%s: moved a leftover export aside to %s", session.name, stale.name)
    cmd = [sys.executable, find_script('scripts_tag_tracking', '07_export_mcap.py'), '-i', session, '-c', config,
        '-o', tmp, '-j', min(workers, 4) if workers else 4]
    result = run_command('mcap', cmd, log_dir.joinpath('mcap.log'), timeout=timeout, cwd=REPO_ROOT)
    result.raise_for_status()
    files = sorted(tmp.glob('*.mcap'))
    require(files, f"{session.name}: the MCAP export wrote no files", PipelineError, step='mcap', log_path=result.log_path)
    final = session.joinpath('dataset_mcap')
    if final.exists() and not any(final.glob('*.mcap')) and not any(final.iterdir()):
        final.rmdir()   # empty folder only
    archived = swap_directory(tmp, final, str(session.joinpath('dataset_mcap')))
    if archived:
        log.info("%s: earlier MCAP files moved to %s", session.name, archived)
    return len(files)


def upload_mcaps(session: pathlib.Path, upload_url: str, workers: int = 4) -> str:
    """Upload dataset_mcap/*.mcap to <upload_url>/, each verified. Returns a one line description."""
    files = sorted(session.joinpath('dataset_mcap').glob('*.mcap'))
    require(files, f"{session.name}: no MCAP files to upload", TransferError)
    base = upload_url.rstrip('/')
    modes, t0 = {}, time.time()
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(s3.upload_verified, p, f"{base}/{p.name}", AWS_PROFILE): p for p in files}
        for f in concurrent.futures.as_completed(futures):
            modes[futures[f].name] = f.result()   # TransferError propagates
    total = sum(p.stat().st_size for p in files)
    kinds = sorted(set(modes.values()))
    return f"uploaded {len(files)} files, {total / 1e9:.1f} GB in {time.time() - t0:.0f} s to {base}/ (verified: {', '.join(kinds)})"


def after_compute(session: pathlib.Path, upload_url, cleanup_after: bool) -> str:
    """Upload and cleanup of one session (runs in the upload thread while the next session is processed)."""
    text = []
    if upload_url:
        text.append(upload_mcaps(session, upload_url))
    if cleanup_after:
        text.append(cleanup(session, upload_url))
    return '; '.join(text)


def process_session(item: dict, opts: dict) -> dict:
    """Run the processing steps of one downloaded session. Returns its result record (status 'ok' / 'failed')."""
    job, name = item['job'], item['name']
    session = job['root'].joinpath(name)
    log_dir = session.joinpath('logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    record = {'station': job['name'], 'session': name, 'status': 'ok', 'failed': None, 'flags': [], 'steps': {},
        'yield': None, 'mcap_files': None, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}
    timeout = opts['timeout']
    workers = opts['num_workers']
    try:
        log.info("============= %s %s =============", job['name'], name)
        cmd = [sys.executable, find_script('run_tag_tracking_pipeline.py'), '-c', job['config'], '-nr',
            '--step_timeout_min', opts['timeout_min']]
        cmd += ['-j', workers] if workers else []
        cmd += ['--resume'] if opts['resume'] else []
        cmd += ['--detect_scale', opts['detect_scale']] if opts['detect_scale'] < 1.0 else []
        t = time.time()
        # the pipeline limits each of its steps itself (--step_timeout_min); the whole run has no limit
        run_command('pipeline', cmd + [session], log_dir.joinpath('pipeline_run.log'), timeout=None,
            cwd=REPO_ROOT).raise_for_status()
        record['steps']['pipeline'] = round(time.time() - t, 1)
        if not opts['no_keep_gaps']:
            t = time.time()
            run_command('plan --keep_gaps', [sys.executable, find_script('scripts_tag_tracking', '06_export_dataset_plan.py'),
                '-i', session, '-c', job['config'], '--keep_gaps'], log_dir.joinpath('plan_keep_gaps.log'),
                timeout=timeout, cwd=REPO_ROOT).raise_for_status()
            record['steps']['plan'] = round(time.time() - t, 1)
        record['yield'] = plan_yield(session)
        if opts['mcap']:
            t = time.time()
            record['mcap_files'] = export_mcap(session, job['config'], workers, log_dir, timeout)
            record['steps']['mcap'] = round(time.time() - t, 1)
        record['flags'] = quality_gates(session, record['yield'], record['mcap_files'], opts['min_yield'],
            opts['max_sync_ms'])
        for flag in record['flags']:
            log.warning("%s %s: FLAG: %s", job['name'], name, flag)
        if record['flags'] and opts['fail_on_flags']:
            record['status'], record['failed'] = 'failed', 'quality gates: ' + '; '.join(record['flags'])
    except PipelineError as e:
        record['status'], record['failed'] = 'failed', str(e)
        log.error("%s %s failed: %s", job['name'], name, e)
    record['minutes'] = round((time.time() - t0) / 60, 1)
    atomic_json_dump(record, log_dir.joinpath('process_station_result.json'))
    return record


def describe(record: dict) -> str:
    y = record['yield']
    text = f"{record['station']} {record['session']}: {record['status']}" + \
        (', flagged' if record['status'] == 'ok' and record['flags'] else '') + f" ({record['minutes']:.0f} min)"
    if record['failed']:
        text += f", {record['failed']}"
    if y:
        text += f"\n  {y['episodes']} episodes, {y['seconds']:.0f} s used" + \
            (f"; {record['mcap_files']} MCAP files" if record['mcap_files'] is not None else '')
    for flag in record['flags']:
        text += f"\n  FLAG: {flag}"
    if record.get('transfer'):
        text += f"\n  {record['transfer']}"
    return text


def run_batch(jobs: list, opts: dict) -> list:
    """
    Process every session of every job. Download of the next session and upload of the finished
    one overlap with the processing of the current one (opts['prefetch']).
    """
    items = [{'job': job, 'name': name} for job in jobs for name in job['names']]
    download_pool = concurrent.futures.ThreadPoolExecutor(1)
    upload_pool = concurrent.futures.ThreadPoolExecutor(1)
    downloads, uploads, records = {}, [], []

    def download(item):
        job, name = item['job'], item['name']
        if not job['on_s3']:
            return None
        t = time.time()
        stats = s3.download_prefix(f"{job['sessions']}/{name}", job['root'].joinpath(name), AWS_PROFILE)
        log.info("%s %s: downloaded in %.0f s", job['name'], name, time.time() - t)
        return stats

    def start_download(k):
        if k < len(items) and k not in downloads:
            downloads[k] = download_pool.submit(download, items[k])

    try:
        for k, item in enumerate(items):
            start_download(k)
            if opts['prefetch']:
                start_download(k + 1)
            try:
                downloads[k].result()
            except (PipelineError, OSError) as e:
                log.error("%s %s: download failed: %s", item['job']['name'], item['name'], e)
                records.append({'station': item['job']['name'], 'session': item['name'], 'status': 'failed',
                    'failed': f"download: {e}", 'flags': [], 'yield': None, 'mcap_files': None, 'minutes': 0.0})
                continue
            record = process_session(item, opts)
            records.append(record)
            if record['status'] == 'ok' and (item['job']['upload'] or opts['cleanup']):
                session = item['job']['root'].joinpath(item['name'])
                future = upload_pool.submit(after_compute, session, item['job']['upload'], opts['cleanup'])
                uploads.append((record, future))
                if not opts['prefetch']:
                    future.exception()   # wait; a failure is reported below
        for record, future in uploads:
            try:
                record['transfer'] = future.result()
                log.info("%s %s: %s", record['station'], record['session'], record['transfer'])
            except (PipelineError, OSError) as e:
                record['status'], record['failed'] = 'failed', f"upload: {e}"
                log.error("%s %s: upload failed, local files kept: %s", record['station'], record['session'], e)
            atomic_json_dump(record, item_log(record, jobs))
    finally:
        download_pool.shutdown(wait=True, cancel_futures=True)
        upload_pool.shutdown(wait=True)
    return records


def item_log(record, jobs):
    job = next(j for j in jobs if j['name'] == record['station'])
    return job['root'].joinpath(record['session'], 'logs', 'process_station_result.json')


# %%
@click.command()
@click.argument('sessions', required=False)
@click.option('-c', '--config', default=None, help="The station's tag tracking config")
@click.option('-w', '--workdir', default=None, help='Local folder for the sessions (required for s3:// sessions)')
@click.option('--tasks', default=None, help='Comma separated session names, default all')
@click.option('--jobs', 'jobs_yaml', default=None,
    help='Several stations, one after the other: yaml list of {sessions, config, workdir, tasks, upload} (instead of SESSIONS)')
@click.option('--no_keep_gaps', is_flag=True, default=False, help='Drop episodes with tracking gaps (no --keep_gaps plan)')
@click.option('--mcap', is_flag=True, default=False, help='Export the episode MCAP files')
@click.option('--upload', default=None, help='s3:// prefix: upload each session\'s MCAP files to <upload>/<session>/')
@click.option('--cleanup', 'cleanup_after', is_flag=True, default=False,
    help='After a verified upload: delete the local videos and MCAP files (sessions on S3 only)')
@click.option('-j', '--num_workers', type=click.IntRange(min=1), default=None, help='Parallel processes per step, default all cores')
@click.option('--resume', is_flag=True, default=False, help='Skip pipeline steps unchanged since they last succeeded')
@click.option('--prefetch/--no_prefetch', default=True, help='Download the next session / upload the last one during processing')
@click.option('--aws_profile', default=None, help='AWS profile for S3 (default: AWS_PROFILE / default chain)')
@click.option('--step_timeout_min', type=float, default=480.0, help='Time limit per step in minutes, 0 = none')
@click.option('--min_yield', type=click.FloatRange(0, 1), default=0.3, help='Flag sessions that use less than this share of the recording')
@click.option('--max_sync_ms', type=float, default=HALF_FRAME_MS, help='Flag wrist sync fits less accurate than this (ms)')
@click.option('--fail_on_flags', is_flag=True, default=False, help='Report flagged sessions as failed')
@click.option('--detect_scale', type=click.FloatRange(0.2, 1.0), default=1.0,
    help='Head tag search scale, 1.0 = original algorithm')
def main(sessions, config, workdir, tasks, jobs_yaml, no_keep_gaps, mcap, upload, cleanup_after, num_workers, resume,
        prefetch, aws_profile, step_timeout_min, min_yield, max_sync_ms, fail_on_flags, detect_scale):
    global AWS_PROFILE
    AWS_PROFILE = aws_profile
    setup_logging()
    if jobs_yaml:
        require(sessions is None and config is None, "--jobs replaces SESSIONS / -c (give them per station in the yaml)")
        try:
            entries = yaml.safe_load(open(str(user_path(jobs_yaml)), 'r'))
        except (OSError, yaml.YAMLError) as e:
            raise InputError(f"{jobs_yaml}: {e}")
        require(isinstance(entries, list) and entries, f"{jobs_yaml}: a list of stations expected")
        for e in entries:
            require(isinstance(e, dict) and 'sessions' in e and 'config' in e, f"{jobs_yaml}: each station needs sessions and config: {e}")
        # every station checked before the first starts
        jobs = [station_job(e['sessions'], e['config'], e.get('workdir'), e.get('tasks'), mcap, e.get('upload'),
            cleanup_after, e.get('name')) for e in entries]
    else:
        require(sessions and config, "SESSIONS and -c, or --jobs")
        jobs = [station_job(sessions, config, workdir, tasks, mcap, upload, cleanup_after)]
    first_root = jobs[0]['root']
    first_root.mkdir(parents=True, exist_ok=True)
    set_log_file(first_root.joinpath(f"process_station_{time.strftime('%Y%m%d_%H%M%S')}.log"))
    for job in jobs:
        log.info("%s: %d sessions: %s", job['name'], len(job['names']), ', '.join(job['names']))

    opts = {'no_keep_gaps': no_keep_gaps, 'mcap': mcap, 'cleanup': cleanup_after, 'num_workers': num_workers,
        'resume': resume, 'prefetch': prefetch, 'timeout': None if step_timeout_min <= 0 else step_timeout_min * 60,
        'timeout_min': step_timeout_min, 'min_yield': min_yield, 'max_sync_ms': max_sync_ms,
        'fail_on_flags': fail_on_flags, 'detect_scale': detect_scale}
    t0 = time.time()
    records = run_batch(jobs, opts)
    print("\n============= summary =============")
    for r in records:
        print(describe(r))
    print(f"total {(time.time() - t0) / 60:.0f} min")
    if any(r['status'] != 'ok' for r in records):
        sys.exit(1)

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
