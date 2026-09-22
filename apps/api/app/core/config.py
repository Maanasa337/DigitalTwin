from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TV_", env_file=".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://twinvoice:twinvoice@127.0.0.1:5433/twinvoice"
    valkey_url: str = "redis://localhost:6379/0"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    ditto_url: str = "http://localhost:8080"
    ditto_subject: str = "pre:twinvoice-api"

    # Tokens are issued to the browser via the public URL, but the API reaches Keycloak on the internal network.
    keycloak_issuer: str = "http://localhost:8081/realms/twinvoice"
    keycloak_internal_url: str = "http://localhost:8081"
    keycloak_realm: str = "twinvoice"
    keycloak_client_id: str = "twinvoice-api"
    keycloak_client_secret: str = "twinvoice-api-dev-secret"

    simulator_url: str = "http://localhost:8090"

    # Narration paraphrase (M6). Unset means template-only narration, which is the safe default.
    llm_endpoint: str | None = None
    llm_model: str = "qwen3"

    # M10 archive root (FR-RP-06). Relative to the working directory, and a compose volume.
    report_archive_dir: str = "data/reports"

    # M5 model bundles, public benchmark data (data/download.py), benchmark reports and simulator
    # exports. Absolute in the containers (compose volumes); override for a host run.
    models_dir: str = "/data/models"
    raw_data_dir: str = "/data/raw"
    benchmarks_dir: str = "/data/benchmarks"
    synthetic_dir: str = "/data/synthetic"

    allow_t3: bool = False
    command_ack_timeout_s: float = 5.0

    @property
    def keycloak_realm_url(self) -> str:
        return f"{self.keycloak_internal_url}/realms/{self.keycloak_realm}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
