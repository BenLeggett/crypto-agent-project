"""Mock-safe supervisor alert boundary.

Phase 7 alerts are structured local records only. They do not call notifiers,
webhooks, exchanges, models, or wallets. Later reporting/notifier work can plug
in a real sink behind this boundary without changing the deterministic risk
governor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from apps.supervisor.health import HealthStatus
from apps.supervisor.kill_switch import FlattenWorkflowRequest
from apps.supervisor.reconciliation import ReconciliationReport, ReconciliationStatus
from apps.supervisor.service import SupervisorEvaluation
from libs.risk import FreezeState, SupervisorControlAction, SupervisorControlCommand

SUPERVISOR_ALERT_SCHEMA_VERSION = "supervisor_alert.v1"
SUPERVISOR_ALERT_DELIVERY_SCHEMA_VERSION = "supervisor_alert_delivery.v1"


class SupervisorAlertType(str, Enum):
    """Phase 7 supervisor alert categories."""

    RISK_VETO = "risk_veto"
    ENTRIES_FROZEN = "entries_frozen"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    FLATTEN_REQUESTED = "flatten_requested"
    DEGRADED_HEALTH = "degraded_health"
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"


class SupervisorAlertSeverity(str, Enum):
    """Operator severity for mock-safe supervisor alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SupervisorAlert:
    """Versioned supervisor alert record for later notifier integration."""

    alert_id: str
    run_id: str
    alert_type: SupervisorAlertType
    severity: SupervisorAlertSeverity
    created_at_ms: int
    summary: str
    source_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = SUPERVISOR_ALERT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, SUPERVISOR_ALERT_SCHEMA_VERSION, "schema_version")
        _require_text(self.alert_id, "alert_id")
        _require_text(self.run_id, "run_id")
        if not isinstance(self.alert_type, SupervisorAlertType):
            raise TypeError("alert_type must be a SupervisorAlertType")
        if not isinstance(self.severity, SupervisorAlertSeverity):
            raise TypeError("severity must be a SupervisorAlertSeverity")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        _require_text(self.summary, "summary")
        _require_text(self.source_id, "source_id")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "run_id": self.run_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "created_at_ms": self.created_at_ms,
            "summary": self.summary,
            "source_id": self.source_id,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SupervisorAlertDelivery:
    """Non-blocking delivery result for a supervisor alert sink call."""

    alert_id: str
    delivered: bool
    provider: str
    error: str = ""
    schema_version: str = SUPERVISOR_ALERT_DELIVERY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, SUPERVISOR_ALERT_DELIVERY_SCHEMA_VERSION, "schema_version")
        _require_text(self.alert_id, "alert_id")
        _require_text(self.provider, "provider")

    def to_record(self) -> dict[str, str | bool]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "delivered": self.delivered,
            "provider": self.provider,
            "error": self.error,
        }


class SupervisorAlertSink(Protocol):
    """Pluggable sink boundary for later notifier implementations."""

    provider_name: str

    def send(self, alert: SupervisorAlert) -> None:
        """Persist or deliver one alert record."""


class MockSupervisorAlertSink:
    """Local in-memory alert sink used by tests and mock-mode validation."""

    provider_name = "mock_supervisor_alert_sink"

    def __init__(self) -> None:
        self.alerts: list[SupervisorAlert] = []

    def send(self, alert: SupervisorAlert) -> None:
        if not isinstance(alert, SupervisorAlert):
            raise TypeError("alert must be a SupervisorAlert")
        self.alerts.append(alert)

    def records(self) -> list[dict[str, Any]]:
        return [alert.to_record() for alert in self.alerts]


