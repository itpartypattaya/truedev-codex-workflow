#!/usr/bin/env python3
"""Build a deterministic, minimal ZIP for the skills-only plugin submission."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import sys
import zipfile

from validate_release import ROOT, ReleaseValidationError, validate


INCLUDED_FILES = (
    "LICENSE",
    "PRIVACY.md",
    "SECURITY.md",
    "SUPPORT.md",
    "TERMS.md",
    "scripts/truedev_workflow.py",
)
INCLUDED_TREES = (".codex-plugin", "assets", "hooks", "skills")
EXCLUDED_NAMES = {"__pycache__", ".ruff_cache", ".pytest_cache", "dist"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def package_files() -> list[Path]:
    paths = [ROOT / name for name in INCLUDED_FILES]
    for tree in INCLUDED_TREES:
        for path in (ROOT / tree).rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDED_NAMES for part in path.parts) or path.suffix in EXCLUDED_SUFFIXES:
                continue
            paths.append(path)
    unique = sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix())
    for path in unique:
        if path.is_symlink():
            raise ReleaseValidationError(f"submission archive cannot contain a symlink: {path}")
    return unique


def build(output: Path) -> Path:
    manifest = validate()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in package_files():
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o755 if relative.endswith((".py",)) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, path.read_bytes())
    print(f"Built {output} ({output.stat().st_size} bytes) for {manifest['version']}.")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default = ROOT / "dist" / "truedev-workflow-1.0.0.zip"
    parser.add_argument("--output", type=Path, default=default)
    args = parser.parse_args(argv)
    try:
        build(args.output)
    except (OSError, ReleaseValidationError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
