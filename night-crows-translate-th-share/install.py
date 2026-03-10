#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def install_requirements(repo_root: Path, skip_pip: bool) -> None:
    requirements = repo_root / "requirements.txt"
    if skip_pip or not requirements.exists():
        return

    cmd = [sys.executable, "-m", "pip", "install", "--user", "-r", str(requirements)]
    print("Installing Python dependencies:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def install_skills(repo_root: Path, codex_home: Path) -> None:
    source_root = repo_root / "skills"
    destination_root = codex_home / "skills"
    destination_root.mkdir(parents=True, exist_ok=True)

    for source_dir in sorted(source_root.iterdir()):
        if not source_dir.is_dir():
            continue
        destination_dir = destination_root / source_dir.name
        if destination_dir.exists():
            shutil.rmtree(destination_dir)
        shutil.copytree(source_dir, destination_dir, ignore=shutil.ignore_patterns(".DS_Store"))
        print(f"Installed {source_dir.name} -> {destination_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install shared Codex skills from this repo.")
    parser.add_argument(
        "--dest",
        help="Override CODEX_HOME. Defaults to $CODEX_HOME or ~/.codex",
    )
    parser.add_argument(
        "--no-pip",
        action="store_true",
        help="Skip pip install for requirements.txt",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    codex_home = Path(args.dest or os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()

    install_requirements(repo_root, args.no_pip)
    install_skills(repo_root, codex_home)

    print("Restart Codex to pick up the installed skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