def deliver_supervisor_alert(alert: SupervisorAlert, sink: SupervisorAlertSink) -> SupervisorAlertDelivery:
    """Try one sink delivery and convert failures into structured records."""

    if not isinstance(alert, SupervisorAlert):
        raise TypeError("alert must be a SupervisorAlert")
    provider = getattr(sink, "provider_name", sink.__class__.__name__)
    try:
        sink.send(alert)
    except Exception as exc:  # pragma: no cover - exact sink failures vary later.
        return SupervisorAlertDelivery(
            alert_id=alert.alert_id,
            delivered=False,
            provider=str(provider),
            error=str(exc),
        )
    return SupervisorAlertDelivery(alert_id=alert.alert_id, delivered=True, provider=str(provider))


def deliver_supervisor_alerts(
    alerts: tuple[SupervisorAlert, ...],
    sink: SupervisorAlertSink,
) -> tuple[SupervisorAlertDelivery, ...]:
    """Deliver alert records without allowing sink failures to block control flow."""

    return tuple(deliver_supervisor_alert(alert, sink) for alert in alerts)


def alerts_from_supervisor_evaluation(
    evaluation: SupervisorEvaluation,
    *,
    created_at_ms: int,
) -> tuple[SupervisorAlert, ...]:
    """Build alerts for risk vetoes and degraded/stopped health states."""

    if not isinstance(evaluation, SupervisorEvaluation):
        raise TypeError("evaluation must be a SupervisorEvaluation")
    _require_timestamp(created_at_ms, "created_at_ms")

    alerts: list[SupervisorAlert] = []
    if not evaluation.risk_decision.allowed:
        alerts.append(
            SupervisorAlert(
                alert_id=_alert_id(SupervisorAlertType.RISK_VETO, evaluation.run_id, evaluation.decision_id, created_at_ms),
                run_id=evaluation.run_id,
                alert_type=SupervisorAlertType.RISK_VETO,
                severity=SupervisorAlertSeverity.WARNING,
                created_at_ms=created_at_ms,
                summary=f"risk veto: {evaluation.risk_decision.primary_reason}",
                source_id=evaluation.decision_id,
                payload=evaluation.risk_decision.to_record(),
                metadata={"proposal_id": evaluation.proposal_id},
            )
        )
    if evaluation.health.status is not HealthStatus.OK:
        alerts.append(
            SupervisorAlert(
                alert_id=_alert_id(
                    SupervisorAlertType.DEGRADED_HEALTH,
                    evaluation.run_id,
                    evaluation.decision_id,
                    created_at_ms,
                ),
                run_id=evaluation.run_id,
                alert_type=SupervisorAlertType.DEGRADED_HEALTH,
                severity=_health_severity(evaluation.health.status),
                created_at_ms=created_at_ms,
                summary=f"supervisor health is {evaluation.health.status.value}",
                source_id=evaluation.decision_id,
                payload=evaluation.health.to_record(),
                metadata={"proposal_id": evaluation.proposal_id},
            )
        )
    return tuple(alerts)


def alert_from_control_command(
    command: SupervisorControlCommand,
    state: FreezeState,
) -> SupervisorAlert | None:
    """Build a freeze or kill-switch alert from a deterministic control command."""

    if not isinstance(command, SupervisorControlCommand):
        raise TypeError("command must be a SupervisorControlCommand")
    if not isinstance(state, FreezeState):
        raise TypeError("state must be a FreezeState")

    if command.action is SupervisorControlAction.FREEZE_ENTRIES:
        return SupervisorAlert(
            alert_id=_alert_id(SupervisorAlertType.ENTRIES_FROZEN, command.run_id, command.command_id, command.created_at_ms),
            run_id=command.run_id,
            alert_type=SupervisorAlertType.ENTRIES_FROZEN,
            severity=SupervisorAlertSeverity.WARNING,
            created_at_ms=command.created_at_ms,
            summary=f"entries frozen: {command.reason}",
            source_id=command.command_id,
            payload={"command": command.to_record(), "state": state.to_record()},
        )
    if command.action is SupervisorControlAction.ACTIVATE_KILL_SWITCH:
        return SupervisorAlert(
            alert_id=_alert_id(
                SupervisorAlertType.KILL_SWITCH_ACTIVATED,
                command.run_id,
                command.command_id,
                command.created_at_ms,
            ),
            run_id=command.run_id,
            alert_type=SupervisorAlertType.KILL_SWITCH_ACTIVATED,
            severity=SupervisorAlertSeverity.CRITICAL,
            created_at_ms=command.created_at_ms,
            summary=f"kill switch activated: {command.reason}",
            source_id=command.command_id,
            payload={"command": command.to_record(), "state": state.to_record()},
        )
    return None


