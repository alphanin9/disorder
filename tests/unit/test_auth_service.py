from control_plane.app.services.auth_service import is_allowed_auth_file_name, normalize_auth_tag, sanitize_auth_file_name


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
