import httpx

from control_plane.app.services.sync_service import _friendly_ctfd_http_error_message


def _http_status_error(status_code: int, location: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://demo.ctfd.io/api/v1/challenges")
    headers = {}
    if location is not None:
        headers["location"] = location
    response = httpx.Response(status_code, headers=headers, request=request)
    return httpx.HTTPStatusError("ctfd request failed", request=request, response=response)


def test_session_cookie_redirect_to_login_maps_to_human_error() -> None:
    exc = _http_status_error(302, "/login?next=%2Fapi%2Fv1%2Fchallenges%3F")
    message = _friendly_ctfd_http_error_message("session_cookie", exc)
    assert message == "CTFd session cookie is invalid or expired. Paste a fresh session cookie and try again."


def test_session_cookie_unauthorized_maps_to_human_error() -> None:
    exc = _http_status_error(403)
    message = _friendly_ctfd_http_error_message("session_cookie", exc)
    assert message == "CTFd session cookie is invalid or expired. Paste a fresh session cookie and try again."


def test_api_token_unauthorized_maps_to_human_error() -> None:
    exc = _http_status_error(401)
    message = _friendly_ctfd_http_error_message("api_token", exc)
    assert message == "CTFd API token is invalid or missing required permissions."


def test_non_auth_http_error_returns_none() -> None:
    exc = _http_status_error(500)
    message = _friendly_ctfd_http_error_message("session_cookie", exc)
    assert message is None