def alert_from_flatten_request(request: FlattenWorkflowRequest) -> SupervisorAlert:
    """Build an alert for a non-executing flatten workflow request."""

    if not isinstance(request, FlattenWorkflowRequest):
        raise TypeError("request must be a FlattenWorkflowRequest")
    return SupervisorAlert(
        alert_id=_alert_id(SupervisorAlertType.FLATTEN_REQUESTED, request.run_id, request.request_id, request.created_at_ms),
        run_id=request.run_id,
        alert_type=SupervisorAlertType.FLATTEN_REQUESTED,
        severity=SupervisorAlertSeverity.CRITICAL,
        created_at_ms=request.created_at_ms,
        summary=f"flatten requested: {request.reason}",
        source_id=request.request_id,
        payload=request.to_record(),
        metadata={"execution_enabled": str(request.execution_enabled).lower()},
    )


def alert_from_reconciliation_report(report: ReconciliationReport) -> SupervisorAlert | None:
    """Build one alert when reconciliation finds account-state mismatches."""

    if not isinstance(report, ReconciliationReport):
        raise TypeError("report must be a ReconciliationReport")
    if report.status is ReconciliationStatus.MATCHED:
        return None

    critical_count = sum(1 for mismatch in report.mismatches if mismatch.severity.value == "critical")
    severity = SupervisorAlertSeverity.CRITICAL if critical_count else SupervisorAlertSeverity.WARNING
    return SupervisorAlert(
        alert_id=_alert_id(
            SupervisorAlertType.RECONCILIATION_MISMATCH,
            report.run_id,
            report.report_id,
            report.created_at_ms,
        ),
        run_id=report.run_id,
        alert_type=SupervisorAlertType.RECONCILIATION_MISMATCH,
        severity=severity,
        created_at_ms=report.created_at_ms,
        summary=f"reconciliation mismatch: {len(report.mismatches)} issue(s)",
        source_id=report.report_id,
        payload=report.to_record(),
        metadata={"critical_mismatches": str(critical_count)},
    )


def _health_severity(status: HealthStatus) -> SupervisorAlertSeverity:
    if status is HealthStatus.STOPPED:
        return SupervisorAlertSeverity.CRITICAL
    return SupervisorAlertSeverity.WARNING


def _alert_id(alert_type: SupervisorAlertType, run_id: str, source_id: str, created_at_ms: int) -> str:
    return f"{alert_type.value}-{run_id}-{source_id}-{created_at_ms}"


def _require_schema(value: str, expected: str, field_name: str) -> None:
    if value != expected:
        raise ValueError(f"{field_name} must be {expected!r}")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_timestamp(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer millisecond timestamp")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _string_mapping(value: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    normalized = dict(value)
    for key, item in normalized.items():
        _require_text(key, f"{field_name} key")
        if not isinstance(item, str):
            raise TypeError(f"{field_name} values must be strings")
    return MappingProxyType(normalized)


__all__ = [
    "SUPERVISOR_ALERT_DELIVERY_SCHEMA_VERSION",
    "SUPERVISOR_ALERT_SCHEMA_VERSION",
    "MockSupervisorAlertSink",
    "SupervisorAlert",
    "SupervisorAlertDelivery",
    "SupervisorAlertSeverity",
    "SupervisorAlertSink",
    "SupervisorAlertType",
    "alert_from_control_command",
    "alert_from_flatten_request",
    "alert_from_reconciliation_report",
    "alerts_from_supervisor_evaluation",
    "deliver_supervisor_alert",
    "deliver_supervisor_alerts",
]
