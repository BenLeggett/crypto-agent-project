from __future__ import annotations

import json
from decimal import Decimal

import pytest

from apps.supervisor.reconciliation import (
    AccountSnapshot,
    BalanceSnapshot,
    PositionSnapshot,
    ReconciliationStatus,
    account_snapshot_from_record,
    reconcile_account_snapshots,
)
from libs.strategy.interfaces import TradeSide
from scripts import reconcile_positions


def test_reconciliation_matches_identical_snapshots() -> None:
    report = reconcile_account_snapshots(
        report_id="recon-1",
        created_at_ms=1_700_000_000_001,
        internal=_snapshot("internal-1", "internal"),
        external=_snapshot("external-1", "external"),
    )

    assert report.status is ReconciliationStatus.MATCHED
    assert report.mismatches == ()
    record = report.to_record()
    assert record["schema_version"] == "reconciliation_report.v1"
    assert record["status"] == "matched"


def test_reconciliation_classifies_position_and_balance_mismatches() -> None:
    internal = _snapshot(
        "internal-1",
        "internal",
        balances=(BalanceSnapshot("USDT", Decimal("1000"), Decimal("900")),),
        positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("500")),),
    )
    external = _snapshot(
        "external-1",
        "external",
        balances=(BalanceSnapshot("USDT", Decimal("850"), Decimal("850")),),
        positions=(
            PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("300")),
            PositionSnapshot("ETH/USDT", TradeSide.LONG, Decimal("100")),
        ),
    )

    report = reconcile_account_snapshots(
        report_id="recon-1",
        created_at_ms=1_700_000_000_001,
        internal=internal,
        external=external,
    )

    assert report.status is ReconciliationStatus.MISMATCHED
    assert [mismatch.code for mismatch in report.mismatches] == [
        "balance_total_mismatch",
        "position_notional_mismatch",
        "unexpected_external_position",
    ]
    assert report.mismatches[1].severity.value == "critical"


def test_reconciliation_respects_tolerances() -> None:
    internal = _snapshot(
        "internal-1",
        "internal",
        balances=(BalanceSnapshot("USDT", Decimal("1000"), Decimal("900")),),
        positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("500")),),
    )
    external = _snapshot(
        "external-1",
        "external",
        balances=(BalanceSnapshot("USDT", Decimal("999.99"), Decimal("900")),),
        positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("499.99")),),
    )

    report = reconcile_account_snapshots(
        report_id="recon-1",
        created_at_ms=1_700_000_000_001,
        internal=internal,
        external=external,
        balance_tolerance=Decimal("0.02"),
        position_notional_tolerance=Decimal("0.02"),
    )

    assert report.status is ReconciliationStatus.MATCHED


def test_account_snapshot_parser_validates_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicate balance asset"):
        account_snapshot_from_record(
            {
                "snapshot_id": "internal-1",
                "source": "internal",
                "run_id": "run-1",
                "created_at_ms": 1_700_000_000_000,
                "balances": [
                    {"asset": "USDT", "total": "100", "available": "100"},
                    {"asset": "USDT", "total": "100", "available": "100"},
                ],
                "positions": [],
            }
        )


def test_reconcile_positions_script_emits_report_json(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    internal_path = tmp_path / "internal.json"
    external_path = tmp_path / "external.json"
    internal_path.write_text(json.dumps(_snapshot("internal-1", "internal").to_record()), encoding="utf-8")
    external_path.write_text(
        json.dumps(
            _snapshot(
                "external-1",
                "external",
                positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("700")),),
            ).to_record()
        ),
        encoding="utf-8",
    )

    result = reconcile_positions.main(
        [
            "--report-id",
            "recon-1",
            "--created-at-ms",
            "1700000000001",
            "--internal-snapshot",
            str(internal_path),
            "--external-snapshot",
            str(external_path),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_id"] == "recon-1"
    assert payload["status"] == "mismatched"
    assert payload["mismatches"][0]["code"] == "position_notional_mismatch"


def test_reconcile_positions_script_defaults_to_empty_mock_snapshots(capsys: pytest.CaptureFixture[str]) -> None:
    result = reconcile_positions.main(
        [
            "--run-id",
            "run-1",
            "--report-id",
            "recon-empty",
            "--created-at-ms",
            "1700000000001",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "matched"
    assert payload["metadata"]["internal_source"] == "internal_mock"
    assert payload["metadata"]["external_source"] == "external_mock"


def _snapshot(
    snapshot_id: str,
    source: str,
    *,
    balances: tuple[BalanceSnapshot, ...] = (BalanceSnapshot("USDT", Decimal("1000"), Decimal("900")),),
    positions: tuple[PositionSnapshot, ...] = (PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("500")),),
) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id=snapshot_id,
        source=source,
        run_id="run-1",
        created_at_ms=1_700_000_000_000,
        balances=balances,
        positions=positions,
    )
