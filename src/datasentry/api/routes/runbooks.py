"""Runbook 目录 API。"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder

from datasentry.api.dependencies import get_runbook_catalog
from datasentry.runbooks import BuiltInRunbookCatalog

router = APIRouter(tags=["runbooks"])


@router.get("/runbooks")
def list_runbooks(
    catalog: Annotated[BuiltInRunbookCatalog, Depends(get_runbook_catalog)],
) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], jsonable_encoder(catalog.list_runbooks()))


@router.get("/runbooks/{runbook_name}")
def get_runbook(
    runbook_name: str,
    catalog: Annotated[BuiltInRunbookCatalog, Depends(get_runbook_catalog)],
) -> dict[str, object]:
    return cast(dict[str, object], jsonable_encoder(catalog.get(runbook_name)))
