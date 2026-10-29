"""Runs only against a disposable CI PostgreSQL instance."""

import os
import subprocess
import tempfile
from pathlib import Path

from xui_fork.backup_manager import postgres_backup, restore_postgres_to_empty_db, verify


def command(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    return result.stdout.strip()


def main() -> None:
    if os.environ.get("XUI_RUN_PG_INTEGRATION") != "1":
        raise RuntimeError("disposable PostgreSQL integration must be explicitly enabled")
    if os.environ.get("PGDATABASE") != "xui_source":
        raise RuntimeError("PGDATABASE must be CI source database")
    command("psql", "--no-password", "-v", "ON_ERROR_STOP=1", "-c",
            "CREATE TABLE clients (id bigint PRIMARY KEY, uuid text NOT NULL)")
    command("psql", "--no-password", "-v", "ON_ERROR_STOP=1", "-c",
            "INSERT INTO clients VALUES (7, 'stable-id')")
    with tempfile.TemporaryDirectory() as directory:
        folder = postgres_backup(Path(directory))
        assert verify(folder)["backend"] == "postgres"
        command("createdb", "--no-password", "xui_restore_ci")
        os.environ["PGDATABASE"] = "xui_restore_ci"
        restore_postgres_to_empty_db(folder, "xui_restore_ci")
        assert command("psql", "--no-password", "-Atc",
                       "SELECT id || ':' || uuid FROM clients") == "7:stable-id"


if __name__ == "__main__":
    main()
