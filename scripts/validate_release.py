#!/usr/bin/env python3
"""Validate the repository contract required for a public TrueDev plugin build."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
PUBLIC_FILES = ("PRIVACY.md", "TERMS.md", "SUPPORT.md", "SECURITY.md", "LICENSE")
IMAGE_FIELDS = ("composerIcon", "logo", "logoDark")


class ReleaseValidationError(RuntimeError):
    """A release-contract violation with an actionable message."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseValidationError(f"cannot read JSON {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseValidationError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseValidationError(message)


def _asset_path(raw: Any, field: str) -> Path:
    require(isinstance(raw, str) and raw.startswith("./"), f"interface.{field} must start with ./")
    relative = Path(raw[2:])
    require(not relative.is_absolute() and ".." not in relative.parts, f"interface.{field} is unsafe")
    resolved = (ROOT / relative).resolve()
    require(ROOT.resolve() in resolved.parents, f"interface.{field} leaves the plugin root")
    require(resolved.is_file(), f"interface.{field} does not exist: {raw}")
    require(resolved.stat().st_size <= 5 * 1024 * 1024, f"interface.{field} exceeds 5 MiB")
    return resolved


def _number(value: str | None, field: str) -> float:
    require(value is not None and re.fullmatch(r"\d+(?:\.\d+)?", value) is not None, field)
    return float(value)


def validate_svg(path: Path) -> None:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ET.ParseError) as exc:
        raise ReleaseValidationError(f"invalid SVG {path.relative_to(ROOT)}: {exc}") from exc
    require(root.tag.rsplit("}", 1)[-1] == "svg", f"{path.relative_to(ROOT)} root must be svg")
    view_box = root.get("viewBox")
    if view_box:
        parts = view_box.split()
        require(len(parts) == 4, f"{path.relative_to(ROOT)} viewBox must contain four numbers")
        try:
            width, height = float(parts[2]), float(parts[3])
        except ValueError as exc:
            raise ReleaseValidationError(f"{path.relative_to(ROOT)} viewBox is not numeric") from exc
    else:
        width = _number(root.get("width"), f"{path.relative_to(ROOT)} width must be numeric")
        height = _number(root.get("height"), f"{path.relative_to(ROOT)} height must be numeric")
    require(width == height, f"{path.relative_to(ROOT)} must be square")
    require(48 <= width <= 4096, f"{path.relative_to(ROOT)} dimensions must be 48..4096")


def validate_manifest() -> dict[str, Any]:
    manifest = load_json(ROOT / ".codex-plugin" / "plugin.json")
    require(manifest.get("name") == "truedev-workflow", "plugin name must be truedev-workflow")
    require(isinstance(manifest.get("version"), str) and SEMVER.fullmatch(manifest["version"]) is not None, "version must be strict semver")
    require(manifest.get("skills") == "./skills/", "skills must point to ./skills/")
    require("hooks" not in manifest, "default hooks/hooks.json discovery must remain authoritative")
    interface = manifest.get("interface")
    require(isinstance(interface, dict), "interface metadata is required")
    assert isinstance(interface, dict)
    limits = {"displayName": 30, "shortDescription": 30, "developerName": 80, "longDescription": 4000}
    for field, limit in limits.items():
        value = interface.get(field)
        require(isinstance(value, str) and 0 < len(value) <= limit, f"interface.{field} must be 1..{limit} characters")
    for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        value = interface.get(field)
        require(isinstance(value, str) and value.startswith("https://"), f"interface.{field} must be HTTPS")
        require(len(value) <= 1024, f"interface.{field} exceeds final-submission limit")
    for field in ("brandColor",):
        require(isinstance(interface.get(field), str) and HEX_COLOR.fullmatch(interface[field]) is not None, f"interface.{field} must be #RRGGBB")
    prompts = interface.get("defaultPrompt")
    require(isinstance(prompts, list) and 1 <= len(prompts) <= 3, "defaultPrompt must contain one to three prompts")
    assert isinstance(prompts, list)
    require(all(isinstance(item, str) and 0 < len(item) <= 128 and "\n" not in item for item in prompts), "defaultPrompt entries must be single-line and at most 128 characters")
    require("screenshots" not in interface, "skills-only manifests must not declare interface.screenshots")
    for field in IMAGE_FIELDS:
        asset = _asset_path(interface.get(field), field)
        require(asset.suffix.lower() == ".svg", f"interface.{field} must use the reviewed SVG asset")
        validate_svg(asset)
    return manifest


