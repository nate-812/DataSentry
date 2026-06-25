from datetime import datetime

import pytest
from pydantic import ValidationError

from datasentry.domain import Evidence, EvidenceStatus, Finding, Severity


def test_finding_requires_evidence(
    inspection_id: str,
    observed_at: datetime,
) -> None:
    with pytest.raises(ValidationError):
        Finding(
            inspection_id=inspection_id,
            severity=Severity.INFO,
            status=EvidenceStatus.CONFIRMED,
            claim="Simulation completed",
            impact="No production impact",
            recommendation="Proceed to M1",
            unknowns=[],
            evidence=[],
            created_at=observed_at,
        )


def test_finding_accepts_historical_evidence(
    inspection_id: str,
    observed_at: datetime,
) -> None:
    evidence = Evidence(
        claim="The component existed in the historical baseline",
        status=EvidenceStatus.HISTORICAL,
        source="knowledge/07-runtime-baseline-2026-06-25.md",
        observed_at=observed_at,
        summary="Historical snapshot only",
    )

    finding = Finding(
        inspection_id=inspection_id,
        severity=Severity.INFO,
        status=EvidenceStatus.HISTORICAL,
        claim="Historical component state is available",
        evidence=[evidence],
        impact="This does not confirm current runtime state",
        recommendation="Query a live read-only tool before drawing a current conclusion",
        created_at=observed_at,
    )

    assert finding.evidence == [evidence]
