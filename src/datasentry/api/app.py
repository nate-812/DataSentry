"""DataSentry M4 FastAPI 应用。"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from datasentry.api.routes import alertmanager, chat, evidence, incidents, operations, overview
from datasentry.config import Settings
from datasentry.errors import DataSentryError, NotFoundError


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    app = FastAPI(title="DataSentry API", version="0.1.0")
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.api_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.add_exception_handler(DataSentryError, _datasentry_error_handler)
    app.include_router(chat.router, prefix="/api")
    app.include_router(alertmanager.router, prefix="/api")
    app.include_router(overview.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.include_router(incidents.router, prefix="/api")
    app.include_router(operations.router, prefix="/api")
    return app


async def _datasentry_error_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    del request
    assert isinstance(error, DataSentryError)
    status_code = 404 if isinstance(error, NotFoundError) else 400
    return JSONResponse(status_code=status_code, content=error.to_dict())
