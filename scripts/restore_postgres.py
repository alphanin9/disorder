from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore a Docker Compose Postgres database from a pg_dump custom-format backup."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a .dump file. Omit only when using --latest.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Restore the newest backup from the output directory.",
    )
    parser.add_argument(
        "--backup-dir",
        default="backups/postgres",
        help="Directory containing backup files for --latest. Default: backups/postgres",
    )
    parser.add_argument(
        "--service",
        default="postgres",
        help="Docker Compose service name for Postgres. Default: postgres",
    )
    parser.add_argument(
        "--database",
        default="ctf_harness",
        help="Target database name. Default: ctf_harness",
    )
    parser.add_argument(
        "--user",
        default="ctf",
        help="Database user. Default: ctf",
    )
    parser.add_argument(
        "--compose-file",
        action="append",
        default=[],
        help="Optional docker compose file(s) to pass through. May be specified multiple times.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the target database before restoring.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Pass --clean --if-exists to pg_restore to remove existing objects first.",
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


def resolve_input_path(args: argparse.Namespace) -> Path:
    if args.latest:
        backup_dir = Path(args.backup_dir)
        candidates = sorted(backup_dir.glob("*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidates:
            raise SystemExit(f"no backup files found in {backup_dir}")
        return candidates[0]

    if not args.input:
        raise SystemExit("provide a backup path or use --latest")

    input_path = Path(args.input)
    if not input_path.exists() or not input_path.is_file():
        raise SystemExit(f"backup file not found: {input_path}")
    return input_path


def run_checked(command: list[str], *, stdin_handle=None) -> None:
    subprocess.run(command, stdin=stdin_handle, check=True)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def recreate_database(compose_prefix: list[str], service: str, user: str, database: str) -> None:
    quoted_database = quote_identifier(database)
    run_checked(
        [
            *compose_prefix,
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            user,
            "-d",
            "postgres",
            "-c",
            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);",
        ]
    )
    run_checked(
        [
            *compose_prefix,
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            user,
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {quoted_database};",
        ]
    )


def main() -> int:
    args = parse_args()
    ensure_docker_compose()

    input_path = resolve_input_path(args)
    compose_prefix = build_compose_prefix(args.compose_file)

    if args.recreate:
        recreate_database(
            compose_prefix=compose_prefix,
            service=args.service,
            user=args.user,
            database=args.database,
        )

    restore_cmd = [
        *compose_prefix,
        "exec",
        "-T",
        args.service,
        "pg_restore",
        "-U",
        args.user,
        "-d",
        args.database,
        "--no-owner",
        "--no-privileges",
    ]
    if args.clean:
        restore_cmd.extend(["--clean", "--if-exists"])

    with input_path.open("rb") as handle:
        run_checked(restore_cmd, stdin_handle=handle)

    print(f"restored {input_path} -> {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
