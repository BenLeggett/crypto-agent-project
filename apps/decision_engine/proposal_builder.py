"""Trade proposal builders for the decision engine."""

from __future__ import annotations

from libs.decisioning.deterministic_rules import (
    DeterministicDecisionResult,
    DeterministicProposalConfig,
    build_deterministic_decision,
)
from libs.strategy.interfaces import StrategySnapshot


class DeterministicProposalBuilder:
    """Build canonical decision outputs from deterministic strategy snapshots."""

    def __init__(self, config: DeterministicProposalConfig) -> None:
        self._config = config

    def build(self, snapshot: StrategySnapshot) -> DeterministicDecisionResult:
        return build_deterministic_decision(snapshot, config=self._config)


__all__ = ["DeterministicProposalBuilder"]
