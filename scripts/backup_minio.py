from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import BaseClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a filesystem snapshot of a MinIO bucket.")
    parser.add_argument("--output-dir", default="backups/minio", help="Backup root directory. Default: backups/minio")
    parser.add_argument("--endpoint", default="http://localhost:9000", help="MinIO/S3 endpoint URL. Default: http://localhost:9000")
    parser.add_argument("--access-key", default="minio", help="Access key. Default: minio")
    parser.add_argument("--secret-key", default="minio123", help="Secret key. Default: minio123")
    parser.add_argument("--region", default="us-east-1", help="Region name. Default: us-east-1")
    parser.add_argument("--bucket", default="ctf-harness", help="Bucket name. Default: ctf-harness")
    parser.add_argument("--prefix", default="", help="Optional key prefix filter.")
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Keep the most recent N snapshots for this bucket. Default: 7. Use 0 to disable pruning.",
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


def encode_key_path(key: str) -> str:
    return quote(key, safe="/._-")


def prune_snapshots(output_dir: Path, bucket: str, keep: int) -> None:
    if keep <= 0:
        return

    snapshots = sorted(
        [path for path in output_dir.glob(f"{bucket}_*") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale_snapshot in snapshots[keep:]:
        shutil.rmtree(stale_snapshot, ignore_errors=True)


def head_to_manifest_entry(key: str, path_rel: str, head: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "path": path_rel,
        "size": int(head.get("ContentLength") or 0),
        "etag": str(head.get("ETag") or "").strip('"'),
        "content_type": str(head.get("ContentType") or "application/octet-stream"),
        "metadata": dict(head.get("Metadata") or {}),
        "cache_control": head.get("CacheControl"),
        "content_disposition": head.get("ContentDisposition"),
        "content_encoding": head.get("ContentEncoding"),
        "content_language": head.get("ContentLanguage"),
    }


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = output_dir / f"{args.bucket}_{timestamp}"
    objects_dir = snapshot_dir / "objects"
    objects_dir.mkdir(parents=True, exist_ok=True)

    client = build_client(args)
    paginator = client.get_paginator("list_objects_v2")

    manifest_objects: list[dict[str, Any]] = []
    total_bytes = 0

    for page in paginator.paginate(Bucket=args.bucket, Prefix=args.prefix):
        for item in page.get("Contents") or []:
            key = str(item.get("Key") or "")
            if not key:
                continue

            path_rel = encode_key_path(key)
            destination = objects_dir / Path(*path_rel.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)

            client.download_file(args.bucket, key, str(destination))
            head = client.head_object(Bucket=args.bucket, Key=key)
            entry = head_to_manifest_entry(key=key, path_rel=path_rel, head=head)
            manifest_objects.append(entry)
            total_bytes += int(entry["size"])

    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "bucket": args.bucket,
        "prefix": args.prefix,
        "object_count": len(manifest_objects),
        "total_bytes": total_bytes,
        "objects": manifest_objects,
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    prune_snapshots(output_dir=output_dir, bucket=args.bucket, keep=args.keep)
    print(snapshot_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
