from __future__ import annotations

import importlib
from pathlib import Path


MODULES = [
    "apps.collector.main",
    "apps.collector.jobs",
    "apps.research.main",
    "apps.research.walkforward",
    "apps.research.reports",
    "apps.decision_engine.main",
    "apps.decision_engine.service",
    "apps.decision_engine.proposal_builder",
    "apps.decision_engine.validators",
    "apps.supervisor.main",
    "apps.supervisor.service",
    "apps.supervisor.policy",
    "apps.supervisor.reconciliation",
    "apps.supervisor.kill_switch",
    "apps.supervisor.health",
    "apps.ai_router.main",
    "apps.ai_router.router",
    "apps.ai_router.budgets",
    "apps.ai_router.prompts",
    "apps.ai_router.schemas",
    "apps.ai_router.providers",
    "apps.ai_router.usage_log",
    "apps.report_jobs.daily_brief",
    "apps.report_jobs.weekly_review",
    "apps.report_jobs.nightly_rollups",
    "apps.report_jobs.operator_update",
    "apps.briefing_cli.main",
    "libs.common.time",
    "libs.common.ids",
    "libs.common.hashing",
    "libs.config.models",
    "libs.config.loader",
    "libs.config.validators",
    "libs.market_data.ccxt_client",
    "libs.market_data.collectors",
    "libs.market_data.normalization",
    "libs.market_data.quality_checks",
    "libs.market_data.storage",
    "libs.strategy.interfaces",
    "libs.strategy.universe",
    "libs.strategy.regime",
    "libs.strategy.breakout",
    "libs.strategy.sizing",
    "libs.strategy.stops",
    "libs.strategy.signal_snapshot",
    "libs.decisioning.schemas",
    "libs.decisioning.deterministic_rules",
    "libs.decisioning.model_signals",
    "libs.decisioning.scoring",
    "libs.risk.account_policy",
    "libs.risk.position_limits",
    "libs.risk.drawdown_rules",
    "libs.risk.freeze_state",
    "libs.journal.writer",
    "libs.journal.schema",
    "libs.journal.queries",
    "libs.journal.rollups",
    "libs.event_packets.schemas",
    "libs.event_packets.builders",
    "libs.event_packets.serializers",
    "libs.retrieval.sqlite_fts",
    "libs.retrieval.filters",
    "libs.retrieval.corpus_builder",
    "libs.notifier.schemas",
    "libs.notifier.mock_notifier",
    "libs.notifier.chat_webhook",
    "libs.ai_costs.quotas",
    "libs.ai_costs.estimators",
    "libs.ai_costs.counters",
]


ENTRYPOINTS = [
    "apps.collector.main",
    "apps.research.main",
    "apps.decision_engine.main",
    "apps.supervisor.main",
    "apps.ai_router.main",
    "apps.briefing_cli.main",
]


def test_planned_modules_import_without_side_effects() -> None:
    for module_name in MODULES:
        importlib.import_module(module_name)


def test_placeholder_entrypoints_return_success() -> None:
    for module_name in ENTRYPOINTS:
        module = importlib.import_module(module_name)
        assert module.main() == 0


def test_canonical_docs_exist() -> None:
    docs_dir = Path("docs")
    for filename in [
        "ARCHITECTURE.md",
        "IMPLEMENTATION_PLAN.md",
        "TASK_QUEUE.md",
        "MANUAL_WIRING_CHECKLIST.md",
    ]:
        assert (docs_dir / filename).is_file()
