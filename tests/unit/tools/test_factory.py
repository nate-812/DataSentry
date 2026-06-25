from pathlib import Path

from datasentry.storage import SQLiteRepository
from datasentry.tools import LiveInspectionService, TargetCatalog
from datasentry.tools.factory import build_live_inspection_service

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_factory_builds_live_service_without_opening_connections(tmp_path: Path) -> None:
    targets_path = tmp_path / "targets.toml"
    targets_path.write_text("[hosts]\n", encoding="utf-8")
    targets = TargetCatalog.load(targets_path)

    with SQLiteRepository(tmp_path / "datasentry.db") as repository:
        service = build_live_inspection_service(
            repository=repository,
            targets=targets,
            knowledge_root=REPOSITORY_ROOT / "knowledge",
        )

    assert isinstance(service, LiveInspectionService)
