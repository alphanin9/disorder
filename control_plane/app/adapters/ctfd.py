from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

URL_RE = re.compile(r"https?://[^\s\]\)>'\"`]+")
NC_RE = re.compile(r"\bnc\s+([A-Za-z0-9._-]+)\s+(\d{1,5})\b")
TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
CSRF_NONCE_BOOTSTRAP_RE = re.compile(r"""['"]csrfNonce['"]\s*:\s*['"](?P<token>[^'"]+)['"]""")
CSRF_META_RE = re.compile(r"""<meta[^>]+name=['"]csrf-token['"][^>]+content=['"](?P<token>[^'"]+)['"]""", re.IGNORECASE)


@dataclass(slots=True)
class CTFdChallengeSummary:
    challenge_id: str
    name: str
    category: str
    points: int


class CTFdClient:
    def __init__(
        self,
        base_url: str,
        api_token: str | None = None,
        session_cookie: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.session_cookie = session_cookie
        self.timeout = timeout
        headers: dict[str, str] = {}
        self._csrf_nonce: str | None = None

        if self.api_token:
            headers["Authorization"] = f"Token {self.api_token}"
        elif self.session_cookie:
            headers["Cookie"] = _normalize_session_cookie(self.session_cookie)
        else:
            raise ValueError("CTFdClient requires either api_token or session_cookie")

        self._client = httpx.Client(
            timeout=self.timeout,
            headers=headers,
        )

    def close(self) -> None:
        self._client.close()

    def list_challenges(self) -> list[CTFdChallengeSummary]:
        response = self._client.get(f"{self.base_url}/api/v1/challenges")
        response.raise_for_status()
        payload = response.json()
        entries = payload.get("data", [])
        summaries: list[CTFdChallengeSummary] = []
        for item in entries:
            summaries.append(
                CTFdChallengeSummary(
                    challenge_id=str(item.get("id")),
                    name=str(item.get("name", "")),
                    category=str(item.get("category", "misc")),
                    points=int(item.get("value") or item.get("points") or 0),
                )
            )
        return summaries

    def get_challenge(self, challenge_id: str) -> dict:
        response = self._client.get(f"{self.base_url}/api/v1/challenges/{challenge_id}")
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", {})

    def download_file(self, file_url: str) -> bytes:
        resolved = urljoin(f"{self.base_url}/", file_url)
        response = self._client.get(resolved)
        response.raise_for_status()
        return response.content

    def submit_flag(self, challenge_id: str, submission: str) -> dict:
        headers: dict[str, str] | None = None
        if self.session_cookie:
            headers = self._session_csrf_headers()

        response = self._client.post(
            f"{self.base_url}/api/v1/challenges/attempt",
            json={"challenge_id": challenge_id, "submission": submission},
            headers=headers,
        )
        if self.session_cookie and response.status_code in {400, 403} and _looks_like_csrf_failure(response):
            self._csrf_nonce = None
            response = self._client.post(
                f"{self.base_url}/api/v1/challenges/attempt",
                json={"challenge_id": challenge_id, "submission": submission},
                headers=self._session_csrf_headers(),
            )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return {"status": "unknown", "raw": data}

    def _session_csrf_headers(self) -> dict[str, str]:
        nonce = self._ensure_csrf_nonce()
        parsed = urlparse(self.base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else self.base_url
        referer = f"{self.base_url}/"
        return {
            "CSRF-Token": nonce,
            "X-CSRF-Token": nonce,
            "Origin": origin,
            "Referer": referer,
        }

    def _ensure_csrf_nonce(self) -> str:
        if self.api_token:
            raise ValueError("CSRF nonce should not be requested for API token auth")
        if self._csrf_nonce:
            return self._csrf_nonce

        response = self._client.get(f"{self.base_url}/")
        location = (response.headers.get("location") or "").lower()
        if response.status_code in {301, 302, 303, 307, 308} and "/login" in location:
            raise httpx.HTTPStatusError("CTFd session redirected to login", request=response.request, response=response)
        response.raise_for_status()

        nonce = _extract_csrf_nonce_from_response(response)
        if not nonce:
            raise ValueError("Unable to extract CTFd CSRF nonce from HTML bootstrap")
        self._csrf_nonce = nonce
        return nonce


def _normalize_session_cookie(cookie_value: str) -> str:
    raw = cookie_value.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw[7:].strip()
    if "=" in raw:
        return raw
    return f"session={raw}"


def _extract_csrf_nonce_from_response(response: httpx.Response) -> str | None:
    cookie_candidates = ["csrf_token", "csrf", "nonce"]
    for name in cookie_candidates:
        try:
            cookie_value = response.cookies.get(name)
        except Exception:
            cookie_value = None
        if cookie_value:
            return str(cookie_value)

    body = response.text
    bootstrap_match = CSRF_NONCE_BOOTSTRAP_RE.search(body)
    if bootstrap_match:
        token = bootstrap_match.group("token").strip()
        if token:
            return token

    meta_match = CSRF_META_RE.search(body)
    if meta_match:
        token = meta_match.group("token").strip()
        if token:
            return token
    return None


def _looks_like_csrf_failure(response: httpx.Response) -> bool:
    body = ""
    try:
        body = response.text.lower()
    except Exception:
        body = ""
    if "csrf" in body or "nonce" in body:
        return True
    return False


def normalize_description(raw_description: str | None) -> str:
    raw = raw_description or ""
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    normalized = html.unescape(normalized)
    normalized = BR_RE.sub("\n", normalized)
    normalized = TAG_RE.sub("", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n")).strip()
    return normalized


def parse_remote_endpoints(text: str) -> list[dict]:
    endpoints: list[dict] = []
    seen: set[tuple] = set()

    for match in NC_RE.finditer(text):
        host = match.group(1)
        port = int(match.group(2))
        key = ("nc", host, port)
        if key in seen:
            continue
        endpoints.append({"type": "nc", "host": host, "port": port})
        seen.add(key)

    for raw_url in URL_RE.findall(text):
        parsed = urlparse(raw_url)
        host = parsed.hostname or ""
        port = parsed.port
        key = ("http", raw_url)
        if key in seen:
            continue
        endpoint = {"type": "http", "url": raw_url, "host": host}
        if port is not None:
            endpoint["port"] = port
        endpoints.append(endpoint)
        seen.add(key)

    return endpoints


def extract_file_entries(challenge_payload: dict) -> list[dict]:
    raw_files = challenge_payload.get("files") or []
    entries: list[dict] = []

    for file_entry in raw_files:
        if isinstance(file_entry, str):
            file_url = file_entry
            file_name = file_url.split("/")[-1] or "artifact.bin"
            entries.append({"name": file_name, "url": file_url})
            continue

        if not isinstance(file_entry, dict):
            continue

        file_url = str(
            file_entry.get("url")
            or file_entry.get("location")
            or file_entry.get("path")
            or ""
        )
        if not file_url:
            continue
        file_name = str(
            file_entry.get("name") or file_url.split("/")[-1] or "artifact.bin"
        )
        entries.append({"name": file_name, "url": file_url})

    return entries
