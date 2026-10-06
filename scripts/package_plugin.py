#!/usr/bin/env python3
"""Build a deterministic, minimal ZIP of the plugin in one of two editions.

full       What the GitHub marketplace installs: skills, the shared runner, and the
           Codex lifecycle hooks.
directory  What the public Plugins Directory accepts today. The directory refuses
           packages with lifecycle hooks, so this edition drops `hooks/`, copies the
           runner into each skill so every skill bundle is self-contained, and gates
           each skill to Codex in its `agents/openai.yaml`. Gates are then held by the
           runner's integrity check alone; the runner reports that edition in status.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import sys
import zipfile

from validate_release import ROOT, ReleaseValidationError, validate


EDITIONS = ("full", "directory")
RUNNER = "scripts/truedev_workflow.py"
SKILLS = ("lifecycle", "project-init")
INCLUDED_FILES = (
    "LICENSE",
    "PRIVACY.md",
    "SECURITY.md",
    "SUPPORT.md",
    "TERMS.md",
)
INCLUDED_TREES = (".codex-plugin", "assets", "hooks", "skills")
DIRECTORY_EXCLUDED_TREES = frozenset({"hooks"})
EXCLUDED_NAMES = {"__pycache__", ".ruff_cache", ".pytest_cache", "dist", "evals"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}
CODEX_ONLY_POLICY = '  products:\n    - "CODEX"\n'


def package_files(edition: str = "full") -> list[Path]:
    trees = [tree for tree in INCLUDED_TREES if edition == "full" or tree not in DIRECTORY_EXCLUDED_TREES]
    paths = [ROOT / name for name in INCLUDED_FILES]
    if edition == "full":
        paths.append(ROOT / RUNNER)
    for tree in trees:
        for path in (ROOT / tree).rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDED_NAMES for part in relative.parts) or path.suffix in EXCLUDED_SUFFIXES:
                continue
            paths.append(path)
    unique = sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix())
    for path in unique:
        if path.is_symlink():
            raise ReleaseValidationError(f"submission archive cannot contain a symlink: {path}")
    return unique


def gate_skill_to_codex(text: str) -> str:
    """Add `products: [CODEX]` under the existing policy mapping.

    The directory serves ChatGPT and Codex from one listing, and these skills need a
    local repository, Git, and Python that a ChatGPT conversation does not have.
    """
    if "\nproducts:" in text or "\n  products:" in text:
        raise ReleaseValidationError("agents/openai.yaml already declares products")
    marker = "\npolicy:\n"
    if marker not in text:
        raise ReleaseValidationError("agents/openai.yaml must declare a policy mapping")
    head, tail = text.split(marker, 1)
    if not tail.endswith("\n"):
        tail += "\n"
    return f"{head}{marker}{tail}{CODEX_ONLY_POLICY}"


def archive_entries(edition: str = "full") -> list[tuple[str, bytes]]:
    if edition not in EDITIONS:
        raise ReleaseValidationError(f"unknown edition: {edition}")
    entries: dict[str, bytes] = {}
    for path in package_files(edition):
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        if edition == "directory" and relative.startswith("skills/") and relative.endswith("/agents/openai.yaml"):
            data = gate_skill_to_codex(data.decode("utf-8")).encode("utf-8")
        entries[relative] = data
    if edition == "directory":
        runner = (ROOT / RUNNER).read_bytes()
        for skill in SKILLS:
            entries[f"skills/{skill}/{RUNNER}"] = runner
    return sorted(entries.items())


def default_output(version: str, edition: str = "full") -> Path:
    suffix = "" if edition == "full" else f"-{edition}"
    return ROOT / "dist" / f"truedev-workflow-{version}{suffix}.zip"


def build(output: Path | None = None, edition: str = "full") -> Path:
    manifest = validate()
    output = (output or default_output(manifest["version"], edition)).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in archive_entries(edition):
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o755 if relative.endswith((".py",)) else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data)
    print(f"Built {output} ({output.stat().st_size} bytes) for {manifest['version']} ({edition} edition).")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--edition", choices=EDITIONS, default="full")
    args = parser.parse_args(argv)
    try:
        build(args.output, args.edition)
    except (OSError, ReleaseValidationError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
