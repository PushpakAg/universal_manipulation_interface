"""
Import paths and path helpers for scripts of tag_tracking_v2.

The v2 folder holds changed copies of some scripts and library modules. Everything else (umi.*,
the unchanged pipeline scripts) is imported or run from the original repository, the parent of the
v2 folder. v2 paths come first, so a v2 module shadows nothing in `umi` (v2 modules are `tt2.*`).

Scripts of the original repository run with the repository root as working directory, and the
config yaml refers to files relative to it. The v2 scripts keep that, but resolve every path the
USER gives on the command line against the directory the script was started from, so that
`-i data/x` means the same thing in any directory.
"""
import os
import pathlib
import sys

V2_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = V2_ROOT.parent
START_DIR = pathlib.Path(os.getcwd())


def setup_paths(chdir_to_repo: bool = True):
    """Put V2_ROOT and REPO_ROOT on sys.path (once); optionally make the repo root the working directory."""
    for p in (str(REPO_ROOT), str(V2_ROOT)):   # V2_ROOT ends up first
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    if chdir_to_repo:
        os.chdir(REPO_ROOT)


def user_path(p) -> pathlib.Path:
    """Absolute path of a command line path: ~ expanded, relative to the directory the script was started in."""
    p = pathlib.Path(os.path.expanduser(str(p)))
    return p if p.is_absolute() else START_DIR / p


def find_script(*relative_parts: str) -> pathlib.Path:
    """Path of a pipeline script: the v2 copy if there is one, else the original."""
    for root in (V2_ROOT, REPO_ROOT):
        p = root.joinpath(*relative_parts)
        if p.is_file():
            return p
    raise FileNotFoundError(f"script not found in {V2_ROOT} or {REPO_ROOT}: {'/'.join(relative_parts)}")
