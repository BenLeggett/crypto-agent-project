from __future__ import annotations

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


def validate(project_root: str | None = None) -> dict[str, object]:
    """Return a placeholder validation result."""
    _ = project_root
    return {
        "passed": False,
        "errors": [],
        "warnings": [],
        "diff_summary": "",
    }
