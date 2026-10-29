"""CLI entrypoint. Mutating system modes intentionally fail closed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api_client import ApiClient, ApiError
from .backup_manager import (BackupError, postgres_backup, restore_postgres_to_empty_db,
                             restore_sqlite_to_new_file, sqlite_backup, verify)
from .compatibility import load_capabilities
from .diagnostics import panel_summary
from .installer import InstallationNotReady, require_release_artifacts
from .preflight import collect


MUTATING_MODES = ("install", "update", "repair", "rollback", "uninstall")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="3x-ui-fork")
    sub = p.add_subparsers(dest="mode", required=True)
    for mode in ("check", "status", "dry-run"):
        command = sub.add_parser(mode)
        command.add_argument("--domain")
        command.add_argument("--api", action="store_true", help="read existing bearer credentials from env")
    backup = sub.add_parser("backup")
    backup.add_argument("--backend", choices=("sqlite", "postgres"), required=True)
    backup.add_argument("--source", type=Path, help="SQLite database path")
    backup.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    target = restore.add_mutually_exclusive_group(required=True)
    target.add_argument("--to-new-file", type=Path)
    target.add_argument("--to-empty-postgres")
    for mode in MUTATING_MODES:
        sub.add_parser(mode)
    return p


def run(args: argparse.Namespace) -> dict:
    if args.mode in ("check", "status", "dry-run"):
        if args.mode == "dry-run":
            raise InstallationNotReady("dry-run requires a concrete desired-state schema and planner")
        result = {"preflight": collect(args.domain), "capabilities": load_capabilities()}
        if args.api:
            result["panel"] = panel_summary(ApiClient.from_env())
        return result
    if args.mode == "backup":
        if args.backend == "sqlite":
            if args.source is None:
                raise BackupError("--source is required for SQLite")
            folder = sqlite_backup(args.source, args.output)
        else:
            folder = postgres_backup(args.output)
        return {"backup": str(folder), "manifest": verify(folder),
                "warning": "backup contains secrets; store it in an encrypted volume"}
    if args.mode == "restore":
        if args.to_new_file:
            path = restore_sqlite_to_new_file(args.backup, args.to_new_file)
            return {"restored_to_new_file": str(path)}
        database = restore_postgres_to_empty_db(args.backup, args.to_empty_postgres)
        return {"restored_to_empty_postgres": database}
    require_release_artifacts()
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
        return 0
    except (ApiError, BackupError, InstallationNotReady, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
