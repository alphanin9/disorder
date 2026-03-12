from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore a MinIO bucket snapshot created by backup_minio.py.")
    parser.add_argument("input", nargs="?", help="Snapshot directory path. Omit only when using --latest.")
    parser.add_argument("--latest", action="store_true", help="Restore the newest snapshot from the backup directory.")
    parser.add_argument("--backup-dir", default="backups/minio", help="Snapshot root directory for --latest.")
    parser.add_argument("--endpoint", default="http://localhost:9000", help="MinIO/S3 endpoint URL. Default: http://localhost:9000")
    parser.add_argument("--access-key", default="minio", help="Access key. Default: minio")
    parser.add_argument("--secret-key", default="minio123", help="Secret key. Default: minio123")
    parser.add_argument("--region", default="us-east-1", help="Region name. Default: us-east-1")
    parser.add_argument("--bucket", default=None, help="Optional target bucket override. Defaults to manifest bucket.")
    parser.add_argument("--target-prefix", default="", help="Optional prefix prepended to restored object keys.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing objects in the target bucket under the target prefix before restore.",
    )
    return parser.parse_args()


def build_client(args: argparse.Namespace) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=args.endpoint,
        aws_access_key_id=args.access_key,
        aws_secret_access_key=args.secret_key,
        region_name=args.region,
    )


def resolve_snapshot_path(args: argparse.Namespace) -> Path:
    if args.latest:
        backup_dir = Path(args.backup_dir)
        if not backup_dir.exists() or not backup_dir.is_dir():
            raise SystemExit(f"backup directory not found: {backup_dir}")
        candidates = sorted(
            [manifest.parent for manifest in backup_dir.glob("*/manifest.json")],
            key=lambda path: (path / "manifest.json").stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise SystemExit(f"no MinIO snapshots found in {backup_dir}")
        return candidates[0]

    if not args.input:
        raise SystemExit("provide a snapshot directory or use --latest")

    snapshot_dir = Path(args.input)
    if not snapshot_dir.is_dir() or not (snapshot_dir / "manifest.json").exists():
        raise SystemExit(f"snapshot directory not found or missing manifest.json: {snapshot_dir}")
    return snapshot_dir


def ensure_bucket(client: BaseClient, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        error_code = str(exc.response.get("Error", {}).get("Code") or "")
        if error_code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        client.create_bucket(Bucket=bucket)


def delete_prefix(client: BaseClient, bucket: str, prefix: str) -> None:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        contents = page.get("Contents") or []
        for index in range(0, len(contents), 1000):
            batch = contents[index : index + 1000]
            objects = [{"Key": str(item.get("Key"))} for item in batch if item.get("Key")]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})


def normalize_target_key(prefix: str, key: str) -> str:
    clean_prefix = prefix.strip("/")
    if not clean_prefix:
        return key
    return f"{clean_prefix}/{key.lstrip('/')}"


def upload_from_manifest(
    client: BaseClient,
    *,
    snapshot_dir: Path,
    manifest_entry: dict[str, Any],
    bucket: str,
    target_prefix: str,
) -> None:
    source_path = snapshot_dir / "objects" / Path(*str(manifest_entry["path"]).split("/"))
    if not source_path.exists():
        raise FileNotFoundError(f"missing backup file for object {manifest_entry['key']}: {source_path}")

    target_key = normalize_target_key(target_prefix, str(manifest_entry["key"]))
    extra: dict[str, Any] = {
        "ContentType": str(manifest_entry.get("content_type") or "application/octet-stream"),
    }
    metadata = manifest_entry.get("metadata")
    if isinstance(metadata, dict) and metadata:
        extra["Metadata"] = {str(key): str(value) for key, value in metadata.items()}
    for field_name, manifest_key in (
        ("CacheControl", "cache_control"),
        ("ContentDisposition", "content_disposition"),
        ("ContentEncoding", "content_encoding"),
        ("ContentLanguage", "content_language"),
    ):
        value = manifest_entry.get(manifest_key)
        if value:
            extra[field_name] = str(value)

    client.upload_file(str(source_path), bucket, target_key, ExtraArgs=extra)


def main() -> int:
    args = parse_args()
    snapshot_dir = resolve_snapshot_path(args)
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))

    target_bucket = str(args.bucket or manifest["bucket"])
    target_prefix = str(args.target_prefix or "")
    client = build_client(args)
    ensure_bucket(client, target_bucket)

    if args.clear:
        delete_prefix(client, target_bucket, target_prefix.strip("/"))

    for entry in manifest.get("objects") or []:
        upload_from_manifest(
            client,
            snapshot_dir=snapshot_dir,
            manifest_entry=entry,
            bucket=target_bucket,
            target_prefix=target_prefix,
        )

    print(f"restored {snapshot_dir} -> bucket={target_bucket} prefix={target_prefix or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
