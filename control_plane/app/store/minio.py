from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from control_plane.app.core.config import get_settings


class MinioBlobStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self._client: BaseClient = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name=settings.minio_region,
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self._client.create_bucket(Bucket=self.bucket)

    def put_bytes(self, object_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._client.put_object(Bucket=self.bucket, Key=object_key, Body=data, ContentType=content_type)

    def put_json(self, object_key: str, payload: str) -> None:
        self.put_bytes(object_key=object_key, data=payload.encode("utf-8"), content_type="application/json")

    def put_file(self, object_key: str, source: Path) -> None:
        guessed_type, _ = mimetypes.guess_type(source.name)
        extra_args = {"ContentType": guessed_type or "application/octet-stream"}
        self._client.upload_file(str(source), self.bucket, object_key, ExtraArgs=extra_args)

    def download_file(self, object_key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self.bucket, object_key, str(destination))

    def get_bytes(self, object_key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=object_key)
        return response["Body"].read()

    def object_exists(self, object_key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except ClientError:
            return False


def artifact_object_key(platform: str, challenge_id: str, file_name: str, sha256_hex: str) -> str:
    safe_name = file_name.replace(" ", "_")
    return f"artifacts/{platform}/{challenge_id}/{sha256_hex}/{safe_name}"


def run_result_object_keys(run_id: str) -> tuple[str, str]:
    return (f"runs/{run_id}/result.json", f"runs/{run_id}/logs.txt")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
