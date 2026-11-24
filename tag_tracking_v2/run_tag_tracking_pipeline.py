"""
Tag tracking (GTSAM) pipeline, v2 of run_tag_tracking_pipeline.py: gripper poses from tag cubes
observed by a head camera, instead of wrist camera SLAM.

Same steps, same outputs, same log names (<session>/logs/<nn>_<name>.log) as the original; see
README_tag_tracking.md for what each step does. What is different:

Reliability
- every step runs with the SAME Python as this script (sys.executable), not `python` from PATH;
- a step has a time limit (--step_timeout_min, default 480, 0 = none); on timeout it is terminated;
- inputs are checked before the first step (config sections, files, session layout) with messages
  that say what to fix, not with bare asserts;
- a failing session does not stop the others; the exit code is 1 if any session failed;
- every step is logged (start, end, duration, exit code) through `logging`; the full step output is in its log file.

Throughput / latency
- --overlap_imu runs imu (Docker) at the same time as wrist_tags (CPU bound). Off by default: on the 8-core test machine
  it gave no gain (the two compete for the cores);
- --resume skips the leading steps whose inputs, arguments, config and script are unchanged since
  they last succeeded (fingerprint in <session>/logs/.state/). The first step that has to run
  makes every later step run, so a skipped step is never stale. Without --resume everything runs, as in the original;
- the changed scripts (00_detect_tag_corners, 03_track_bodies, 03b, 03c, 06, 07) come from this
  folder, the rest from the original repository.

Records
- <session>/logs/pipeline_timings.json: per step start, end, seconds, exit code, skipped or not.

python tag_tracking_v2/run_tag_tracking_pipeline.py -c umi_calib/tag_tracking.yaml <session_dir>
python tag_tracking_v2/run_tag_tracking_pipeline.py -c umi_calib/tag_tracking.yaml --stop_after calibrate_bodies <session_dir>
python tag_tracking_v2/run_tag_tracking_pipeline.py -c umi_calib/tag_tracking.yaml -j 16 --resume <session_dir>
"""
# %%
import os
import pathlib
import sys

V2_ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(V2_ROOT))
from tt2.bootstrap import setup_paths, user_path, find_script, REPO_ROOT
setup_paths()

# %%
import concurrent.futures
import json
import time
import click
import yaml
from tt2.errors import ConfigError, InputError, PipelineError, require
from tt2.fsutil import atomic_json_dump, fingerprint
from tt2.log import setup_logging, set_log_file, get_logger
from tt2.runner import run_command, StepResult

log = get_logger(__name__)

STEP_NAMES = ['sort_videos', 'imu', 'wrist_tags', 'gripper_range', 'audio_sync', 'head_tags',
    'segment_episodes', 'use_setup', 'calibrate_bodies', 'track_bodies', 'fuse_head_imu', 'trim_docking', 'gripper_tcp', 'sync_wrists',
    'fuse_grippers',
    'render', 'export_plan']
# steps that may run at the same time (independent inputs, one CPU bound, one waiting on a container)
OVERLAP = ('imu', 'wrist_tags')


# %%
def build_steps(session, config_path, config_yaml, aruco_config, gripper_config, camera_intrinsics, workers,
        detect_scale):
    """
    {step: (script path, args)} for one session. Scripts: the v2 copy if this folder has one,
    else the original (scripts_slam_pipeline / scripts_tag_tracking).
    """
    demos_dir = session.joinpath('demos')
    tag_args = ['-i', session, '-c', config_path]
    slam = lambda name: find_script('scripts_slam_pipeline', name)
    tag = lambda name: find_script('scripts_tag_tracking', name)
    scale = [] if detect_scale >= 1.0 else ['--detect_scale', detect_scale]
    return {
        'sort_videos': (slam('00_process_videos.py'), [session, '--strict']),
        'imu': (slam('01_extract_gopro_imu.py'), [session] + workers),
        'wrist_tags': (slam('04_detect_aruco.py'), ['--input_dir', demos_dir,
            '--camera_intrinsics', camera_intrinsics, '--aruco_yaml', aruco_config,
            '--tag_tracking_config', config_path, '--wrist_only'] + workers),
        'gripper_range': (slam('05_run_calibrations.py'),
            [session, '--gripper_config', gripper_config, '--skip_slam_tag']),
        'audio_sync': (slam('06a_estimate_audio_sync.py'), ['--input', session] + workers),
        'head_tags': (tag('00_detect_tag_corners.py'), tag_args + workers_n(workers) + scale),
        'segment_episodes': (tag('00b_segment_episodes.py'), tag_args),
        'use_setup': (tag('00c_use_setup.py'), tag_args),
        'calibrate_bodies': (tag('02_calibrate_bodies.py'), tag_args),
        'track_bodies': (tag('03_track_bodies.py'), tag_args + workers),
        'fuse_head_imu': (tag('03b_fuse_head_imu.py'), tag_args + workers),
        'trim_docking': (tag('03t_trim_docking.py'), tag_args),
        'sync_wrists': (tag('03s_sync_wrists.py'), tag_args),
        'fuse_grippers': (tag('03c_fuse_gripper_imu.py'), tag_args + workers),
        'gripper_tcp': (tag('05_calibrate_gripper_tcp.py'), tag_args),
        'render': (tag('04_render_tracking.py'), tag_args),
        'export_plan': (tag('06_export_dataset_plan.py'), tag_args),
    }


