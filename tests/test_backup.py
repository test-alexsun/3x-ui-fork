import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from xui_fork.backup_manager import (
    BackupError,
    _write_manifest,
    restore_postgres_to_empty_db,
    restore_sqlite_to_new_file,
    sqlite_backup,
    verify,
)


class BackupTests(unittest.TestCase):
    def test_sqlite_online_backup_includes_wal_and_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            source = tmp_path / "source.db"
            writer = sqlite3.connect(source)
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY, uuid TEXT)")
            writer.execute("INSERT INTO clients (uuid) VALUES ('stable-id')")
            writer.commit()
            folder = sqlite_backup(source, tmp_path / "backups")
            self.assertEqual(verify(folder)["backend"], "sqlite")
            dest = restore_sqlite_to_new_file(folder, tmp_path / "restored.db")
            with closing(sqlite3.connect(dest)) as db:
                self.assertEqual(db.execute("SELECT uuid FROM clients").fetchone()[0], "stable-id")
            with self.assertRaisesRegex(BackupError, "already exists"):
                restore_sqlite_to_new_file(folder, dest)
            writer.close()


    def test_backup_checksum_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            tmp_path = Path(temporary)
            source = tmp_path / "source.db"
            with closing(sqlite3.connect(source)) as db:
                db.execute("CREATE TABLE t (id INTEGER)")
            folder = sqlite_backup(source, tmp_path / "backups")
            (folder / "x-ui.db").write_bytes(b"tampered")
            with self.assertRaisesRegex(BackupError, "checksum"):
                verify(folder)


    def test_manifest_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "backup"
            folder.mkdir()
            (folder / "manifest.json").write_text(json.dumps({"schema": 1, "backend": "sqlite",
                "file": "../outside", "size": 0, "sha256": ""}))
            with self.assertRaisesRegex(BackupError, "unsafe"):
                verify(folder)

    def test_postgres_restore_rejects_wrong_or_nonempty_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            archive = folder / "x-ui.dump"
            archive.write_bytes(b"fixture archive")
            _write_manifest(folder, archive, "postgres")
            with self.assertRaisesRegex(BackupError, "dedicated"):
                restore_postgres_to_empty_db(folder, "production")
            with patch.dict("os.environ", {"PGDATABASE": "xui_restore_test"}):
                with patch("subprocess.run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = "1\n"
                    with self.assertRaisesRegex(BackupError, "not empty"):
                        restore_postgres_to_empty_db(folder, "xui_restore_test")
                    self.assertEqual(run.call_count, 1)
