from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

# Response "kind" values returned by rCTF when the bearer/auth token is missing
# or invalid. Hitting one of these means the short-lived authToken should be
# refreshed by logging in again with the long-lived team token.
_AUTH_FAILURE_KINDS = {"badToken", "badZeroAuth"}

# "kind"/status combinations that mean the requested API version is not served
# by this instance. Used to fall back from the richer v2 challenge API to v1
# during auto-negotiation (older rCTF deployments only expose ``/api/v1``).
_MISSING_ENDPOINT_KINDS = {"badEndpoint", "badVersion", "badNotFound"}

# Successful challenge-list "kind" per API version. The otter-sec rCTF v2 fork
# returns ``goodChallengesV2`` from ``GET /api/v2/challs`` with extra metadata
# (per-file size, tags, instancer info, scoringKind, hasFlag, ...); classic v1
# returns ``goodChallenges`` from ``GET /api/v1/challs``.
_CHALLENGES_OK = {"v1": "goodChallenges", "v2": "goodChallengesV2"}


@dataclass(slots=True)
class RCTFInstancer:
    """On-demand challenge instance ("instancer") metadata, exposed by rCTF v2.

    Only populated for challenges that actually have a deployable instance
    (a non-null ``instancerLifetime`` or one or more ``instancerActions``).
    """

    lifetime_ms: int | None = None
    extendable: bool = False
    stoppable: bool = False
    actions: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class RCTFChallengeSummary:
    challenge_id: str
    name: str
    category: str
    points: int
    # v2 enrichments. They default to v1-safe values so callers that only read
    # the original four fields keep working against either API version.
    solves: int = 0
    tags: list[str] = field(default_factory=list)
    scoring_kind: str | None = None
    has_flag: bool = True
    instancer: RCTFInstancer | None = None


class RCTFAuthError(RuntimeError):
    """Raised when rCTF team-token login fails or the event blocks access."""


def challenge_metadata(summary: RCTFChallengeSummary) -> dict:
    """Flatten the v2 enrichments of a summary into a JSON-serializable dict.

    Used by the sync service to persist rCTF v2 metadata onto the challenge
    manifest without leaking adapter dataclasses into the storage layer.
    """
    meta: dict = {
        "solves": summary.solves,
        "tags": list(summary.tags),
        "scoring_kind": summary.scoring_kind,
        "has_flag": summary.has_flag,
    }
    if summary.instancer is not None:
        meta["instancer"] = {
            "lifetime_ms": summary.instancer.lifetime_ms,
            "extendable": summary.instancer.extendable,
            "stoppable": summary.instancer.stoppable,
            "actions": summary.instancer.actions,
        }
    return meta


