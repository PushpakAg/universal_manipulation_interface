"""
Compare the step times of two pipeline runs: a baseline (original scripts) and a new run (v2).

Baseline: the original pipeline writes <session>/logs/<nn>_<name>.log; a step ran from the log's creation time
to its last write (accurate to about 1 s; macOS birth time, else ctime). New run: <session>/logs/pipeline_timings.json
(per step started / finished / seconds). The session folders may be different folders of the same recording
(e.g. the original run's and a v2 run's), or the same one if the logs were kept apart.

Also reports the process_station summary if <session>/logs/process_station_result.json exists (yield, flags).

python tag_tracking_v2/scripts_tag_tracking/compare_runs.py --baseline data/station1/industrial_data/task01 --new data/v2_run/task01 [-o report.md]
"""
# %%
import sys
import pathlib

V2_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V2_ROOT))
from tt2.bootstrap import setup_paths, user_path
setup_paths(chdir_to_repo=False)

# %%
import json
import os
import re
import click
from tt2.errors import PipelineError, require
from tt2.log import setup_logging, get_logger

log = get_logger(__name__)


def baseline_durations(session: pathlib.Path) -> dict:
    """{step: seconds} from the original step logs (creation -> last write)."""
    out = {}
    for p in sorted(session.joinpath('logs').glob('[0-9][0-9]_*.log')):
        m = re.match(r'\d\d_(.+)\.log$', p.name)
        if not m or m.group(1).startswith(('annotate', 'check')):
            continue
        st = p.stat()
        start = getattr(st, 'st_birthtime', st.st_ctime)
        out[m.group(1)] = max(st.st_mtime - start, 0.0)
    return out


def new_durations(session: pathlib.Path) -> dict:
    """{step: seconds} from pipeline_timings.json (steps that ran; skipped ones count 0)."""
    path = session.joinpath('logs', 'pipeline_timings.json')
    require(path.is_file(), f"{path} not found: was this session run with the v2 pipeline?")
    return {r['name']: float(r.get('seconds') or 0.0) for r in json.loads(path.read_text())}


def table(base: dict, new: dict) -> str:
    names = [n for n in dict.fromkeys([*base, *new])]
    rows = ["| Step | Baseline (min) | New (min) | Change |", "|---|---|---|---|"]
    tb = tn = 0.0
    for n in names:
        b, v = base.get(n), new.get(n)
        tb += b or 0.0
        tn += v or 0.0
        change = f"{(v - b) / b * 100:+.0f}%" if b and v is not None and b > 5 else ''
        rows.append(f"| {n} | {'' if b is None else f'{b / 60:.1f}'} | {'' if v is None else f'{v / 60:.1f}'} | {change} |")
    rows.append(f"| **total (steps listed)** | {tb / 60:.1f} | {tn / 60:.1f} | {(tn - tb) / tb * 100:+.0f}% |" if tb else "")
    return '\n'.join(rows)


@click.command()
@click.option('--baseline', required=True, help='Session folder of the original run (logs/NN_step.log)')
@click.option('--new', required=True, help='Session folder of the v2 run (logs/pipeline_timings.json)')
@click.option('-o', '--output', default=None, help='Write the report as markdown')
def main(baseline, new, output):
    setup_logging()
    b, n = user_path(baseline), user_path(new)
    require(b.is_dir() and n.is_dir(), f"session folders not found: {b} / {n}")
    text = [f"Baseline: {b}", f"New: {n}", '', table(baseline_durations(b), new_durations(n))]
    for label, s in (('Baseline', b), ('New', n)):
        p = s.joinpath('logs', 'process_station_result.json')
        if p.is_file():
            r = json.loads(p.read_text())
            text.append(f"\n{label} result: {r['status']}, yield {r.get('yield')}, MCAP files {r.get('mcap_files')}, flags {r.get('flags')}")
    report = '\n'.join(text)
    print(report)
    if output:
        user_path(output).write_text(report + '\n')

# %%
if __name__ == "__main__":
    try:
        main(standalone_mode=False)
    except (PipelineError, click.ClickException) as e:
        get_logger(__name__).error("%s", e)
        sys.exit(1)
