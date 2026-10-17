"""Pull latest committed model weights from the git remote."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.config import ROOT


def pull_latest(repo_root: Path | None = None) -> str:
    root = repo_root or ROOT
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            return f"git pull failed ({result.returncode}): {out.strip()}"
        return out.strip() or "Already up to date."
    except FileNotFoundError:
        return "git not available"