def workers_n(workers):
    """00_detect_tag_corners takes -n, the others --num_workers."""
    return ['-n', workers[1]] if workers else []


def skip_reasons(config_yaml, no_render):
    """{step: reason or None} from the config: steps that do not apply."""
    has = lambda k: k in config_yaml
    return {
        'fuse_head_imu': None if has('head_imu') else "no head_imu in config",
        'segment_episodes': None if has('episodes') else "no episodes in config (one take = one demo)",
        'render': "--no_render" if no_render else None,
        'fuse_grippers': None if has('gripper_imu') else "no gripper_imu in config",
        'trim_docking': None if has('episodes') else "no episodes in config",
        'sync_wrists': None if (has('gripper_imu') and has('episodes')) else "needs episodes and gripper_imu in config",
        # setup calibration (calibrate_setup.py) replaces per-session calibration
        'use_setup': None if has('setup_calibration') else "no setup_calibration in config",
        'calibrate_bodies': "using setup_calibration" if has('setup_calibration') else None,
        'gripper_tcp': "using setup_calibration" if has('setup_calibration') else None,
    }


def step_fingerprint(name, script, args, config_files, session) -> str:
    """
    Identity of a step run: script content, arguments (without worker count), config files and the
    raw videos (names and sizes). Equal fingerprint + the cascade rule = the step would redo the same work.
    """
    raw = session.joinpath('raw_videos')
    videos = sorted((str(p.relative_to(raw)), p.stat().st_size) for p in raw.rglob('*')
        if p.suffix.lower() == '.mp4' and p.exists()) if raw.is_dir() else []
    shown = [str(a) for a in args]
    return fingerprint([script, *config_files], [name, shown, videos])


def state_path(log_dir, name):
    return log_dir.joinpath('.state', f"{name}.json")


def is_done(log_dir, name, fp) -> bool:
    try:
        return json.loads(state_path(log_dir, name).read_text()).get('fingerprint') == fp
    except (OSError, ValueError):
        return False


def mark_done(log_dir, name, fp):
    atomic_json_dump({'fingerprint': fp, 'finished': time.strftime('%Y-%m-%d %H:%M:%S')}, state_path(log_dir, name))


def plan_execution(order, steps, skip, resume, log_dir, config_files, session):
    """
    Decide per step: ('skip', reason), ('cached', None) or ('run', fingerprint).
    A step that runs makes all later steps run (their inputs may have changed).
    """
    plan, dirty = {}, not resume
    for i, name in order:
        if skip.get(name) is not None:
            plan[name] = ('skip', skip[name])
            continue
        script, args = steps[name]
        fp = step_fingerprint(name, script, args, config_files, session)
        if not dirty and is_done(log_dir, name, fp):
            plan[name] = ('cached', None)
        else:
            dirty = True
            plan[name] = ('run', fp)
    return plan


def run_stages(session, order, steps, plan, log_dir, step_timeout, overlap, timings_path, records):
    """Run the planned steps in order; imu and wrist_tags together if overlap. Raises PipelineError on the first failure."""
    todo = [(i, n) for i, n in order if plan[n][0] == 'run']
    stages, k = [], 0
    while k < len(todo):
        names = [todo[k][1]]
        if overlap and names[0] == OVERLAP[0] and k + 1 < len(todo) and todo[k + 1][1] == OVERLAP[1]:
            names.append(todo[k + 1][1])
        stages.append([(todo[k + j][0], n) for j, n in enumerate(names)])
        k += len(names)

    def one(i, name):
        script, args = steps[name]
        assert script.is_file(), script
        started = time.strftime('%Y-%m-%d %H:%M:%S')
        result = run_command(name, [sys.executable, script] + [str(a) for a in args],
            log_dir.joinpath(f"{i:02d}_{name}.log"), timeout=step_timeout, cwd=REPO_ROOT)
        records[name] = dict(result.to_dict(), started=started, finished=time.strftime('%Y-%m-%d %H:%M:%S'))
        atomic_json_dump(list(records.values()), timings_path)
        if result.ok:
            mark_done(log_dir, name, plan[name][1])
        return result

    for stage in stages:
        if len(stage) == 1:
            results = [one(*stage[0])]
        else:
            log.info("running %s at the same time", ' and '.join(n for _, n in stage))
            with concurrent.futures.ThreadPoolExecutor(len(stage)) as pool:
                results = [f.result() for f in [pool.submit(one, i, n) for i, n in stage]]
        for r in results:
            r.raise_for_status()


