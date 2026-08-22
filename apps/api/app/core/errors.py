"""A single error contract.

A request that would cross entities without explicit permission returns not
found rather than forbidden, so record existence is not disclosed
(PRD section 12.1).
"""

from fastapi import HTTPException, status


class PlatformError(HTTPException):
    """Base class carrying a stable machine-readable code."""

    code = "platform_error"

    def __init__(self, detail: str, status_code: int, field_errors: dict | None = None):
        super().__init__(status_code=status_code, detail=detail)
        self.field_errors = field_errors or {}

    def payload(self) -> dict:
        body: dict = {"code": self.code, "message": self.detail}
        if self.field_errors:
            body["field_errors"] = self.field_errors
        return body


class NotFound(PlatformError):
    code = "not_found"

    def __init__(self, detail: str = "Not found."):
        super().__init__(detail, status.HTTP_404_NOT_FOUND)


class Forbidden(PlatformError):
    """Used only where the caller already knows the record exists."""

    code = "forbidden"

    def __init__(self, detail: str = "You are not permitted to do that."):
        super().__init__(detail, status.HTTP_403_FORBIDDEN)


class Unauthenticated(PlatformError):
    code = "unauthenticated"

    def __init__(self, detail: str = "Authentication is required."):
        super().__init__(detail, status.HTTP_401_UNAUTHORIZED)


class StepUpRequired(PlatformError):
    """Re-authentication is required for signature, clause publication,
    restricted-matter access and administrative changes (LOP-M15-US-02)."""

    code = "step_up_required"

    def __init__(self, action: str):
        super().__init__(
            f"Re-authentication is required before you can {action}.",
            status.HTTP_401_UNAUTHORIZED,
        )


class ValidationFailed(PlatformError):
    """Mandatory-field validation returns field-level errors, never a generic
    failure (PRD LOP-M01-US-03)."""

    code = "validation_failed"

    def __init__(self, detail: str, field_errors: dict | None = None):
        super().__init__(detail, status.HTTP_422_UNPROCESSABLE_ENTITY, field_errors)


class Conflict(PlatformError):
    code = "conflict"

    def __init__(self, detail: str):
        super().__init__(detail, status.HTTP_409_CONFLICT)


class Refused(PlatformError):
    """A controlled refusal with a stated reason, rather than a silent failure.

    Generation refused for a missing variable, an unapproved template version
    or an outstanding approval lands here (PRD LOP-M04-US-06).
    """

    code = "refused"

    def __init__(self, detail: str, reasons: list[str] | None = None):
        super().__init__(detail, status.HTTP_409_CONFLICT)
        self.reasons = reasons or []

    def payload(self) -> dict:
        body = super().payload()
        body["reasons"] = self.reasons
        return body


class CapabilityDisabled(PlatformError):
    """A capability below its gate does not run (PRD section 4.2)."""

    code = "capability_disabled"

    def __init__(self, capability: str, reason: str):
        super().__init__(
            f"The {capability} capability is not available. {reason}",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
