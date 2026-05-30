import base64
import json

from control_plane.app.services.auth_service import (
    CODEX_DEVICE_VERIFICATION_URI,
    _build_codex_auth_json,
    _parse_quota_snapshot,
    _quota_status,
    is_allowed_auth_file_name,
    normalize_auth_tag,
    sanitize_auth_file_name,
)


def test_normalize_auth_tag_accepts_valid_values() -> None:
    assert normalize_auth_tag("default") == "default"
    assert normalize_auth_tag("team.alpha-01") == "team.alpha-01"


def test_normalize_auth_tag_rejects_invalid_values() -> None:
    for invalid in ("", " ", "..bad", "tag with spaces", "x" * 100):
        try:
            normalize_auth_tag(invalid)
        except ValueError:
            continue
        raise AssertionError(f"Expected invalid tag to fail: {invalid!r}")


def test_sanitize_auth_file_name_drops_directories() -> None:
    assert sanitize_auth_file_name("nested/path/auth.json") == "auth.json"
    assert sanitize_auth_file_name("..\\token.json") == "token.json"


def test_auth_file_allowlist_defaults() -> None:
    assert is_allowed_auth_file_name("auth.json")
    assert is_allowed_auth_file_name("my-token.json")
    assert not is_allowed_auth_file_name("notes.txt")


def test_build_codex_auth_json_matches_cli_shape() -> None:
    claims = {"email": "User@Example.COM", "https://api.openai.com/auth": {"chatgpt_account_id": "acct_123"}}
    encoded_claims = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("utf-8").rstrip("=")
    id_token = f"header.{encoded_claims}.signature"

    raw = _build_codex_auth_json(
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": id_token,
        }
    )

    payload = json.loads(raw)
    assert payload["auth_mode"] == "chatgpt"
    assert payload["OPENAI_API_KEY"] is None
    assert payload["email"] == "user@example.com"
    assert payload["tokens"]["access_token"] == "access-token"
    assert payload["tokens"]["refresh_token"] == "refresh-token"
    assert payload["tokens"]["id_token"] == id_token
    assert payload["tokens"]["account_id"] == "acct_123"


def test_build_codex_auth_json_falls_back_to_access_token_id_token() -> None:
    payload = json.loads(_build_codex_auth_json({"access_token": "access-token", "refresh_token": "refresh-token"}))
    assert payload["tokens"]["id_token"] == "access-token"


def test_codex_device_verification_uri() -> None:
    assert CODEX_DEVICE_VERIFICATION_URI == "https://auth.openai.com/codex/device"


def test_parse_quota_snapshot_from_codex_headers() -> None:
    from httpx import Headers

    snapshot = _parse_quota_snapshot(
        Headers(
            {
                "x-codex-primary-used-percent": "25",
                "x-codex-primary-window-minutes": "300",
                "x-codex-secondary-used-percent": "99.5",
                "x-codex-secondary-window-minutes": "10080",
                "x-codex-plan-type": "plus",
                "x-codex-active-limit": "2",
            }
        ),
        status_code=200,
        model="gpt-5.3-codex",
    )

    assert snapshot is not None
    assert snapshot["plan_type"] == "plus"
    assert snapshot["active_limit"] == 2
    assert snapshot["primary"]["used_percent"] == 25
    assert snapshot["secondary"]["window_minutes"] == 10080
    assert _quota_status(snapshot) == "available"


def test_quota_status_detects_exhausted_and_rate_limited() -> None:
    assert _quota_status({"status": 429, "primary": {}, "secondary": {}}) == "rate_limited"
    assert _quota_status({"status": 200, "primary": {"used_percent": 100}, "secondary": {}}) == "exhausted"
