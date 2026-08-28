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
        "DSN and EqualyzAI legal staff. AI may recommend, an authorised human "
        "must confirm. The API is the only write path."
    ),
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

@app.middleware("http")
async def unhandled_error_to_problem(request: Request, call_next):
    """Turn an unhandled failure into a response the browser can read.

    Starlette's own handler for an unhandled exception sits outside the CORS
    layer, so a 500 reaches the browser with no CORS header and is reported as
    a CORS failure. The real error then never appears in the console. This
    catches first, inside CORS, so the status and reason survive the trip.
    """
    try:
        return await call_next(request)
    except Exception:
        logging.getLogger(__name__).exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Something failed on the server. The error has been logged.",
            },
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
        consultants,
        contracts,
        counterparties,
        documents,
        library,
        lifecycle,
        matters,
        obligations,
        reports,
        requests,
        scim,
        webhooks,
        workspace,
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
        lifecycle,
        consultants,
        counterparties,
        ai,
        assessments,
        reports,
        admin,
        workspace,
        scim,
        webhooks,
    ):
        app.include_router(module.router, prefix=prefix)


register_routers()
