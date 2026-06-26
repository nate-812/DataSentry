from datetime import UTC, datetime
from pathlib import Path

from datasentry.diagnosis import (
    ComponentDownRule,
    ConfigurationMismatchRule,
    DiagnosisService,
    FlinkBackpressureRule,
    KlineStalledAtFlinkRule,
)
from datasentry.domain import Observation
from datasentry.knowledge import KnowledgeIndex, KnowledgeRouter, build_streamlake_lineage
from datasentry.storage import SQLiteRepository
from datasentry.tools.collector import CollectionResult
from datasentry.tools.service import LiveInspectionService

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class FixturePlanner:
    def plan(self, prepared: object) -> tuple:
        del prepared
        return ()


class FixtureCollector:
    def collect(self, inspection_id: str, calls: tuple) -> CollectionResult:
        del calls
        return CollectionResult(
            outcomes=[],
            observations=[
                Observation(
                    inspection_id=inspection_id,
                    component="kafka",
                    metric_or_fact="topic_advancing",
                    value=True,
                    source="fixture",
                    target="binance.trade.raw",
                    observed_at=NOW,
                ),
                Observation(
                    inspection_id=inspection_id,
                    component="flink",
                    metric_or_fact="kline_job_state",
                    value={"state": "MISSING"},
                    source="fixture",
                    target="kline",
                    observed_at=NOW,
                ),
                Observation(
                    inspection_id=inspection_id,
                    component="doris",
                    metric_or_fact="kline_freshness_seconds",
                    value=900,
                    source="fixture",
                    target="kline_1min",
                    observed_at=NOW,
                ),
            ],
            unknowns=[],
        )


def test_live_service_collects_and_completes_diagnosis(tmp_path: Path) -> None:
    knowledge = KnowledgeIndex.load(REPOSITORY_ROOT / "knowledge")
    with SQLiteRepository(tmp_path / "datasentry.db") as repository:
        diagnosis = DiagnosisService(
            repository=repository,
            knowledge_index=knowledge,
            router=KnowledgeRouter(knowledge),
            lineage_graph=build_streamlake_lineage(),
            rules=(
                KlineStalledAtFlinkRule(),
                ComponentDownRule(),
                FlinkBackpressureRule(),
                ConfigurationMismatchRule(),
            ),
            clock=lambda: NOW,
        )
        result = LiveInspectionService(
            repository=repository,
            diagnosis=diagnosis,
            planner=FixturePlanner(),
            collector=FixtureCollector(),
        ).run("为什么K线不更新")

    assert result.diagnosis.aggregate.findings[0].claim == "K线链路停在 Flink 计算层"
    assert result.tool_invocations == []
