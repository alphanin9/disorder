from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a logical backup of the Docker Compose Postgres database with pg_dump."
    )
    parser.add_argument(
        "--output-dir",
        default="backups/postgres",
        help="Directory for backup files. Default: backups/postgres",
    )
    parser.add_argument(
        "--service",
        default="postgres",
        help="Docker Compose service name for Postgres. Default: postgres",
    )
    parser.add_argument(
        "--database",
        default="ctf_harness",
        help="Database name passed to pg_dump. Default: ctf_harness",
    )
    parser.add_argument(
        "--user",
        default="ctf",
        help="Database user passed to pg_dump. Default: ctf",
    )
    parser.add_argument(
        "--compose-file",
        action="append",
        default=[],
        help="Optional docker compose file(s) to pass through. May be specified multiple times.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Keep the most recent N backups in the output directory. Default: 7. Use 0 to disable pruning.",
    )
    return parser.parse_args()


def build_compose_prefix(compose_files: list[str]) -> list[str]:
    prefix = ["docker", "compose"]
    for compose_file in compose_files:
        prefix.extend(["-f", compose_file])
    return prefix


def ensure_docker_compose() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("docker is not installed or not in PATH")


def prune_backups(output_dir: Path, keep: int) -> None:
    if keep <= 0:
        return

    backups = sorted(output_dir.glob("*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
    for stale_backup in backups[keep:]:
        stale_backup.unlink()


def main() -> int:
    args = parse_args()
    ensure_docker_compose()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{args.database}_{timestamp}.dump"
    final_path = output_dir / backup_name
    temp_path = final_path.with_suffix(".dump.tmp")

    compose_prefix = build_compose_prefix(args.compose_file)
    dump_cmd = [
        *compose_prefix,
        "exec",
        "-T",
        args.service,
        "pg_dump",
        "-U",
        args.user,
        "-d",
        args.database,
        "-Fc",
    ]

    try:
        with temp_path.open("wb") as handle:
            subprocess.run(dump_cmd, stdout=handle, check=True)
        temp_path.replace(final_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    prune_backups(output_dir=output_dir, keep=args.keep)
    print(final_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