class RCTFClient:
    """Client for the otter-sec rCTF API (v1 and the newer v2 challenge API).

    rCTF (unlike CTFd) authenticates with a single long-lived *team token* that
    is exchanged for a short-lived bearer ``authToken`` via
    ``POST /api/v1/auth/login``. All other endpoints take
    ``Authorization: Bearer <authToken>``.

    The challenge list endpoint already returns full challenge objects including
    ``description`` and ``files``, so there is no per-challenge detail request --
    :meth:`get_challenge` serves entries cached during :meth:`list_challenges`.

    ``api_version`` selects the challenge API:

    * ``"auto"`` (default) -- try ``/api/v2/challs`` first and transparently
      fall back to ``/api/v1/challs`` on instances that do not serve v2.
    * ``"v2"`` -- require the v2 challenge API.
    * ``"v1"`` -- use only the classic v1 challenge API.

    Auth (login) and flag submission always use the stable ``/api/v1`` routes;
    rCTF v2 does not expose v2 variants of those.
    """

    def __init__(
        self,
        base_url: str,
        team_token: str,
        timeout: float = 30.0,
        *,
        api_version: str = "auto",
        file_timeout: float = 300.0,
    ) -> None:
        if not team_token:
            raise ValueError("RCTFClient requires a team_token")
        if api_version not in {"auto", "v1", "v2"}:
            raise ValueError("api_version must be 'auto', 'v1', or 'v2'")
        self.base_url = base_url.rstrip("/")
        self.team_token = team_token
        self.timeout = timeout
        # Artifact downloads can be large (rCTF v2 reports per-file sizes well
        # into the tens of MB), so give them a more generous read budget.
        self.file_timeout = file_timeout
        self.api_version = api_version
        # The version that actually served the last list_challenges() call.
        self.negotiated_version: str | None = None
        self._auth_token: str | None = None
        self._challenge_cache: dict[str, dict] = {}
        self._client = httpx.Client(timeout=self.timeout)

    def close(self) -> None:
        self._client.close()

    # -- HTTP plumbing ---------------------------------------------------
    def _api(self, path: str, version: str = "v1") -> str:
        return f"{self.base_url}/api/{version}{path}"

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

    def _authed_json(
        self,
        method: str,
        path: str,
        *,
        version: str = "v1",
        json: dict | None = None,
        _retry: bool = True,
    ) -> dict:
        headers = {"Authorization": f"Bearer {self._ensure_auth_token()}"}
        response = self._client.request(
            method, self._api(path, version), json=json, headers=headers
        )
        payload = self._payload(response)
        kind = str(payload.get("kind") or "")
        if _retry and (response.status_code == 401 or kind in _AUTH_FAILURE_KINDS):
            # authToken likely expired -- re-login once and retry.
            self._auth_token = None
            return self._authed_json(
                method, path, version=version, json=json, _retry=False
            )
        return payload

    # -- public API ------------------------------------------------------
    def list_challenges(self) -> list[RCTFChallengeSummary]:
        order = {"v1": ["v1"], "v2": ["v2"]}.get(self.api_version, ["v2", "v1"])
        errors: list[str] = []
        for version in order:
            payload = self._authed_json("GET", "/challs", version=version)
            kind = str(payload.get("kind") or "")
            if kind == "badNotStarted":
                # The event gate is version-independent; surface it immediately.
                raise RCTFAuthError(
                    str(payload.get("message") or "rCTF event has not started yet.")
                )
            if kind == _CHALLENGES_OK[version]:
                self.negotiated_version = version
                return self._parse_challenges(payload.get("data") or [], version)
            # Not a success for this version. In "auto" mode this lets us fall
            # through to the next candidate version (v2 -> v1).
            errors.append(str(payload.get("message") or kind or "unknown"))
        raise RCTFAuthError(
            f"rCTF challenge list failed ({'; '.join(errors) or 'unknown'})."
        )

    def _parse_challenges(self, entries: object, version: str) -> list[RCTFChallengeSummary]:
        summaries: list[RCTFChallengeSummary] = []
        self._challenge_cache = {}
        if not isinstance(entries, list):
            return summaries
        for item in entries:
            if not isinstance(item, dict):
                continue
            challenge_id = str(item.get("id") or "")
            if not challenge_id:
                continue
            self._challenge_cache[challenge_id] = item
            summaries.append(self._summarize(item, version))
        return summaries

    def _summarize(self, item: dict, version: str) -> RCTFChallengeSummary:
        summary = RCTFChallengeSummary(
            challenge_id=str(item.get("id") or ""),
            name=str(item.get("name") or ""),
            category=str(item.get("category") or "misc"),
            points=int(item.get("points") or 0),
            solves=int(item.get("solves") or 0),
        )
        if version == "v2":
            tags = item.get("tags")
            summary.tags = [str(t) for t in tags] if isinstance(tags, list) else []
            scoring = item.get("scoringKind")
            summary.scoring_kind = str(scoring) if scoring else None
            summary.has_flag = bool(item.get("hasFlag", True))
            summary.instancer = self._parse_instancer(item)
        return summary

    @staticmethod
    def _parse_instancer(item: dict) -> RCTFInstancer | None:
        lifetime = item.get("instancerLifetime")
        raw_actions = item.get("instancerActions")
        actions = (
            [a for a in raw_actions if isinstance(a, dict)]
            if isinstance(raw_actions, list)
            else []
        )
        # Static challenges still carry instancer* keys (lifetime null, no
        # actions); only treat a challenge as having an instancer when it can
        # actually be spun up.
        if lifetime is None and not actions:
            return None
        return RCTFInstancer(
            lifetime_ms=int(lifetime) if isinstance(lifetime, (int, float)) else None,
            extendable=bool(item.get("instancerExtendable")),
            stoppable=bool(item.get("instancerStoppable")),
            actions=actions,
        )

    def get_challenge(self, challenge_id: str) -> dict:
        challenge_id = str(challenge_id)
        if challenge_id in self._challenge_cache:
            return self._challenge_cache[challenge_id]
        # Cache miss (e.g. a submit-only client): refresh the list once.
        self.list_challenges()
        return self._challenge_cache.get(challenge_id, {})

    def download_file(self, file_url: str) -> bytes:
        resolved = urljoin(f"{self.base_url}/", file_url)
        headers: dict[str, str] = {}
        # Only forward the rCTF bearer to same-origin uploads (in case the
        # instance gates downloads). rCTF v2 frequently serves artifacts from
        # external object storage (e.g. Google Cloud Storage), which rejects an
        # unexpected Authorization header with HTTP 401.
        if self._auth_token and urlparse(resolved).netloc == urlparse(self.base_url).netloc:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        response = self._client.get(resolved, headers=headers, timeout=self.file_timeout)
        response.raise_for_status()
        return response.content

    def submit_flag(self, challenge_id: str, submission: str) -> dict:
        # Flag submission is only served by the stable v1 route, even on rCTF v2.
        return self._authed_json(
            "POST", f"/challs/{challenge_id}/submit", json={"flag": submission}
        )
