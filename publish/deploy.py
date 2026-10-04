"""Publish build/site to the gh-pages branch as a single orphan commit (force-pushed).

History is deliberately discarded: the site is regenerated data, and keeping every daily
snapshot would bloat the repo. Only gh-pages is ever force-pushed, never main. GitHub Pages
must be set to serve the gh-pages branch.

Usage:
    python -m publish.build && python -m publish.deploy
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).parents[1]
BRANCH = "gh-pages"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def deploy(site: Path):
    remote = git(REPO, "remote", "get-url", "origin")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        shutil.copytree(site, work)
        git(work, "init", "-q", "-b", BRANCH)
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "Publish site")
        git(work, "push", "-q", "--force", remote, f"{BRANCH}:{BRANCH}")
    print(f"[deploy] {site} -> {remote} {BRANCH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=Path("build/site"))
    deploy(parser.parse_args().site)
