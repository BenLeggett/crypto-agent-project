from __future__ import annotations


def wait_for_approval(reference: str, db_path: str | None = None, timeout_seconds: int | None = None) -> bool:
    """Return a placeholder approval result."""
    _ = (reference, db_path, timeout_seconds)
    return False


def record_decision(
    reference: str,
    gate_type: str,
    decision: str,
    notes: str = "",
    db_path: str | None = None,
) -> None:
    """Placeholder decision recorder."""
    _ = (reference, gate_type, decision, notes, db_path)
