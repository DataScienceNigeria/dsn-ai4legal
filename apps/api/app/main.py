"""Application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import PlatformError

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Legal Operations Platform",
    version="1.0.0",
    description=(
        "DSN and EqualyzAI legal operations. AI may recommend, an authorised human "
        "must confirm. The API is the only write path."
    ),
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.dsnlai_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PlatformError)
def platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


@app.get("/health", tags=["platform"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.dsnlai_env}


def register_routers() -> None:
    from app.api.v1 import (
        admin,
        ai,
        approvals,
        assessments,
        auth,
        contracts,
        counterparties,
        documents,
        library,
        matters,
        obligations,
        reports,
        requests,
        scim,
        webhooks,
    )

    prefix = "/api/v1"
    for module in (
        auth,
        requests,
        matters,
        library,
        documents,
        approvals,
        contracts,
        obligations,
        counterparties,
        ai,
        assessments,
        reports,
        admin,
        scim,
        webhooks,
    ):
        app.include_router(module.router, prefix=prefix)


register_routers()
