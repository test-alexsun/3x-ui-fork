"""CLI entrypoint for system orchestration and bounded data operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api_client import ApiClient, ApiError
from .backup_manager import (
    BackupError,
    postgres_backup,
    restore_postgres_to_empty_db,
    restore_sqlite_to_new_file,
    sqlite_backup,
    verify,
)
from .compatibility import load_capabilities
from .diagnostics import panel_summary
from .installer import InstallationNotReady, install_clean
from .lifecycle import _state, repair_owned, rollback_uninstall, uninstall_owned
from .planner import Paths, plan
from .preflight import collect
from .updater import rollback_update, update_owned


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="3x-ui-fork")
    sub = p.add_subparsers(dest="mode", required=True)
    for mode in ("check", "status", "dry-run"):
        command = sub.add_parser(mode)
        command.add_argument("--domain")
        command.add_argument("--api", action="store_true", help="read existing bearer credentials from env")
        if mode == "dry-run":
            command.add_argument("--action", choices=("install", "update", "repair", "uninstall"),
                                 default="install")
            command.add_argument("--panel-port", type=int, default=2053)
    backup = sub.add_parser("backup")
    backup.add_argument("--backend", choices=("sqlite", "postgres"), required=True)
    backup.add_argument("--source", type=Path, help="SQLite database path")
    backup.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("--backup", type=Path, required=True)
    target = restore.add_mutually_exclusive_group(required=True)
    target.add_argument("--to-new-file", type=Path)
    target.add_argument("--to-empty-postgres")
    install = sub.add_parser("install")
    install.add_argument("--panel-port", type=int, default=2053)
    sub.add_parser("update")
    sub.add_parser("repair")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--restore-data", action="store_true")
    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--confirm-uninstall", action="store_true")
    return p


def run(args: argparse.Namespace) -> dict:
    if args.mode == "dry-run":
        return plan(args.action, domain=args.domain, panel_port=args.panel_port)
    if args.mode in ("check", "status"):
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
    if args.mode == "install":
        return install_clean(panel_port=args.panel_port)
    if args.mode == "update":
        return update_owned()
    if args.mode == "repair":
        return repair_owned()
    if args.mode == "rollback":
        if _state(Paths()).get("status") == "uninstalled":
            return rollback_uninstall()
        return rollback_update(restore_data=args.restore_data)
    if args.mode == "uninstall":
        return uninstall_owned(confirmed=args.confirm_uninstall)
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
