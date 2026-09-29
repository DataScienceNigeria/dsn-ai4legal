"""Application configuration.

Every value is environment-driven so that the same image runs in development,
staging and production without a rebuild (PRD section 10.2).
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: The repository's own .env, found from this file rather than from the working
#: directory. The API is run three ways, from the repository root in a
#: container, from apps/api by uvicorn, and from apps/api by pytest, and a
#: relative path meant each of those read a different file, or none. A local
#: apps/api/.env is still read after it and still wins, which is what makes a
#: per-checkout override possible without a second copy of everything.
_REPO_ROOT_ENV = next(
    (
        parent / ".env"
        for parent in Path(__file__).resolve().parents
        if (parent / ".env").is_file()
    ),
    Path(".env"),
)

def _default_storage_root() -> Path:
    """Where documents go when nothing says otherwise.

    Found by looking for the repository root rather than by counting parents:
    this file is four levels below the root in a checkout and two below ``/srv``
    in the image, so a fixed index raises IndexError in the container and takes
    the whole deployment down at import.

    Compose sets DSNLAI_STORAGE_PATH explicitly, so this is the development
    default and the image's fallback, never the production path.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return here.parents[2]


_REPO_ROOT = _default_storage_root()

#: The key the platform ships with. Anything holding it can sign a token for
#: any role, so a deployment that is not development refuses to start on it.
DEVELOPMENT_SECRET_KEY = "development-secret-key-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="", env_file=(_REPO_ROOT_ENV, ".env"), extra="ignore"
    )

    dsnlai_env: str = "development"
    dsnlai_secret_key: str = DEVELOPMENT_SECRET_KEY

    # Where the interface is served from. Empty in development, which allows
    # any origin. Outside development this is the list, and an empty one means
    # the interface cannot sign in, so it is reported on startup rather than
    # left to read as a CORS error in somebody's console.
    dsnlai_allowed_origins: str = ""
    dsnlai_access_token_minutes: int = 60
    dsnlai_step_up_window_minutes: int = 5

    postgres_db: str = "dsn_lai"
    postgres_user: str = "dsnlai_owner"
    postgres_password: str = "dsnlai_owner_dev_password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    dsnlai_app_db_user: str = "dsnlai_app"
    dsnlai_app_db_password: str = "dsnlai_app_dev_password"

    redis_url: str = "redis://localhost:6379/0"
    # Where documents live. local is a folder, for development. azure is Azure
    # Blob Storage, for production, reached by managed identity unless a
    # connection string is set. There is no fallback from one to the other.
    dsnlai_storage_backend: str = "local"
    dsnlai_storage_path: str = str(_REPO_ROOT / "storage")
    azure_storage_account_url: str = ""
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "ai4legal"

    # local issues its own token. oidc verifies one issued by Keycloak,
    # Entra ID or Google Workspace against the issuer's published keys.
    dsnlai_auth_mode: str = "local"
    dsnlai_oidc_issuer: str = ""
    dsnlai_oidc_audience: str = "dsn-lai-api"
    dsnlai_oidc_jwks_url: str = ""
    dsnlai_oidc_roles_claim: str = "roles"
    dsnlai_oidc_entities_claim: str = "entities"
    dsnlai_oidc_jwks_cache_seconds: int = 3600
    dsnlai_oidc_allow_local_fallback: bool = False

    # Multi-factor authentication. Enforced for the roles named here, which is
    # everyone who can publish, sign, restrict or administer.
    # The whole second-factor module, on or off. Off is a development
    # convenience and nothing else: no code is demanded at sign-in, no
    # privileged act asks for one, and enrolment still works so it can be
    # exercised before it is turned back on.
    dsnlai_mfa_enabled: bool = True
    dsnlai_mfa_required_roles: str = "admin,head_of_legal"
    dsnlai_mfa_issuer: str = "DSN Legal Operations"
    dsnlai_totp_window: int = 1

    # SCIM 2.0 provisioning. The bearer token is what the directory presents.
    dsnlai_scim_enabled: bool = False
    dsnlai_scim_token: str = ""
    dsnlai_scim_default_entity: str = "DSN"

    # E-signature. internal is the built-in simulation, which stays the
    # fallback whenever no provider is configured.
    dsnlai_signature_provider: str = "internal"
    #: Self-hosted OpenSign. DocuSeal was here first and could not do the job
    #: in its free edition: every route that accepts a document answers 404
    #: with a link to its pricing page, and its image carries no converter.
    opensign_base_url: str = "http://localhost:8080/app"
    opensign_app_id: str = "opensign"
    opensign_email: str = ""
    opensign_password: str = ""
    opensign_webhook_secret: str = ""
    #: Where a person opens the signing service, as opposed to where the
    #: platform calls it. A browser resolves this one.
    opensign_client_url: str = "http://localhost:3200"

    # Notification delivery. Anything not configured falls back to the log,
    # which is what the outbox did before any transport existed.
    dsnlai_notify_transport: str = "log"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "legal@dsn.example"
    smtp_starttls: bool = True
    dsnlai_webhook_url: str = ""
    dsnlai_webhook_secret: str = ""

    # Malware scanning. Without a scanner the magic-byte heuristic applies and
    # says so, rather than claiming a clean result it cannot support.
    dsnlai_clamav_host: str = ""
    dsnlai_clamav_port: int = 3310
    dsnlai_clamav_timeout_seconds: float = 30.0

    # Embeddings. The deterministic projection is the fallback, and the
    # dimension is pinned because the column is typed to it.
    dsnlai_embedding_provider: str = "deterministic"
    dsnlai_embedding_model: str = "text-embedding-3-small"

    openai_api_key: str = ""
    openai_base_url: str = ""
    dsnlai_ai_default_model: str = "gpt-5"
    dsnlai_ai_local_base_url: str = ""
    dsnlai_ai_local_model: str = "local-open-weights"
    dsnlai_ai_effort: str = "high"
    dsnlai_ai_send_effort: bool = True
    dsnlai_ai_max_tokens: int = 16000
    dsnlai_ai_timeout_seconds: float = 120.0
    dsnlai_ai_input_cost_per_mtok: float = 1.25
    dsnlai_ai_output_cost_per_mtok: float = 10.0

    dsnlai_max_upload_mb: int = 50
    # Spreadsheets and presentations are here because a counterparty's rate
    # card or schedule usually is one, and refusing it kept the covering note
    # while losing the thing it covered.
    dsnlai_allowed_upload_types: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/msword,text/plain,image/png,image/jpeg,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/vnd.ms-excel,text/csv,"
        "application/vnd.openxmlformats-officedocument.presentationml.presentation,"
        "application/vnd.ms-powerpoint"
    )

    @property
    def owner_dsn(self) -> str:
        """DSN for migrations and administration. Bypasses row-level security."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def app_dsn(self) -> str:
        """DSN for request handling. Subject to row-level security (LOP-NFR-13)."""
        return (
            f"postgresql+psycopg://{self.dsnlai_app_db_user}:{self.dsnlai_app_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_development(self) -> bool:
        return self.dsnlai_env == "development"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.dsnlai_allowed_origins.split(",") if o.strip()]

    @property
    def allowed_upload_types(self) -> list[str]:
        return [t.strip() for t in self.dsnlai_allowed_upload_types.split(",") if t.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
