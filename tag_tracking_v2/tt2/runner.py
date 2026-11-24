"""
Run a child process (a pipeline step or an external tool) and report what happened.

run_command writes the child's combined stdout/stderr to a log file as it arrives (raw chunks, so
progress bars with carriage returns stay live on the console), keeps only the last lines in memory,
enforces a time limit (terminate, then kill), and returns a StepResult. It never raises for a
non-zero exit: the caller decides (see `StepResult.raise_for_status`).

Why not subprocess.run(capture_output=True): that holds all output in memory until the end, shows
nothing while the step runs, and has no timeout.
"""
import collections
import dataclasses
import os
import subprocess
import sys
import threading
import time
from typing import Dict, List, Optional, Sequence

from tt2.errors import PipelineError, StepTimeout
from tt2.log import get_logger

log = get_logger(__name__)
TAIL_LINES = 40


@dataclasses.dataclass
class StepResult:
    name: str
    returncode: int
    seconds: float
    log_path: Optional[str] = None
    timed_out: bool = False
    tail: List[str] = dataclasses.field(default_factory=list)
    skipped: Optional[str] = None   # reason, if the step was not run

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def raise_for_status(self):
        if self.timed_out:
            raise StepTimeout(f"timed out after {self.seconds / 60:.1f} min", self.name, self.log_path)
        if self.returncode != 0:
            last = next((l for l in reversed(self.tail) if l.strip()), '')
            raise PipelineError(f"exit code {self.returncode}: {last}", self.name, self.log_path)

    def to_dict(self) -> dict:
        return {'name': self.name, 'returncode': self.returncode, 'seconds': round(self.seconds, 2),
            'log': self.log_path, 'timed_out': self.timed_out, 'skipped': self.skipped}


def _pump(stream, log_file, console, tail: collections.deque):
    """Copy the child's output to the log file / console; keep the last lines."""
    partial = ''
    fd = stream.fileno()
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        if log_file is not None:
            log_file.write(chunk)
            log_file.flush()
        if console:
            sys.stderr.buffer.write(chunk)
            sys.stderr.flush()
        text = partial + chunk.decode('utf-8', errors='replace')
        lines = text.replace('\r', '\n').split('\n')
        partial = lines.pop()
        tail.extend(l for l in lines if l.strip())
    if partial.strip():
        tail.append(partial)


def run_command(name: str, cmd: Sequence, log_path=None, timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None, cwd=None, console: bool = True) -> StepResult:
    """
    Run `cmd` (list; items are converted with str). timeout in seconds, None for no limit.
    Output goes to log_path (created with its parent folder), to the console if `console`.
    """
    cmd = [str(c) for c in cmd]
    log.info("%s: start: %s", name, ' '.join(cmd))
    full_env = dict(os.environ, PYTHONUNBUFFERED='1', **(env or {}))
    # unchanged scripts of the original repository start further steps with a bare `python`: make that the
    # interpreter running this script, not whatever is (or is not) first on PATH
    full_env['PATH'] = os.path.dirname(os.path.abspath(sys.executable)) + os.pathsep + full_env.get('PATH', '')
    t0 = time.time()
    tail = collections.deque(maxlen=TAIL_LINES)
    log_file = None
    if log_path is not None:
        os.makedirs(os.path.dirname(str(log_path)), exist_ok=True)
        log_file = open(str(log_path), 'wb')
        log_file.write((' '.join(cmd) + '\n').encode())
    timed_out = False
    try:
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=full_env,
                cwd=None if cwd is None else str(cwd))
        except OSError as e:
            log.error("%s: cannot start %s: %s", name, cmd[0], e)
            return StepResult(name, 127, time.time() - t0, None if log_path is None else str(log_path),
                tail=[f"cannot start {cmd[0]}: {e}"])
        pump = threading.Thread(target=_pump, args=(process.stdout, log_file, console, tail), daemon=True)
        pump.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            log.error("%s: timeout after %.0f s, terminating", name, timeout)
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        pump.join(timeout=10)
    finally:
        if log_file is not None:
            log_file.close()
    seconds = time.time() - t0
    result = StepResult(name, process.returncode, seconds, None if log_path is None else str(log_path),
        timed_out, list(tail))
    (log.info if result.ok else log.error)("%s: %s in %.1f s (exit %s)", name, 'done' if result.ok else 'FAILED',
        seconds, process.returncode)
    return result