# %%
@click.command()
@click.argument('session_dir', nargs=-1)
@click.option('-c', '--config', required=True, help='Tag tracking config yaml, see umi/tag_tracking/config.py')
@click.option('-ci', '--camera_intrinsics', default=None,
    help='Fallback intrinsics json for 04_detect_aruco.py (cameras not in the config), default gopro_intrinsics_2_7k.json next to the config')
@click.option('-sf', '--start_from', type=click.Choice(STEP_NAMES), default=STEP_NAMES[0], help='First step to run')
@click.option('-sa', '--stop_after', type=click.Choice(STEP_NAMES), default=STEP_NAMES[-1], help='Last step to run')
@click.option('-nr', '--no_render', is_flag=True, default=False, help='Skip the render step')
@click.option('-j', '--num_workers', type=click.IntRange(min=1), default=None,
    help='Parallel processes for imu, wrist_tags, audio_sync, head_tags, track_bodies and fuse_head_imu, default all cores')
@click.option('--resume', is_flag=True, default=False, help='Skip leading steps unchanged since they last succeeded')
@click.option('--overlap_imu/--no_overlap_imu', default=False,
    help='Run imu and wrist_tags at the same time (off by default: no gain measured on 8 cores, see CHANGELOG_v2.md)')
@click.option('--step_timeout_min', type=float, default=480.0, help='Time limit per step in minutes, 0 = none')
@click.option('--detect_scale', type=click.FloatRange(0.2, 1.0), default=1.0,
    help='Head tag search scale (1.0 = original algorithm; below 1.0 validate with compare_detection.py)')
def main(session_dir, config, camera_intrinsics, start_from, stop_after, no_render, num_workers, resume,
        overlap_imu, step_timeout_min, detect_scale):
    setup_logging()
    require(session_dir, "give at least one session directory")
    first, last = STEP_NAMES.index(start_from), STEP_NAMES.index(stop_after)
    require(first <= last, "--start_from must not come after --stop_after")

    config_path = user_path(config)
    require(config_path.is_file(), f"config not found: {config_path}")
    config_dir = config_path.parent
    try:
        config_yaml = yaml.safe_load(config_path.open('r'))
    except yaml.YAMLError as e:
        raise ConfigError(f"{config_path}: invalid yaml: {e}")
    require(isinstance(config_yaml, dict) and 'aruco_config' in config_yaml, f"{config_path}: no aruco_config", ConfigError)
    require('gripper_config' in config_yaml, "tag tracking config needs gripper_config", ConfigError)
    aruco_config = config_dir.joinpath(config_yaml['aruco_config'])
    gripper_config = config_dir.joinpath(config_yaml['gripper_config'])
    camera_intrinsics = user_path(camera_intrinsics) if camera_intrinsics else config_dir.joinpath('gopro_intrinsics_2_7k.json')
    for path in [aruco_config, gripper_config, camera_intrinsics]:
        require(path.is_file(), f"file referenced by the config not found: {path}", ConfigError)
    workers = [] if num_workers is None else ['--num_workers', num_workers]
    step_timeout = None if step_timeout_min <= 0 else step_timeout_min * 60
    config_files = [config_path, aruco_config, gripper_config, camera_intrinsics]

    failed = []
    for session in session_dir:
        session = user_path(session)
        t0 = time.time()
        try:
            require(session.is_dir(), f"session folder not found: {session}")
            require(session.joinpath('raw_videos').is_dir(), f"{session}: no raw_videos/ folder (sort_recordings.py --tasks)")
            log_dir = session.joinpath('logs')
            log_dir.mkdir(exist_ok=True)
            set_log_file(log_dir.joinpath('pipeline.log'))
            log.info("============= %s =============", session)
            steps = build_steps(session, config_path, config_yaml, aruco_config, gripper_config, camera_intrinsics,
                workers, detect_scale)
            require(set(steps) == set(STEP_NAMES), "internal: steps and STEP_NAMES differ", PipelineError)
            skip = skip_reasons(config_yaml, no_render)
            order = list(enumerate(STEP_NAMES))[first:last + 1]
            plan = plan_execution(order, steps, skip, resume, log_dir, config_files, session)
            records = {}
            for i, name in order:
                kind, info = plan[name]
                if kind == 'skip':
                    log.info("Skipping %s: %s", name, info)
                    records[name] = {'name': name, 'skipped': info}
                elif kind == 'cached':
                    log.info("Skipping %s: unchanged since it last succeeded (--resume)", name)
                    records[name] = {'name': name, 'skipped': 'resume: unchanged'}
            run_stages(session, order, steps, plan, log_dir, step_timeout, overlap_imu,
                log_dir.joinpath('pipeline_timings.json'), records)
            log.info("Done %s: steps %s to %s in %.1f min, logs in %s", session.name, start_from, stop_after,
                (time.time() - t0) / 60, log_dir)
        except PipelineError as e:
            log.error("session %s failed: %s", session.name, e)
            failed.append(session.name)
    if failed:
        raise PipelineError(f"{len(failed)} of {len(session_dir)} sessions failed: {', '.join(failed)}")

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