def validate_hooks() -> None:
    hooks = load_json(ROOT / "hooks" / "hooks.json").get("hooks")
    require(isinstance(hooks, dict) and set(hooks) == {"SessionStart", "PreToolUse", "Stop"}, "unexpected hook events")
    assert isinstance(hooks, dict)
    for groups in hooks.values():
        require(isinstance(groups, list), "hook event must contain groups")
        for group in groups:
            for handler in group.get("hooks", []):
                command = handler.get("command")
                windows = handler.get("commandWindows")
                require(isinstance(command, str) and command.startswith('python3 -c "'), "POSIX hooks must use the python3 launcher")
                require(isinstance(windows, str) and windows.startswith('python -c "'), "Windows hooks must use the python launcher")
                for label, launcher in (("POSIX", command), ("Windows", windows)):
                    require(
                        "os.environ.get('PLUGIN_ROOT','')" in launcher,
                        f"{label} hook must read PLUGIN_ROOT inside Python, not through a shell",
                    )
                    require(
                        "os.path.isabs(p) and os.path.isfile(p) else 0" in launcher,
                        f"{label} hook must require an absolute installed path and fail open otherwise",
                    )
                    require(
                        "$env:" not in launcher
                        and "%PLUGIN_ROOT%" not in launcher
                        and "$PLUGIN_ROOT" not in launcher,
                        f"{label} hook must not guess the command shell",
                    )
                require("py -3" not in windows, "Windows hook must not assume a registered py launcher")


def validate_codex_gating() -> None:
    marketplace = load_json(ROOT / ".agents" / "plugins" / "marketplace.json")
    entries = marketplace.get("plugins")
    require(isinstance(entries, list) and len(entries) == 1, "marketplace must contain one plugin")
    policy = entries[0].get("policy", {})
    require(policy.get("products") == ["CODEX"], "marketplace plugin must be gated to CODEX")
    for skill in ("lifecycle", "project-init"):
        yaml_text = (ROOT / "skills" / skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
        require("products:" not in yaml_text, f"{skill} uses unsupported product gating")


def validate_public_materials() -> None:
    for name in PUBLIC_FILES:
        path = ROOT / name
        require(path.is_file() and path.stat().st_size > 100, f"missing public material: {name}")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()
    normalized_security = " ".join(security.split())
    require("not a complete security boundary" in normalized_security, "SECURITY.md must state the hook boundary")
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8").lower()
    normalized_privacy = " ".join(privacy.split())
    require("does not include telemetry" in normalized_privacy, "PRIVACY.md must disclose telemetry behavior")
    support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    require("https://github.com/itpartypattaya/truedev-codex-workflow/issues" in support, "SUPPORT.md must contain the HTTPS support URL")
    for name in ("workflow-overview.png", "gate-guardrail.png"):
        require((ROOT / "docs" / "images" / name).is_file(), f"missing review image: {name}")


def validate_evals() -> None:
    data = load_json(ROOT / "evals" / "plugin" / "evals.json")
    evals = data.get("evals")
    require(isinstance(evals, list), "plugin evals must be a list")
    assert isinstance(evals, list)
    positive = [item for item in evals if item.get("polarity") == "positive"]
    negative = [item for item in evals if item.get("polarity") == "negative"]
    require(len(positive) >= 5, "submission requires at least five positive evals")
    require(len(negative) >= 3, "submission requires at least three negative evals")
    ids = [item.get("id") for item in evals]
    require(len(ids) == len(set(ids)) and all(isinstance(item, str) and item for item in ids), "eval ids must be unique strings")
    for item in evals:
        require(isinstance(item.get("prompt"), str) and item["prompt"], f"eval {item.get('id')} lacks a prompt")
        assertions = item.get("assertions")
        require(isinstance(assertions, list) and len(assertions) >= 3, f"eval {item.get('id')} needs objective assertions")


def validate_evidence_is_current(manifest: dict[str, Any]) -> None:
    """Refuse to present benchmark results that describe a different release.

    The published results carry no provenance until 1.1.8, so a run from an older
    tree looked exactly like a fresh one.
    """
    benchmark = load_json(ROOT / "evals" / "results" / "benchmark.json")
    metadata = benchmark.get("metadata")
    require(isinstance(metadata, dict), "benchmark.json must carry a metadata object")
    assert isinstance(metadata, dict)
    recorded = metadata.get("plugin_version")
    require(
        isinstance(recorded, str) and recorded == manifest["version"],
        f"benchmark evidence was produced for {recorded!r} but this release is "
        f"{manifest['version']!r}; rerun the eval suite from the release SHA",
    )


def validate_no_legacy_host_text() -> None:
    needle = "cl" + "aude"
    company_needle = "anth" + "ropic"
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", ".ruff_cache", "dist", "workspace"} for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".zip"}:
            continue
        try:
            text = path.read_text(encoding="utf-8").lower()
        except UnicodeError:
            continue
        require(needle not in text and company_needle not in text, f"legacy host reference remains in {path.relative_to(ROOT)}")


def validate(root: Path = ROOT, *, require_current_evidence: bool = False) -> dict[str, Any]:
    require(root.resolve() == ROOT.resolve(), "alternate roots are not supported")
    manifest = validate_manifest()
    validate_hooks()
    validate_codex_gating()
    validate_public_materials()
    validate_evals()
    validate_no_legacy_host_text()
    if require_current_evidence:
        validate_evidence_is_current(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-current-evidence",
        action="store_true",
        help="also require the published benchmark to describe this exact release",
    )
    args = parser.parse_args()
    try:
        manifest = validate(require_current_evidence=args.require_current_evidence)
    except ReleaseValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Release validation passed for {manifest['name']} {manifest['version']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
