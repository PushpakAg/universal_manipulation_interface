"""
Swap left and right in exported episodes (14_export_rhoda.py / 15_export_episode_videos.py layout) whose
grippers were in the other hands than the config said: per episode folder
  <rec>_left.mp4 <-> <rec>_right.mp4, <rec>_left_gripper.csv <-> <rec>_right_gripper.csv (renamed, the
  files themselves unchanged), meta.json: the left / right camera records swapped and
  "left_right_swapped" added (date, what was done), <rec>_mosaic.mp4 rendered again (left wrist bottom
  left) if the episode had one. Then checked as an export (14_export_rhoda.check_outputs) and written
  back: S3 uploaded with meta.json last, sizes checked; a local folder replaced file by file.
An episode whose meta.json has "left_right_swapped" is skipped, so a list can be run again. An episode
prepared in -w but not uploaded (stopped run) is uploaded from there on the next run, not swapped twice.

LIST: a text / CSV file with one path per line, an episode folder or any file in it (s3:// or local,
e.g. the episodes' mosaic URLs); other lines (a header) are ignored. Several files of one episode count once.

python scripts_tag_tracking/swap_left_right.py left_right_switch.csv -w ~/swap_work -j 4 [--dry_run]
"""
# %%
import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# %%
import concurrent.futures
import datetime
import importlib
import json
import pathlib
import re
import shutil
import subprocess
from fractions import Fraction
import click

rhoda = importlib.import_module('14_export_rhoda')
EPISODE = re.compile(r'^(.*/episode_\d+)(/.*)?$')
NOTE = 'hands were swapped while recording: left / right mp4s, gripper CSVs and camera records swapped, mosaic rendered again'


def episode_folders(list_path: str) -> list:
    """
    Episode folders (no trailing /) from the list, in its order, each once.
    """
    out = list()
    for line in pathlib.Path(os.path.expanduser(list_path)).read_text().splitlines():
        line = line.strip().strip('"').split(',')[0].strip()
        m = EPISODE.match(line.rstrip('/'))
        if (line.startswith('s3://') or line.startswith('/') or line.startswith('~')) and m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def list_names(folder: str) -> list:
    if folder.startswith('s3://'):
        out = subprocess.run(['aws', 's3', 'ls', folder + '/'], capture_output=True, text=True)
        return [line.split()[-1] for line in out.stdout.splitlines() if line.strip() and not line.strip().startswith('PRE')]
    p = pathlib.Path(os.path.expanduser(folder))
    return sorted(x.name for x in p.iterdir() if x.is_file()) if p.is_dir() else []


def read_text(path: str) -> str:
    if path.startswith('s3://'):
        return subprocess.run(['aws', 's3', 'cp', path, '-'], check=True, capture_output=True, text=True).stdout
    return pathlib.Path(os.path.expanduser(path)).read_text()


def fetch(folder: str, names: list, local: pathlib.Path):
    local.mkdir(parents=True)
    for name in names:
        if folder.startswith('s3://'):
            subprocess.run(['aws', 's3', 'cp', f"{folder}/{name}", str(local.joinpath(name)), '--only-show-errors'],
                check=True, capture_output=True)
        else:
            shutil.copy2(pathlib.Path(os.path.expanduser(folder)).joinpath(name), local.joinpath(name))


def put(local: pathlib.Path, folder: str):
    """
    The swapped episode back, meta.json last (on S3 a recording with meta.json is complete).
    """
    if folder.startswith('s3://'):
        rhoda.upload_recording(local, folder)
        return
    names = sorted(p.name for p in local.iterdir())
    for name in [n for n in names if not n.endswith('_meta.json')] + [n for n in names if n.endswith('_meta.json')]:
        shutil.copy2(local.joinpath(name), pathlib.Path(os.path.expanduser(folder)).joinpath(name))


def probe(path: pathlib.Path) -> dict:
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
        'stream=r_frame_rate,nb_read_packets', '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)['streams'][0]


