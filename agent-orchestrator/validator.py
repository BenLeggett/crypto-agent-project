from __future__ import annotations

import subprocess
from pathlib import Path

FORBIDDEN_PATHS = [
    "configs/live/",
    "freqtrade/user_data/config.live.json",
    ".env",
]

SECRETS_PATTERNS = [
    "api_key",
    "api_secret",
    "password",
    "token",
    "passphrase",
]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with the validator's standard safety settings."""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}{result.stderr}"


def _make_check(target: str, project_root: Path, errors: list[str], warnings: list[str]) -> None:
    try:
        result = _run(["make", target], project_root)
    except FileNotFoundError:
        warnings.append(f"Skipped make {target}: make executable not found.")
        return
    output = _combined_output(result)
    if result.returncode == 0:
        return
    if "No rule for target" in output:
        warnings.append(f"Skipped make {target}: target does not exist.")
        return
    errors.append(f"make {target} failed:\n{output.strip()}")


def validate(project_root: str) -> dict[str, object]:
    """Run validation checks for the project workspace."""
    root = Path(project_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    diff_summary = ""

    try:
        diff_stat = _run(["git", "diff", "--stat", "HEAD"], root)
        diff_summary = _combined_output(diff_stat).strip()
    except subprocess.TimeoutExpired:
        errors.append("git diff --stat HEAD timed out.")
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
            "diff_summary": diff_summary,
        }

    for forbidden_path in FORBIDDEN_PATHS:
        if forbidden_path in diff_summary:
            errors.append(f"Forbidden path modified: {forbidden_path}")
            return {
                "passed": False,
                "errors": errors,
                "warnings": warnings,
                "diff_summary": diff_summary,
            }

    try:
        diff_patch_result = _run(["git", "diff", "HEAD"], root)
        diff_patch = _combined_output(diff_patch_result)
    except subprocess.TimeoutExpired:
        errors.append("git diff HEAD timed out.")
        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
            "diff_summary": diff_summary,
        }

    lowered_patch = diff_patch.lower()
    for pattern in SECRETS_PATTERNS:
        if pattern.lower() in lowered_patch:
            errors.append(f"Potential secret pattern found in diff: {pattern}")
            return {
                "passed": False,
                "errors": errors,
                "warnings": warnings,
                "diff_summary": diff_summary,
            }

    for target in ("lint", "typecheck", "test"):
        try:
            _make_check(target, root, errors, warnings)
        except subprocess.TimeoutExpired:
            errors.append(f"make {target} timed out.")

    if "Dockerfile" in diff_summary or ".github/workflows" in diff_summary:
        warnings.append("Diff includes Dockerfile or GitHub workflow changes.")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "diff_summary": diff_summary,
    }
