from __future__ import annotations

from types import SimpleNamespace

import httpx
import respx

from control_plane.app.services.flag_submission_service import (
    _attempt_rctf_submit,
    _normalize_rctf_verdict,
)


def test_normalize_rctf_verdict_mapping() -> None:
    assert _normalize_rctf_verdict({"kind": "goodFlag"})[:2] == ("correct", True)
    assert _normalize_rctf_verdict({"kind": "badAlreadySolvedChallenge"})[:2] == ("already_solved", True)
    assert _normalize_rctf_verdict({"kind": "badFlag"})[:2] == ("incorrect", False)
    assert _normalize_rctf_verdict({"kind": "badRateLimit"})[:2] == ("rate_limited", False)
    assert _normalize_rctf_verdict({"kind": "badNotStarted"})[:2] == ("error", False)
    assert _normalize_rctf_verdict({})[:2] == ("error", False)


def test_attempt_rctf_submit_correct_flag() -> None:
    challenge = SimpleNamespace(platform_challenge_id="abc")
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt"}})
        )
        mock_router.post("https://rctf.local/api/v1/challs/abc/submit").mock(
            return_value=httpx.Response(200, json={"kind": "goodFlag", "message": "Correct flag!"})
        )

        outcome = _attempt_rctf_submit(
            challenge=challenge,
            flag="flag{demo}",
            base_url="https://rctf.local",
            auth_mode="team_token",
            secret="team-tok",
        )

    assert outcome.normalized_verdict == "correct"
    assert outcome.verified is True
    assert outcome.auth_mode == "team_token"
    assert "Correct flag!" in outcome.details


def test_attempt_rctf_submit_bad_flag() -> None:
    challenge = SimpleNamespace(platform_challenge_id="abc")
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(200, json={"kind": "goodLogin", "data": {"authToken": "jwt"}})
        )
        mock_router.post("https://rctf.local/api/v1/challs/abc/submit").mock(
            return_value=httpx.Response(200, json={"kind": "badFlag", "message": "Incorrect flag."})
        )

        outcome = _attempt_rctf_submit(
            challenge=challenge,
            flag="flag{wrong}",
            base_url="https://rctf.local",
            auth_mode="team_token",
            secret="team-tok",
        )

    assert outcome.normalized_verdict == "incorrect"
    assert outcome.verified is False


def test_attempt_rctf_submit_auth_failure_is_error() -> None:
    challenge = SimpleNamespace(platform_challenge_id="abc")
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://rctf.local/api/v1/auth/login").mock(
            return_value=httpx.Response(400, json={"kind": "badTokenVerification", "message": "bad token"})
        )

        outcome = _attempt_rctf_submit(
            challenge=challenge,
            flag="flag{demo}",
            base_url="https://rctf.local",
            auth_mode="team_token",
            secret="bad",
        )

    assert outcome.normalized_verdict == "error"
    assert outcome.verified is False
    assert "authentication failed" in outcome.details
