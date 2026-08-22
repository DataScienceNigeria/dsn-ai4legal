"""Object storage.

Documents live in MinIO with versioning and object lock, so an executed copy is
write-once for its retention period (PRD section 10.1 and LOP-M08-US-01). When
the object store is unreachable the platform falls back to a local directory,
so a development environment needs no infrastructure.
"""

from __future__ import annotations

import io
import logging
import pathlib

from app.core.config import settings
from app.core.errors import ValidationFailed
from app.services.hashing import file_hash

logger = logging.getLogger(__name__)

LOCAL_ROOT = pathlib.Path(".storage")


class ObjectStore:
    def __init__(self) -> None:
        self._client = None
        self._checked = False

    def _get_client(self):
        if self._checked:
            return self._client
        self._checked = True
        try:
            from minio import Minio

            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            if not client.bucket_exists(settings.minio_bucket):
                client.make_bucket(settings.minio_bucket, object_lock=True)
            self._client = client
        except Exception as exc:
            logger.warning("Object store unavailable, using the local fallback: %s", exc)
            self._client = None
        return self._client

    def put(self, key: str, data: bytes, content_type: str) -> str:
        client = self._get_client()
        if client is None:
            path = LOCAL_ROOT / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return key
        client.put_object(
            settings.minio_bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return key

    def get(self, key: str) -> bytes:
        client = self._get_client()
        if client is None:
            return (LOCAL_ROOT / key).read_bytes()
        response = client.get_object(settings.minio_bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def put_immutable(self, key: str, data: bytes, content_type: str, retain_years: int = 7) -> str:
        """Store an executed copy under object lock."""
        from datetime import UTC, datetime, timedelta

        client = self._get_client()
        if client is None:
            return self.put(key, data, content_type)
        from minio.commonconfig import GOVERNANCE
        from minio.retention import Retention

        client.put_object(
            settings.minio_bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            retention=Retention(
                GOVERNANCE, datetime.now(UTC) + timedelta(days=365 * retain_years)
            ),
        )
        return key


store = ObjectStore()


def validate_upload(filename: str, content_type: str, data: bytes) -> str:
    """Uploads are content-type verified and size checked before storage.

    LOP-NFR-14 also requires virus scanning with quarantine on failure. That is
    `scan_upload`, which the caller runs before storing what this returns.
    """
    max_bytes = settings.dsnlai_max_upload_mb * 1024 * 1024
    errors: dict[str, str] = {}

    if len(data) > max_bytes:
        errors["file"] = f"The file is larger than the {settings.dsnlai_max_upload_mb} MB limit."
    if content_type not in settings.allowed_upload_types:
        errors["content_type"] = f"{content_type} is not an accepted file type."
    if not filename.strip():
        errors["filename"] = "A filename is required."

    sniffed = sniff(data)
    if sniffed and sniffed != content_type:
        errors["content_type"] = (
            f"The file content looks like {sniffed}, which does not match the declared "
            f"type {content_type}."
        )

    if errors:
        raise ValidationFailed("This file cannot be accepted.", errors)

    return file_hash(data)


SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
]


def sniff(data: bytes) -> str | None:
    """Identify a file by its leading bytes, ignoring the declared type."""
    for magic, content_type in SIGNATURES:
        if data.startswith(magic):
            return content_type
    if data.startswith(b"PK\x03\x04"):
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if b"word/" in data[:4096]
            else None
        )
    return None


def scan_upload(data: bytes) -> tuple[bool, str]:
    """Scan an upload before it is stored.

    ClamAV where a daemon is configured, a header heuristic where none is, and
    a refusal where a configured scanner cannot be reached. Quarantine on
    failure is the caller's job.
    """
    from app.services.malware import scan

    return scan(data)
