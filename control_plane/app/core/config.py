from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ctf-harness-control-plane"
    app_env: str = Field(default="dev")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    database_url: str = Field(
        default="postgresql+psycopg://ctf:ctf@postgres:5432/ctf_harness"
    )

    minio_endpoint: str = Field(default="http://minio:9000")
    minio_access_key: str = Field(default="minio")
    minio_secret_key: str = Field(default="minio123")
    minio_bucket: str = Field(default="ctf-harness")
    minio_region: str = Field(default="us-east-1")

    runs_dir: Path = Field(default=Path("./runs").resolve())
    docker_bind_runs_dir: Path = Field(default=Path("./runs").resolve())
    sandbox_image: str = Field(default="ctf-agent-sandbox:latest")
    sandbox_build_target: str | None = Field(default="full")
    docker_socket: str = Field(default="unix://var/run/docker.sock")

    default_cpu_limit: float = Field(default=1.0)
    default_mem_limit: str = Field(default="1g")
    default_pids_limit: int = Field(default=256)
    enable_run_continuation: bool = Field(default=True)
    max_continuation_message_chars: int = Field(default=4000)
    max_continuation_depth: int = Field(default=5)
    max_continuation_deliverables: int = Field(default=16)
    max_continuation_deliverable_bytes: int = Field(default=5 * 1024 * 1024)
    max_continuation_total_bytes: int = Field(default=20 * 1024 * 1024)
    sandbox_env_passthrough: str = Field(
        default=(
            "OPENAI_API_KEY,OPENAI_BASE_URL,OPENAI_ORG_ID,OPENAI_PROJECT_ID,"
            "CODEX_API_KEY,CODEX_BASE_URL,CODEX_CLI_CMD,"
            "CODEX_JSONL_LIVE_LOG_ONLY,CODEX_FLAG_VERIFY_MCP_ENABLED,"
            "ANTHROPIC_API_KEY,ANTHROPIC_BASE_URL,ANTHROPIC_MODEL,"
            "CLAUDE_CODE_OAUTH_TOKEN,CLAUDE_CODE_CLI_CMD,"
            "CLAUDE_FLAG_VERIFY_MCP_ENABLED"
        )
    )
    sandbox_codex_auth_include: str = Field(
        default="auth.json,credentials.json,token.json,*auth*.json,*token*.json,*credential*.json,*session*.json"
    )
    sandbox_codex_auth_tag: str | None = Field(default=None)
    sandbox_codex_skills_host_path: str | None = Field(default=None)
    sandbox_ida_host_path: str | None = Field(default=None)
    sandbox_ida_mount_path: str = Field(default="/opt/ida")
    sandbox_ida_registry_host_path: str | None = Field(default=None)
    sandbox_ida_accept_eula: bool = Field(default=True)
    sandbox_ida_eula_versions: str = Field(default="90,91,92,93")
    sandbox_control_plane_url: str | None = Field(default=None)
    sandbox_flag_submit_mcp_enabled: bool = Field(default=False)
    codex_auth_encryption_key: str | None = Field(default=None)
    codex_auth_max_file_bytes: int = Field(default=262_144)
    codex_auth_health_check_interval_seconds: int = Field(default=6 * 60 * 60)
    codex_auth_device_flow_timeout_seconds: int = Field(default=15 * 60)
    codex_auth_limit_probe_enabled: bool = Field(default=True)
    codex_auth_limit_probe_model: str = Field(default="gpt-5.3-codex")
    # Claude Code (Anthropic) auth. The OAuth credential store reuses the Codex
    # Fernet cipher (codex_auth_encryption_key / derived dev key). Endpoints are
    # configurable because Anthropic's OAuth hosts have shifted historically;
    # defaults reflect the public Claude Code authorization-code + PKCE flow.
    sandbox_claude_auth_tag: str | None = Field(default=None)
    claude_auth_health_check_interval_seconds: int = Field(default=6 * 60 * 60)
    claude_auth_device_flow_timeout_seconds: int = Field(default=15 * 60)
    claude_auth_usage_probe_enabled: bool = Field(default=True)
    claude_oauth_client_id: str = Field(
        default="9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    )
    claude_oauth_authorize_url: str = Field(
        default="https://claude.ai/oauth/authorize"
    )
    claude_oauth_token_url: str = Field(
        default="https://console.anthropic.com/v1/oauth/token"
    )
    claude_oauth_redirect_uri: str = Field(
        default="https://console.anthropic.com/oauth/code/callback"
    )
    claude_oauth_scopes: str = Field(
        default="org:create_api_key user:profile user:inference"
    )
    claude_oauth_usage_url: str = Field(
        default="https://api.anthropic.com/api/oauth/usage"
    )
    ctfd_auto_submit_enabled: bool = Field(default=True)
    ctfd_auto_submit_max_attempts_per_run: int = Field(default=8)
    ctfd_auto_submit_retry_count: int = Field(default=0)
    discord_webhook_url: str | None = Field(default=None)
    discord_notify_on_flag: bool = Field(default=True)
    discord_notify_include_flag: bool = Field(default=True)
    sandbox_gpu_passthrough: bool = Field(default=False)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    return settings
