from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx


URL_RE = re.compile(r"https?://[^\s\]\)>'\"]+")
NC_RE = re.compile(r"\bnc\s+([A-Za-z0-9._-]+)\s+(\d{1,5})\b")
TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


@dataclass(slots=True)
class CTFdChallengeSummary:
    challenge_id: str
    name: str
    category: str
    points: int


class CTFdClient:
    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Authorization": f"Token {self.api_token}"},
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
        file_name = str(file_entry.get("name") or file_url.split("/")[-1] or "artifact.bin")
        entries.append({"name": file_name, "url": file_url})

    return entries
