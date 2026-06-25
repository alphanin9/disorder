import json

import httpx
import pytest
import respx

from control_plane.app.adapters.ctfd import extract_file_entries
from control_plane.app.adapters.rctf import RCTFAuthError, RCTFClient


def test_rctf_client_login_list_submit_flow() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        def login_handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.read()) == {"teamToken": "team-tok"}
            return httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt-123"}})

        def challs_handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer jwt-123"
            return httpx.Response(
                200,
                json={
                    "kind": "goodChallenges",
                    "data": [
                        {
                            "id": "abc",
                            "name": "Warmup",
                            "category": "pwn",
                            "description": "nc chal.local 1337",
                            "author": "tester",
                            "files": [{"name": "chal.zip", "url": "/uploads/deadbeef/chal.zip"}],
                            "points": 480,
                        }
                    ],
                },
            )

        def submit_handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer jwt-123"
            return httpx.Response(200, json={"kind": "goodFlag", "message": "Correct flag!"})

        mock_router.post("https://rctf.local/api/v1/auth/login").mock(side_effect=login_handler)
        mock_router.get("https://rctf.local/api/v1/challs").mock(side_effect=challs_handler)
        mock_router.get("https://rctf.local/uploads/deadbeef/chal.zip").mock(
            return_value=httpx.Response(200, content=b"abc")
        )
        mock_router.post("https://rctf.local/api/v1/challs/abc/submit").mock(side_effect=submit_handler)

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok")
        try:
            challenges = client.list_challenges()
            assert len(challenges) == 1
            assert challenges[0].challenge_id == "abc"
            assert challenges[0].points == 480

            detail = client.get_challenge("abc")
            files = extract_file_entries(detail)
            assert files == [{"name": "chal.zip", "url": "/uploads/deadbeef/chal.zip"}]

            data = client.download_file("/uploads/deadbeef/chal.zip")
            assert data == b"abc"

            verdict = client.submit_flag("abc", "flag{demo}")
            assert verdict["kind"] == "goodFlag"
        finally:
            client.close()


def test_rctf_client_login_failure_raises_auth_error() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(
                400, json={"kind": "badTokenVerification", "message": "Invalid team token."}
            )
        )

        client = RCTFClient(base_url="https://rctf.local", team_token="bad")
        try:
            with pytest.raises(RCTFAuthError, match="Invalid team token."):
                client.list_challenges()
        finally:
            client.close()


def test_rctf_client_reauths_on_expired_token() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        tokens = iter(["jwt-old", "jwt-new"])

        def login_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": next(tokens)}})

        calls = {"n": 0}

        def challs_handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                assert request.headers.get("Authorization") == "Bearer jwt-old"
                return httpx.Response(401, json={"kind": "badToken", "message": "expired"})
            assert request.headers.get("Authorization") == "Bearer jwt-new"
            return httpx.Response(200, json={"kind": "goodChallenges", "data": []})

        mock_router.post("https://rctf.local/api/v1/auth/login").mock(side_effect=login_handler)
        mock_router.get("https://rctf.local/api/v1/challs").mock(side_effect=challs_handler)

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok")
        try:
            assert client.list_challenges() == []
            assert calls["n"] == 2
        finally:
            client.close()
