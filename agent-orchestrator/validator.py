from __future__ import annotations

import re
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

SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    ^\s*\+                              # added diff line only
    \s*
    (?P<key>["']?[A-Z0-9_.-]*
        (?:api[_-]?key|api[_-]?secret|password|passphrase|secret|token)
        [A-Z0-9_.-]*["']?)
    \s*[:=]\s*
    (?P<value>.+?)
    \s*[,;]?\s*$
    """
)

PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "example",
    "fake",
    "mock",
    "none",
    "null",
    "placeholder",
    "redacted",
    "todo",
    "xxx",
    "your-token-here",
    "your_api_key_here",
}

SECRET_KEY_SUFFIXES = (
    "api_key",
    "apikey",
    "api_secret",
    "apisecret",
    "client_secret",
    "clientsecret",
    "password",
    "passphrase",
    "secret",
    "secret_key",
    "secretkey",
    "token",
)


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


def _current_diff_file(line: str, current_file: str) -> str:
    """Track the destination file while walking a git diff."""
    if not line.startswith("+++ b/"):
        return current_file
    return line.removeprefix("+++ b/").strip()


def _clean_secret_value(value: str) -> str:
    """Normalize a candidate value without exposing it in errors."""
    return value.strip().strip(",;").strip().strip('"').strip("'").strip()


def _looks_like_secret_key(key: str) -> bool:
    """Return True for key names that look like credential fields."""
    normalized = key.strip('"\'').lower().replace("-", "_").replace(".", "_")
    return any(normalized == suffix or normalized.endswith(f"_{suffix}") for suffix in SECRET_KEY_SUFFIXES)


def _looks_like_secret_value(value: str) -> bool:
    """Return True for assigned values that look like real secret material."""
    cleaned = _clean_secret_value(value)
    lowered = cleaned.lower()
    if lowered in PLACEHOLDER_VALUES:
        return False
    if lowered.startswith(("os.getenv(", "env(", "${", "$")):
        return False
    if lowered in {"true", "false"}:
        return False
    if lowered.isdigit():
        return False
    if "(" in lowered or ")" in lowered:
        return False
    if "..." in lowered or "<" in lowered or ">" in lowered:
        return False
    return len(cleaned) >= 12 and not any(character.isspace() for character in cleaned)


def _secret_findings(diff_patch: str) -> list[str]:
    """Return redacted descriptions of high-confidence secret additions."""
    findings: list[str] = []
    current_file = ""
    for line_number, line in enumerate(diff_patch.splitlines(), start=1):
        current_file = _current_diff_file(line, current_file)
        if line.startswith("+++") or not line.startswith("+"):
            continue

        match = SECRET_ASSIGNMENT_RE.match(line)
        if match is None:
            continue

        key = match.group("key").strip('"\'')
        value = match.group("value")
        if not _looks_like_secret_key(key):
            continue
        if not _looks_like_secret_value(value):
            continue

        location = current_file or f"diff line {line_number}"
        findings.append(f"{location}: secret-like assignment for `{key}`")
    return findings


def _is_missing_make_target(output: str) -> bool:
    """Detect common Make messages for targets that are not configured."""
    return "No rule for target" in output or "No rule to make target" in output


def _make_check(target: str, project_root: Path, errors: list[str], warnings: list[str]) -> None:
    try:
        result = _run(["make", target], project_root)
    except FileNotFoundError:
        warnings.append(f"Skipped make {target}: make executable not found.")
        return
    output = _combined_output(result)
    if result.returncode == 0:
        return
    if _is_missing_make_target(output):
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

    secret_findings = _secret_findings(diff_patch)
    if secret_findings:
        errors.append(
            "Potential secret value added to diff:\n"
            + "\n".join(f"- {finding}" for finding in secret_findings)
        )
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
