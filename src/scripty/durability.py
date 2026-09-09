"""Export/restore of project rows through the frames bucket (gs://scripty-frames/db/<project>/)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from . import db

BUCKET = os.getenv("SCRIPTY_BUCKET", "gs://scripty-frames")


def backup(project: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        counts = db.export_project(project, d)
        subprocess.run(["gcloud", "storage", "rsync", "--recursive", d, f"{BUCKET}/db/{project}"], check=True, capture_output=True)
    return counts


def restore_all_if_empty() -> dict:
    """On app boot: if ClickHouse has no frames, pull every exported project back in.

    ensure_schema() runs first: the node's disk is ephemeral, so a restart drops the database
    itself, not just the rows. Asking is_empty() first raises UNKNOWN_DATABASE and the caller
    skips the restore — the one path meant to survive a wipe failing on exactly a wipe.
    """
    db.ensure_schema()
    if not db.is_empty():
        return {"restored": False}
    out = {}
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["gcloud", "storage", "rsync", "--recursive", f"{BUCKET}/db", d], capture_output=True, text=True)
        if r.returncode != 0:
            return {"restored": False, "error": r.stderr[-200:]}
        for pdir in Path(d).iterdir():
            if pdir.is_dir():
                out[pdir.name] = db.restore_dir(pdir)
    return {"restored": True, "projects": out}