def swap_local(local: pathlib.Path, rec: str, encoder: str, threads: int) -> dict:
    """
    The swap in a downloaded episode folder; returns {'frames', 'mosaic'}. Raises if a file is missing
    or the result fails the export check.
    """
    meta_path = local.joinpath(f"{rec}_meta.json")
    meta = json.loads(meta_path.read_text())
    pairs = [(f"{rec}_left.mp4", f"{rec}_right.mp4")]
    if all(local.joinpath(f"{rec}_{s}_gripper.csv").is_file() for s in ('left', 'right')):
        pairs.append((f"{rec}_left_gripper.csv", f"{rec}_right_gripper.csv"))
    for a, b in pairs:
        assert local.joinpath(a).is_file() and local.joinpath(b).is_file(), f"{a} / {b} missing"
        tmp = local.joinpath(a + '.swap')
        local.joinpath(a).rename(tmp)
        local.joinpath(b).rename(local.joinpath(a))
        tmp.rename(local.joinpath(b))
    if meta.get('cameras') and 'left' in meta['cameras'] and 'right' in meta['cameras']:
        meta['cameras']['left'], meta['cameras']['right'] = meta['cameras']['right'], meta['cameras']['left']
    meta['left_right_swapped'] = {'date': datetime.date.today().isoformat(), 'note': NOTE}
    meta_path.write_text(json.dumps(meta, indent=2))

    head = probe(local.joinpath(meta['files']['head']))
    n, fps = int(head['nb_read_packets']), float(Fraction(head['r_frame_rate']))
    with_mosaic = local.joinpath(f"{rec}_mosaic.mp4").is_file()
    if with_mosaic:
        rhoda.mosaic(*((local.joinpath(meta['files'][x]), 0) for x in ('head', 'right', 'left')), n,
            local.joinpath(f"{rec}_mosaic.mp4"), fps, encoder, threads=threads)
    rhoda.check_outputs(local, rec, {'files': meta['files'], 'n_frames': n, 'fps': fps}, with_mosaic)
    return {'frames': n, 'mosaic': with_mosaic}


def swap_episode(folder: str, workdir: pathlib.Path, encoder: str, threads: int, dry_run: bool) -> dict:
    entry = {'episode': folder}
    key = re.sub(r'^s3://[^/]+/', '', folder).lstrip('/~')
    local = workdir.joinpath(key)
    prepared = workdir.joinpath(key + '.prepared')
    stage = 'read'
    try:
        names = list_names(folder)
        metas = [n for n in names if n.endswith('_meta.json')]
        if len(metas) != 1:
            return {**entry, 'status': 'failed', 'detail': f"{len(metas)} meta.json files ({len(names)} files)"}
        rec = metas[0][:-len('_meta.json')]
        if json.loads(read_text(f"{folder}/{metas[0]}")).get('left_right_swapped'):
            return {**entry, 'status': 'skipped', 'detail': 'already swapped'}
        if dry_run:
            return {**entry, 'status': 'would swap', 'detail': ', '.join(names)}
        if prepared.is_file() and local.is_dir():
            result = json.loads(prepared.read_text())      # swapped in a stopped run, not uploaded yet
        else:
            if local.exists():
                shutil.rmtree(local)
            stage = 'download'
            fetch(folder, names, local)
            stage = 'swap'
            result = swap_local(local, rec, encoder, threads)
            prepared.write_text(json.dumps(result))
        stage = 'upload'
        put(local, folder)
        shutil.rmtree(local)
        prepared.unlink()
        return {**entry, 'status': 'swapped', **result}
    except Exception as e:
        stderr = getattr(e, 'stderr', None)
        stderr = stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr
        detail = (stderr.strip() if stderr else str(e)) or type(e).__name__
        if stage in ('download', 'swap') and local.exists():
            shutil.rmtree(local)        # nothing written back: start over next run
        return {**entry, 'status': 'failed', 'detail': f"{stage}: {detail.splitlines()[-1][:300]}"}


# %%
@click.command()
@click.argument('list_path')
@click.option('-w', '--workdir', default='~/swap_left_right_work', help='Local folder for the episodes being swapped')
@click.option('-j', '--jobs', type=int, default=4, help='Episodes at the same time')
@click.option('--encoder', default='libx264', help='Mosaic encoder (libx264, h264_nvenc)')
@click.option('--dry_run', is_flag=True, default=False, help='Only list what would be swapped')
def main(list_path, workdir, jobs, encoder, dry_run):
    folders = episode_folders(list_path)
    workdir = pathlib.Path(os.path.expanduser(workdir)).absolute()
    workdir.mkdir(parents=True, exist_ok=True)
    threads = max(1, (os.cpu_count() or 1) // max(jobs, 1))
    print(f"{len(folders)} episodes from {list_path}" + (" (dry run)" if dry_run else f", {jobs} at a time"), flush=True)
    results = list()
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(swap_episode, f, workdir, encoder, threads, dry_run) for f in folders]
        for k, fut in enumerate(futures, start=1):
            r = fut.result()
            results.append(r)
            print(f"[{k}/{len(folders)}] {r['status']}: {r['episode']}"
                + (f" ({r['detail']})" if r.get('detail') and r['status'] != 'would swap' else '')
                + (f" ({r['frames']} frames{', mosaic' if r['mosaic'] else ''})" if r['status'] == 'swapped' else ''),
                flush=True)
    counts = {s: sum(r['status'] == s for r in results) for s in ('swapped', 'would swap', 'skipped', 'failed')}
    log = workdir.joinpath(f"swap_{datetime.datetime.now():%Y%m%d_%H%M%S}.json")
    log.write_text(json.dumps(results, indent=2))
    print('done: ' + ', '.join(f"{v} {k}" for k, v in counts.items() if v) + f"; log {log}")
    if counts['failed']:
        sys.exit(1)


# %%
if __name__ == "__main__":
    main()
