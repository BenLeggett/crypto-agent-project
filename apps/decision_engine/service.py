"""Decision engine audit artifact helpers."""

from __future__ import annotations

from dataclasses import dataclass

from libs.decisioning.deterministic_rules import DeterministicDecisionResult
from libs.decisioning.schemas import NoTradeDecision, TradeProposal
from libs.event_packets import EventPacket, build_proposal_packet
from libs.journal import JournalRecord, JournalRecordType


@dataclass(frozen=True)
class DecisionAuditArtifacts:
    """Local audit artifacts emitted by a decision-engine result."""

    journal_records: tuple[JournalRecord, ...]
    event_packets: tuple[EventPacket, ...]

    def to_record(self) -> dict:
        return {
            "journal_records": [record.to_record() for record in self.journal_records],
            "event_packets": [packet.to_record() for packet in self.event_packets],
        }


def build_decision_audit_artifacts(
    result: DeterministicDecisionResult,
    *,
    source: str = "decision_engine",
) -> DecisionAuditArtifacts:
    """Build journal records and packets for one deterministic decision result."""

    if not isinstance(result, DeterministicDecisionResult):
        raise TypeError("result must be a DeterministicDecisionResult")

    decision_input = result.decision_input
    output = result.output
    output_record = output.to_record()
    input_record = decision_input.to_record()

    journal_records = (
        JournalRecord(
            record_id=f"proposal-input-{decision_input.run_id}-{decision_input.decision_id}",
            run_id=decision_input.run_id,
            created_at_ms=decision_input.created_at_ms,
            record_type=JournalRecordType.PROPOSAL_INPUT,
            source=source,
            config_hash=decision_input.config_hash,
            payload=input_record,
            metadata={"decision_id": decision_input.decision_id},
        ),
        JournalRecord(
            record_id=f"proposal-output-{decision_input.run_id}-{decision_input.decision_id}",
            run_id=decision_input.run_id,
            created_at_ms=_output_created_at_ms(output),
            record_type=JournalRecordType.PROPOSAL_OUTPUT,
            source=source,
            config_hash=decision_input.config_hash,
            payload=output_record,
            metadata={
                "decision_id": decision_input.decision_id,
                "output_kind": "proposal" if isinstance(output, TradeProposal) else "no_trade",
            },
        ),
    )

    event_packet = build_proposal_packet(
        run_id=decision_input.run_id,
        proposal_id=_output_entity_id(output),
        occurred_at_ms=_output_created_at_ms(output),
        proposal=output_record,
        rejected=isinstance(output, NoTradeDecision),
        reason="" if isinstance(output, TradeProposal) else output.reason.value,
        source=source,
    )
    return DecisionAuditArtifacts(journal_records=journal_records, event_packets=(event_packet,))


def _output_created_at_ms(output: TradeProposal | NoTradeDecision) -> int:
    return output.created_at_ms


def _output_entity_id(output: TradeProposal | NoTradeDecision) -> str:
    if isinstance(output, TradeProposal):
        return output.proposal_id
    return output.decision_id


__all__ = [
    "DecisionAuditArtifacts",
    "build_decision_audit_artifacts",
]
