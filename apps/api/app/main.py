"""Application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core import context
from app.core.config import DEVELOPMENT_SECRET_KEY, settings
from app.core.deps import client_ip
from app.core.errors import PlatformError

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse to start on anything that would be a defect in production.

    A platform that comes up with its document store unreachable accepts
    uploads it cannot keep, and one running on the signing key that ships with
    the repository will accept a token anybody could have minted. Both stop it
    here rather than at the first signed agreement.
    """
    from app.services.storage import store

    log = logging.getLogger(__name__)

    if not settings.is_development and settings.dsnlai_secret_key == DEVELOPMENT_SECRET_KEY:
        raise RuntimeError(
            "DSNLAI_SECRET_KEY is still the one in the repository, so anybody "
            f"holding it could sign a token for any role. Set it before running a "
            f"{settings.dsnlai_env} deployment."
        )

    store.verify()
    log.info("Documents are kept in the %s store.", store.backend.name)

    if not settings.is_development and not settings.allowed_origins:
        log.warning(
            "DSNLAI_ALLOWED_ORIGINS is empty, so no browser origin may call this "
            "API. Set it to the address the interface is served from, unless one "
            "address fronts both."
        )
    yield


app = FastAPI(
    lifespan=lifespan,
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
async def carry_the_request_context(request: Request, call_next):
    """Hold where a request came from, so the audit does not have to be asked.

    Every service that appends to the trail would otherwise need a ``Request``
    parameter it has no other use for, and eleven of a hundred and twelve call
    sites had one. Set here, read in ``audit.record``, reset on the way out.
    """
    token = context.set_context(
        context.RequestContext(
            ip_address=client_ip(request),
            user_agent=(request.headers.get("user-agent") or None),
        )
    )
    try:
        return await call_next(request)
    finally:
        context.reset_context(token)


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
    allow_origins=["*"] if settings.is_development else settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PlatformError)
def platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload())


def _health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.dsnlai_env,
        "storage": settings.dsnlai_storage_backend,
    }


@app.get("/health", tags=["platform"])
def health() -> dict[str, str]:
    """For the container's own probe, which reaches the port directly."""
    return _health()


@app.get("/api/v1/health", tags=["platform"])
def health_through_the_proxy() -> dict[str, str]:
    """The same answer, where a proxy can reach it.

    A reverse proxy routes ``/api/`` here and everything else to the interface,
    so a checker asking the public address for ``/health`` gets the interface's
    404 and reports the platform down while it is serving perfectly well.
    """
    return _health()


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
