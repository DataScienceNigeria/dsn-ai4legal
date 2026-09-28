"""Object storage.

Where documents live is a setting, not a guess. ``local`` keeps them in a
folder, which is what development uses. ``azure`` keeps them in Azure Blob
Storage, where an executed copy is written under a version-level immutability
policy for its retention period (PRD section 10 and LOP-M08-US-01).

There is no fallback between the two. The store used to drop to a local folder
whenever the object store could not be reached, and in production that would
put signed agreements on the server's own disk, with no lock and no backup,
while every screen looked normal. An unreachable store now fails the request
that needed it and, for Azure, stops the platform starting at all.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.errors import PlatformError, ValidationFailed
from app.services.hashing import file_hash

logger = logging.getLogger(__name__)


class StorageUnavailable(PlatformError):
    code = "storage_unavailable"

    def __init__(self, detail: str):
        super().__init__(detail, 503)


class LocalStore:
    """A folder. Development only: a folder cannot refuse to be edited, so the
    immutability of an executed copy rests on the database constraint here."""

    name = "local"

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    def _path(self, key: str) -> pathlib.Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValidationFailed("That storage key is not allowed.", {"key": key})
        return path

    def verify(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def put_immutable(self, key: str, data: bytes, content_type: str, retain_years: int) -> str:
        return self.put(key, data, content_type)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageUnavailable(f"{key} is not in the document store.") from exc

    def keys(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            str(path.relative_to(self.root)) for path in self.root.rglob("*") if path.is_file()
        )


class AzureStore:
    """Azure Blob Storage.

    Managed identity where the platform runs in Azure, so there is no account
    key to leak; a connection string only where one is configured, which is
    staging. The container must have version-level immutability enabled, or
    Azure refuses the policy an executed copy is written under, and that
    refusal is the correct outcome rather than something to work around.
    """

    name = "azure"

    def __init__(self) -> None:
        self._container = None

    def _client(self):
        if self._container is not None:
            return self._container
        try:
            from azure.storage.blob import BlobServiceClient

            if settings.azure_storage_connection_string:
                service = BlobServiceClient.from_connection_string(
                    settings.azure_storage_connection_string
                )
            else:
                from azure.identity import DefaultAzureCredential

                service = BlobServiceClient(
                    account_url=settings.azure_storage_account_url,
                    credential=DefaultAzureCredential(),
                )
            self._container = service.get_container_client(settings.azure_storage_container)
        except Exception as exc:
            raise StorageUnavailable(f"Azure Blob Storage is not reachable: {exc}") from exc
        return self._container

    def verify(self) -> None:
        if not (settings.azure_storage_connection_string or settings.azure_storage_account_url):
            raise StorageUnavailable(
                "DSNLAI_STORAGE_BACKEND is azure but no account URL or connection string is set."
            )
        try:
            container = self._client()
            if not container.exists():
                raise StorageUnavailable(
                    f"The container {settings.azure_storage_container} does not exist."
                )
            properties = container.get_container_properties()
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"Azure Blob Storage is not reachable: {exc}") from exc

        # Said here rather than discovered at the first signed agreement. The
        # container capability can only be set when the container is created,
        # so learning about it late means making the container again.
        if not properties.immutable_storage_with_versioning_enabled:
            logger.warning(
                "%s does not have version-level immutability, so an executed copy "
                "cannot be written write-once and filing one will fail. It can only "
                "be enabled on a new container, with blob versioning on for the "
                "account first.",
                settings.azure_storage_container,
            )

    def put(self, key: str, data: bytes, content_type: str) -> str:
        from azure.storage.blob import ContentSettings

        try:
            self._client().upload_blob(
                key,
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"The document could not be stored: {exc}") from exc
        return key

    def put_immutable(self, key: str, data: bytes, content_type: str, retain_years: int) -> str:
        from azure.storage.blob import (
            BlobImmutabilityPolicyMode,
            ContentSettings,
            ImmutabilityPolicy,
        )

        policy = ImmutabilityPolicy(
            expiry_time=datetime.now(UTC) + timedelta(days=365 * retain_years),
            policy_mode=BlobImmutabilityPolicyMode.UNLOCKED,
        )
        try:
            self._client().upload_blob(
                key,
                data,
                overwrite=False,
                content_settings=ContentSettings(content_type=content_type),
                immutability_policy=policy,
            )
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"The executed copy could not be stored: {exc}") from exc
        return key

    def get(self, key: str) -> bytes:
        try:
            return self._client().download_blob(key).readall()
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"{key} could not be read from the document store.") from exc

    def keys(self) -> list[str]:
        return sorted(blob.name for blob in self._client().list_blobs())


class ObjectStore:
    """The configured backend, and nothing else."""

    def __init__(self) -> None:
        self._backend: LocalStore | AzureStore | None = None

    @property
    def backend(self) -> LocalStore | AzureStore:
        if self._backend is None:
            self._backend = build(settings.dsnlai_storage_backend)
        return self._backend

    def verify(self) -> None:
        self.backend.verify()

    def put(self, key: str, data: bytes, content_type: str) -> str:
        return self.backend.put(key, data, content_type)

    def put_immutable(self, key: str, data: bytes, content_type: str, retain_years: int = 7) -> str:
        """Store an executed copy so it cannot be changed for its retention period."""
        return self.backend.put_immutable(key, data, content_type, retain_years)

    def get(self, key: str) -> bytes:
        return self.backend.get(key)


def build(backend: str) -> LocalStore | AzureStore:
    if backend == "local":
        return LocalStore(pathlib.Path(settings.dsnlai_storage_path))
    if backend == "azure":
        return AzureStore()
    raise ValueError(f"DSNLAI_STORAGE_BACKEND must be local or azure, not {backend!r}.")


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
