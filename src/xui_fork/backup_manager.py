"""Consistent standalone DB snapshots. Restore only into a new destination."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class BackupError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _new_directory(root: Path) -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="xui-", dir=root))
    os.chmod(folder, 0o700)
    return folder


def sqlite_backup(source: Path, backup_root: Path) -> Path:
    if not source.is_file():
        raise BackupError("SQLite source does not exist")
    folder = _new_directory(backup_root)
    target = folder / "x-ui.db"
    try:
        # SQLite's online backup API includes committed WAL content.
        with closing(sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("snapshot integrity check failed")
        os.chmod(target, 0o600)
        _write_manifest(folder, target, "sqlite")
        return folder
    except Exception:
        target.unlink(missing_ok=True)
        (folder / "manifest.json").unlink(missing_ok=True)
        folder.rmdir()
        raise


def postgres_backup(backup_root: Path, dsn: str | None = None) -> Path:
    folder = _new_directory(backup_root)
    target = folder / "x-ui.dump"
    env = os.environ.copy()
    # PG* environment variables or a service file are preferred to argv secrets.
    if dsn is not None:
        env["PGSERVICE"] = dsn
    try:
        with target.open("wb") as output:
            proc = subprocess.run(["pg_dump", "--no-password", "--format=custom",
                                   "--no-owner", "--file=-"],
                                  env=env, stdout=output, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0 or target.stat().st_size == 0:
            raise BackupError(f"pg_dump failed (exit {proc.returncode})")
        subprocess.run(["pg_restore", "--list", str(target)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(target, 0o600)
        _write_manifest(folder, target, "postgres")
        return folder
    except Exception:
        target.unlink(missing_ok=True)
        (folder / "manifest.json").unlink(missing_ok=True)
        folder.rmdir()
        raise


def _write_manifest(folder: Path, target: Path, backend: str) -> None:
    manifest = {"schema": 1, "backend": backend, "created_utc":
                datetime.now(timezone.utc).isoformat(), "file": target.name,
                "size": target.stat().st_size, "sha256": sha256(target)}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def verify(folder: Path) -> dict:
    data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("backend") not in {"sqlite", "postgres"}:
        raise BackupError("unsupported manifest")
    filename = data.get("file")
    if filename not in {"x-ui.db", "x-ui.dump"}:
        raise BackupError("unsafe backup filename")
    target = folder / filename
    if not target.is_file() or target.is_symlink():
        raise BackupError("backup file missing or symlinked")
    if target.stat().st_size != data.get("size") or sha256(target) != data.get("sha256"):
        raise BackupError("backup checksum mismatch")
    return data


def restore_sqlite_to_new_file(folder: Path, destination: Path) -> Path:
    manifest = verify(folder)
    if manifest["backend"] != "sqlite":
        raise BackupError("SQLite backup required")
    if destination.exists() or destination.is_symlink():
        raise BackupError("destination already exists; live restore is forbidden")
    if not destination.parent.is_dir():
        raise BackupError("destination parent does not exist")
    source = folder / "x-ui.db"
    try:
        with closing(sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise BackupError("restored DB failed integrity check")
        os.chmod(destination, 0o600)
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def restore_postgres_to_empty_db(folder: Path, database: str) -> str:
    """Restore a custom archive into a pre-created, empty, dedicated database."""
    manifest = verify(folder)
    if manifest["backend"] != "postgres":
        raise BackupError("PostgreSQL backup required")
    if not database.startswith("xui_restore_") or not database.replace("_", "").isalnum():
        raise BackupError("destination must be a dedicated xui_restore_* database")
    env = os.environ.copy()
    if env.get("PGDATABASE") != database:
        raise BackupError("PGDATABASE must equal the explicit restore destination")
    probe = subprocess.run(
        ["psql", "--no-password", "--no-psqlrc", "--tuples-only", "--no-align", "--command",
         "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname NOT IN "
         "('pg_catalog','information_schema')"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "0":
        raise BackupError("PostgreSQL destination is not empty or unavailable")
    archive = folder / "x-ui.dump"
    result = subprocess.run(
        ["pg_restore", "--no-password", "--exit-on-error", "--single-transaction", "--no-owner",
         "--no-privileges", "--dbname", database, str(archive)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise BackupError(f"pg_restore failed (exit {result.returncode})")
    return database
