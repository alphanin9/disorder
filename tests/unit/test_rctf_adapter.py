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

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok", api_version="v1")
        try:
            challenges = client.list_challenges()
            assert client.negotiated_version == "v1"
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

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok", api_version="v1")
        try:
            assert client.list_challenges() == []
            assert calls["n"] == 2
        finally:
            client.close()


_V2_CHALL = {
    "id": "web_end",
    "name": "EnD",
    "category": "web",
    "description": "BLOCK BLOCK\n\n> [!CONNECTION]\n> nc end.chals.example 1337",
    "author": "zonkor",
    "files": [{"name": "web_end.tar.gz", "url": "/uploads/abc/web_end.tar.gz", "size": 16736}],
    "points": 500,
    "solves": 3,
    "tags": ["⭐⭐⭐⭐"],
    "instancerLifetime": 1800000,
    "instancerExtendable": True,
    "instancerStoppable": True,
    "instancerActions": [],
    "adminBotInputs": None,
    "hasFlag": True,
    "scoringKind": "decay",
}

_V2_STATIC_CHALL = {
    "id": "rev_static",
    "name": "Static",
    "category": "rev",
    "description": "no remote",
    "files": [],
    "points": 100,
    "solves": 92,
    "tags": ["SEKAI"],
    "instancerLifetime": None,
    "instancerExtendable": True,
    "instancerStoppable": True,
    "instancerActions": [],
    "hasFlag": True,
    "scoringKind": "decay",
}


def test_rctf_client_v2_list_parses_metadata() -> None:
    from control_plane.app.adapters.rctf import challenge_metadata

    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt"}})
        )

        def challs_v2(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer jwt"
            return httpx.Response(
                200,
                json={"kind": "goodChallengesV2", "data": [_V2_CHALL, _V2_STATIC_CHALL]},
            )

        mock_router.get("https://rctf.local/api/v2/challs").mock(side_effect=challs_v2)

        # api_version defaults to "auto" -> v2 is tried first and succeeds.
        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok")
        try:
            challenges = client.list_challenges()
            assert client.negotiated_version == "v2"
            assert [c.challenge_id for c in challenges] == ["web_end", "rev_static"]

            end = challenges[0]
            assert end.tags == ["⭐⭐⭐⭐"]
            assert end.solves == 3
            assert end.scoring_kind == "decay"
            assert end.has_flag is True
            assert end.instancer is not None
            assert end.instancer.lifetime_ms == 1800000
            assert end.instancer.stoppable is True

            # Static challenges carry instancer* keys but no live instance.
            assert challenges[1].instancer is None

            meta = challenge_metadata(end)
            assert meta["tags"] == ["⭐⭐⭐⭐"]
            assert meta["scoring_kind"] == "decay"
            assert meta["instancer"]["lifetime_ms"] == 1800000
            assert "instancer" not in challenge_metadata(challenges[1])
        finally:
            client.close()


def test_rctf_client_auto_falls_back_to_v1() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt"}})
        )
        # v2 endpoint is not served by this (older) instance.
        mock_router.get("https://rctf.local/api/v2/challs").mock(
            return_value=httpx.Response(
                404, json={"kind": "badEndpoint", "message": "The request endpoint could not be found."}
            )
        )
        mock_router.get("https://rctf.local/api/v1/challs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "kind": "goodChallenges",
                    "data": [{"id": "abc", "name": "W", "category": "pwn", "points": 1}],
                },
            )
        )

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok")
        try:
            challenges = client.list_challenges()
            assert client.negotiated_version == "v1"
            assert len(challenges) == 1
            # No v2 enrichment when falling back to v1.
            assert challenges[0].tags == []
            assert challenges[0].scoring_kind is None
        finally:
            client.close()


def test_rctf_client_download_omits_bearer_for_external_storage() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt"}})
        )

        def same_origin(request: httpx.Request) -> httpx.Response:
            # Same-origin uploads still carry the bearer (instance may gate them).
            assert request.headers.get("Authorization") == "Bearer jwt"
            return httpx.Response(200, content=b"local")

        def external(request: httpx.Request) -> httpx.Response:
            # External object storage (GCS/S3) must NOT receive the rCTF bearer,
            # otherwise it rejects the request with HTTP 401.
            assert "Authorization" not in request.headers
            return httpx.Response(200, content=b"remote")

        mock_router.get("https://rctf.local/uploads/x/local.bin").mock(side_effect=same_origin)
        mock_router.get("https://files.example.com/uploads/y/remote.tar.gz").mock(side_effect=external)

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok")
        try:
            client.login()  # populate the auth token
            assert client.download_file("/uploads/x/local.bin") == b"local"
            assert client.download_file("https://files.example.com/uploads/y/remote.tar.gz") == b"remote"
        finally:
            client.close()


def test_rctf_client_explicit_v2_does_not_fall_back() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt"}})
        )
        mock_router.get("https://rctf.local/api/v2/challs").mock(
            return_value=httpx.Response(404, json={"kind": "badEndpoint", "message": "nope"})
        )

        client = RCTFClient(base_url="https://rctf.local", team_token="team-tok", api_version="v2")
        try:
            with pytest.raises(RCTFAuthError, match="nope"):
                client.list_challenges()
        finally:
            client.close()
