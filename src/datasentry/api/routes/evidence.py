"""巡检证据查看路由。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_repository
from datasentry.storage import SQLiteRepository

router = APIRouter(tags=["evidence"])


@router.get("/evidence/inspections/{inspection_id}")
def inspection_evidence(
    inspection_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> dict[str, object]:
    aggregate = repository.get_inspection(inspection_id)
    return {
        "inspection": cast(dict[str, object], jsonable_encoder(aggregate.inspection)),
        "observations": cast(list[dict[str, object]], jsonable_encoder(aggregate.observations)),
        "findings": cast(list[dict[str, object]], jsonable_encoder(aggregate.findings)),
        "tool_invocations": cast(
            list[dict[str, object]],
            jsonable_encoder(repository.list_tool_invocations(inspection_id)),
        ),
    }
