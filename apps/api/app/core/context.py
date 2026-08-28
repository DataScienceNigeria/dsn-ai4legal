"""What the request knew, available to code that was never handed the request.

``audit.record`` is called from a hundred and twelve places, most of them
services that have no business taking a ``Request`` parameter just so a column
can be filled. Eleven of those call sites passed an IP address and the rest
did not, so the trail could say what was done and by whom but only rarely from
where, which is the question asked first when an account is suspected.

A context variable set once per request answers it everywhere without a single
service learning about HTTP. It is per task, so concurrent requests do not see
each other's, and it is reset when the request ends.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class RequestContext:
    """Deliberately mutable.

    FastAPI runs a synchronous dependency in a worker thread, and a context
    variable set inside that thread does not propagate back to the request that
    started it. The middleware's value is copied in, so reads work and writes
    are lost, which is why the session identifier the token dependency learns
    has to be written into this object rather than into a replacement for it.
    """

    ip_address: str | None = None
    session_id: str | None = None
    user_agent: str | None = None


_current: ContextVar[RequestContext] = ContextVar("request_context", default=RequestContext())


def set_context(context: RequestContext):
    return _current.set(context)


def reset_context(token) -> None:
    _current.reset(token)


def current() -> RequestContext:
    return _current.get()


def attach_session(session_id: str | None) -> None:
    """Add the session to the context once the token has been read.

    The middleware runs before anything has decoded a token, so the session
    identifier arrives here rather than there. It is written into the object
    the middleware put in the variable, not into a new one, because this runs
    in a worker thread and a rebound variable would not survive the return.
    """
    if session_id:
        _current.get().session_id = session_id
