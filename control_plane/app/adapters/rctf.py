from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

# Response "kind" values returned by rCTF when the bearer/auth token is missing
# or invalid. Hitting one of these means the short-lived authToken should be
# refreshed by logging in again with the long-lived team token.
_AUTH_FAILURE_KINDS = {"badToken", "badZeroAuth"}


@dataclass(slots=True)
class RCTFChallengeSummary:
    challenge_id: str
    name: str
    category: str
    points: int


class RCTFAuthError(RuntimeError):
    """Raised when rCTF team-token login fails or the event blocks access."""


class RCTFClient:
    """Minimal client for the otter-sec rCTF API.

    rCTF (unlike CTFd) authenticates with a single long-lived *team token* that
    is exchanged for a short-lived bearer ``authToken`` via
    ``POST /api/v1/auth/login``. All other endpoints take
    ``Authorization: Bearer <authToken>``.

    The challenge list endpoint (``GET /api/v1/challs``) already returns full
    challenge objects including ``description`` and ``files``, so there is no
    per-challenge detail request -- :meth:`get_challenge` serves entries cached
    during :meth:`list_challenges`.
    """

    def __init__(self, base_url: str, team_token: str, timeout: float = 30.0) -> None:
        if not team_token:
            raise ValueError("RCTFClient requires a team_token")
        self.base_url = base_url.rstrip("/")
        self.team_token = team_token
        self.timeout = timeout
        self._auth_token: str | None = None
        self._challenge_cache = {}
        self._client = httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        self._client.close()

    # -- HTTP plumbing ---------------------------------------------------
    def _api(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    @staticmethod
    def _payload(response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            # Surface a transport error for non-JSON 4xx/5xx; otherwise raise auth error.
            response.raise_for_status()
            raise RCTFAuthError("rCTF returned a non-JSON response") from exc
        if isinstance(data, dict):
            return data
        return {"kind": "unknown", "data": data}

    def _ensure_auth_token(self) -> str:
        return self._auth_token or self.login()

    def login(self) -> str:
        response = self._client.post(
            self._api("/auth/login"), json={"teamToken": self.team_token}
        )
        payload = self._payload(response)
        kind = str(payload.get("kind") or "")
        if kind != "goodLogin":
            message = str(payload.get("message") or kind or "rCTF login failed")
            raise RCTFAuthError(message)
        data = payload.get("data") or {}
        token = str(data.get("authToken") or "") if isinstance(data, dict) else ""
        if not token:
            raise RCTFAuthError("rCTF login succeeded but returned no authToken")
        self._auth_token = token
        return token

    def _authed_json(self, method: str, path: str, *, json: dict | None = None, _retry: bool = True) -> dict:
        headers = {"Authorization": f"Bearer {self._ensure_auth_token()}"}
        response = self._client.request(method, self._api(path), json=json, headers=headers)
        payload = self._payload(response)
        kind = str(payload.get("kind") or "")
        if _retry and (response.status_code == 401 or kind in _AUTH_FAILURE_KINDS):
            # authToken likely expired -- re-login once and retry.
            self._auth_token = None
            return self._authed_json(method, path, json=json, _retry=False)
        return payload

    # -- public API ------------------------------------------------------
    def list_challenges(self) -> list[RCTFChallengeSummary]:
        payload = self._authed_json("GET", "/challs")
        kind = str(payload.get("kind") or "")
        if kind == "badNotStarted":
            raise RCTFAuthError(
                str(payload.get("message") or "rCTF event has not started yet.")
            )
        if kind != "goodChallenges":
            raise RCTFAuthError(
                str(payload.get("message") or f"rCTF challenge list failed ({kind or 'unknown'}).")
            )

        entries = payload.get("data") or []
        summaries: list[RCTFChallengeSummary] = []
        self._challenge_cache = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            challenge_id = str(item.get("id") or "")
            if not challenge_id:
                continue
            self._challenge_cache[challenge_id] = item
            summaries.append(
                RCTFChallengeSummary(
                    challenge_id=challenge_id,
                    name=str(item.get("name") or ""),
                    category=str(item.get("category") or "misc"),
                    points=int(item.get("points") or 0),
                )
            )
        return summaries

    def get_challenge(self, challenge_id: str) -> dict:
        challenge_id = str(challenge_id)
        if challenge_id in self._challenge_cache:
            return self._challenge_cache[challenge_id]
        # Cache miss (e.g. a submit-only client): refresh the list once.
        self.list_challenges()
        return self._challenge_cache.get(challenge_id, {})

    def download_file(self, file_url: str) -> bytes:
        resolved = urljoin(f"{self.base_url}/", file_url)
        # Uploads live outside /api/v1 and are usually public, but include the
        # bearer in case the instance gates downloads.
        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        response = self._client.get(resolved, headers=headers)
        response.raise_for_status()
        return response.content

    def submit_flag(self, challenge_id: str, submission: str) -> dict:
        return self._authed_json(
            "POST", f"/challs/{challenge_id}/submit", json={"flag": submission}
        )
