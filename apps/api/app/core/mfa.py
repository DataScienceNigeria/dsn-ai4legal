"""Time-based one-time passwords, PRD section 5.1.

A password proves someone knew a secret once. A second factor proves someone
holds a device now, which is the property step-up actually needs before a
signature, a publication or an access grant.

RFC 6238 is implemented here rather than pulled in, because it is thirty lines
of standard library and one fewer dependency in a build that has to be audited.
Nothing about it is novel; the constants are the ones the RFC names.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from app.core.config import settings

DIGITS = 6
PERIOD = 30
RECOVERY_CODE_COUNT = 10


def generate_secret() -> str:
    """A base32 secret of the length RFC 4226 recommends."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Single-use codes for the day the device is lost.

    Without these, losing a phone means an administrator turning the factor off
    for someone, which is exactly the request an attacker would make.
    """
    def one() -> str:
        return "-".join(secrets.token_hex(2) for _ in range(3))

    return [one() for _ in range(count)]


def _counter_code(secret: str, counter: int) -> str:
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**DIGITS)).zfill(DIGITS)


def code_at(secret: str, when: float | None = None) -> str:
    return _counter_code(secret, int((when or time.time()) // PERIOD))


def verify(secret: str, code: str, last_counter: int | None = None) -> int | None:
    """Return the counter the code matched, or None.

    The caller stores the counter so the same code cannot be presented twice.
    A one-time password that can be replayed for thirty seconds is a password.
    """
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != DIGITS:
        return None

    now = int(time.time() // PERIOD)
    window = settings.dsnlai_totp_window
    for drift in range(-window, window + 1):
        counter = now + drift
        if last_counter is not None and counter <= last_counter:
            continue
        if hmac.compare_digest(_counter_code(secret, counter), candidate):
            return counter
    return None


def provisioning_uri(secret: str, email: str) -> str:
    """The otpauth URI an authenticator app reads from a QR code."""
    issuer = quote(settings.dsnlai_mfa_issuer)
    label = quote(f"{settings.dsnlai_mfa_issuer}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"
    )


def required_roles() -> set[str]:
    return {
        role.strip()
        for role in settings.dsnlai_mfa_required_roles.split(",")
        if role.strip()
    }


def is_required_for(roles: list[str]) -> bool:
    """Whether this person's roles put them inside the factor requirement."""
    return bool(required_roles() & set(roles))
