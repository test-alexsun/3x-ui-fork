"""CLI entrypoint. Mutating system modes intentionally fail closed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api_client import ApiClient, ApiError
from .backup_manager import BackupError, postgres_backup, restore_sqlite_to_new_file, sqlite_backup, verify
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
    restore.add_argument("--to-new-file", type=Path, required=True)
    for mode in MUTATING_MODES:
        sub.add_parser(mode)
    return p


def run(args: argparse.Namespace) -> dict:
    if args.mode in ("check", "status", "dry-run"):
        result = {"preflight": collect(args.domain), "capabilities": load_capabilities()}
        if args.api:
            result["panel"] = panel_summary(ApiClient.from_env())
        if args.mode == "dry-run":
            result["plan"] = []
            result["ready_to_apply"] = False
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
        path = restore_sqlite_to_new_file(args.backup, args.to_new_file)
        return {"restored_to_new_file": str(path)}
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
