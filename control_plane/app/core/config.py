from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ctf-harness-control-plane"
    app_env: str = Field(default="dev")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    database_url: str = Field(default="postgresql+psycopg://ctf:ctf@postgres:5432/ctf_harness")

    minio_endpoint: str = Field(default="http://minio:9000")
    minio_access_key: str = Field(default="minio")
    minio_secret_key: str = Field(default="minio123")
    minio_bucket: str = Field(default="ctf-harness")
    minio_region: str = Field(default="us-east-1")

    runs_dir: Path = Field(default=Path("./runs").resolve())
    docker_bind_runs_dir: Path = Field(default=Path("./runs").resolve())
    sandbox_image: str = Field(default="ctf-agent-sandbox:latest")
    docker_socket: str = Field(default="unix://var/run/docker.sock")

    default_cpu_limit: float = Field(default=1.0)
    default_mem_limit: str = Field(default="1g")
    default_pids_limit: int = Field(default=256)
    sandbox_env_passthrough: str = Field(
        default=(
            "OPENAI_API_KEY,OPENAI_BASE_URL,OPENAI_ORG_ID,OPENAI_PROJECT_ID,"
            "CODEX_API_KEY,CODEX_BASE_URL,CODEX_MODEL,CODEX_CLI_CMD,"
            "ANTHROPIC_API_KEY,CLAUDE_CODE_CLI_CMD"
        )
    )
    sandbox_codex_auth_path: str | None = Field(default=None)
    sandbox_codex_auth_mode: str = Field(default="auth_only")
    sandbox_codex_auth_include: str = Field(
        default="auth.json,credentials.json,token.json,*auth*.json,*token*.json,*credential*.json,*session*.json"
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    return settings
