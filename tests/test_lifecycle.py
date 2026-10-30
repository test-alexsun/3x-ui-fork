import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from xui_fork.installer import InstallationNotReady, file_digest
from xui_fork.lifecycle import _wait_loopback, repair_owned, rollback_uninstall, uninstall_owned
from xui_fork.planner import Paths
from xui_fork.updater import rollback_update, update_owned


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = Paths(root / "x-ui", root / "db", root / "x-ui.service",
                           root / "state.json", root / "nginx.conf", root / "x-ui-command")
        self.paths.panel.mkdir()
        self.paths.database.mkdir()
        (self.paths.panel / "x-ui").write_bytes(b"binary")
        (self.paths.panel / "x-ui.service.debian").write_bytes(b"unit")
        (self.paths.panel / "x-ui.sh").write_bytes(b"command")
        self.paths.unit.write_bytes(b"unit")
        self.paths.command.write_bytes(b"command")
        state = {"schema": 1, "status": "installed", "panel_version": "3.11.0",
                 "panel_port": 2053,
                 "hashes": {"binary": file_digest(self.paths.panel / "x-ui"),
                            "unit": file_digest(self.paths.unit),
                            "command": file_digest(self.paths.command)}}
        self.paths.state.write_text(json.dumps(state), encoding="utf-8")

    def test_repair_restores_only_missing_owned_files(self):
        self.paths.unit.unlink()
        with (patch("xui_fork.lifecycle._require_linux_root"),
              patch("xui_fork.lifecycle._run") as runner,
              patch("xui_fork.lifecycle.subprocess.run", return_value=Mock(returncode=0)),
              patch("xui_fork.lifecycle.socket.create_connection") as connection):
            result = repair_owned(self.paths)
        self.assertEqual(result["repaired"], ["unit"])
        self.assertEqual(self.paths.unit.read_bytes(), b"unit")
        self.assertEqual(self.paths.command.read_bytes(), b"command")
        runner.assert_called_once_with(["systemctl", "daemon-reload"])
        connection.assert_called_once()

    def test_repair_refuses_foreign_modified_unit(self):
        self.paths.unit.write_bytes(b"user replacement")
        with patch("xui_fork.lifecycle._require_linux_root"):
            with self.assertRaisesRegex(InstallationNotReady, "modified"):
                repair_owned(self.paths)
        self.assertEqual(self.paths.unit.read_bytes(), b"user replacement")

    def test_uninstall_preserves_data_and_rollback_restores_owned_files(self):
        (self.paths.database / "x-ui.db").write_bytes(b"user data")
        with (patch("xui_fork.lifecycle._require_linux_root"),
              patch("xui_fork.lifecycle._run"),
              patch("xui_fork.lifecycle.socket.create_connection")):
            removed = uninstall_owned(confirmed=True, paths=self.paths)
            self.assertTrue(removed["uninstalled"])
            self.assertFalse(self.paths.panel.exists())
            self.assertEqual((self.paths.database / "x-ui.db").read_bytes(), b"user data")
            restored = rollback_uninstall(self.paths)
        self.assertEqual(restored["rolled_back"], "uninstall")
        self.assertEqual((self.paths.panel / "x-ui").read_bytes(), b"binary")
        self.assertEqual(self.paths.unit.read_bytes(), b"unit")
        self.assertEqual(self.paths.command.read_bytes(), b"command")

    def test_uninstall_needs_confirmation(self):
        with patch("xui_fork.lifecycle._require_linux_root"):
            with self.assertRaisesRegex(InstallationNotReady, "confirm"):
                uninstall_owned(confirmed=False, paths=self.paths)
        self.assertTrue(self.paths.panel.is_dir())

    def test_loopback_health_waits_for_service_start(self):
        with (patch("xui_fork.lifecycle.socket.create_connection",
                    side_effect=[OSError("not yet"), MagicMock()]) as connect,
              patch("xui_fork.lifecycle.time.sleep") as sleep):
            _wait_loopback(2053)
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_update_swaps_binary_and_preserves_database(self):
        database = self.paths.database / "x-ui.db"
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            db.execute("INSERT INTO users VALUES (1, 'kept')")
            db.commit()
        root = self.paths.panel.parent
        fresh = root / "fresh"
        fresh.mkdir()
        (fresh / "x-ui").write_bytes(b"new binary")
        (fresh / "x-ui.service.debian").write_bytes(b"new unit")
        (fresh / "x-ui.sh").write_bytes(b"new command")

        def run(args):
            return "3.11.0\n" if args[-1] == "-v" else "active\n"

        with (patch("xui_fork.updater._require_linux_root"),
              patch("xui_fork.updater.os.uname", create=True,
                    return_value=Mock(machine="x86_64")),
              patch("xui_fork.updater.fetch_release", return_value=root / "unused"),
              patch("xui_fork.updater.extract_release", return_value=fresh),
              patch("xui_fork.updater.DEBIAN_UNIT_SHA256", file_digest(fresh / "x-ui.service.debian")),
              patch("xui_fork.updater.RELEASE_SCRIPT_SHA256", file_digest(fresh / "x-ui.sh")),
              patch("xui_fork.updater._run", side_effect=run),
              patch("xui_fork.updater._healthy")):
            result = update_owned(self.paths)
        self.assertTrue(result["changed"])
        self.assertEqual((self.paths.panel / "x-ui").read_bytes(), b"new binary")
        self.assertEqual(self.paths.unit.read_bytes(), b"new unit")
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("SELECT name FROM users").fetchone()[0], "kept")
        self.assertEqual((Path(result["rollback_checkpoint"]) / "x-ui" / "x-ui").read_bytes(),
                         b"binary")
        with (patch("xui_fork.updater._require_linux_root"),
              patch("xui_fork.updater._run", side_effect=run),
              patch("xui_fork.updater._healthy")):
            rolled_back = rollback_update(paths=self.paths)
        self.assertEqual(rolled_back["rolled_back"], "update")
        self.assertFalse(rolled_back["database_restored"])
        self.assertEqual((self.paths.panel / "x-ui").read_bytes(), b"binary")
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("SELECT name FROM users").fetchone()[0], "kept")

    def test_failed_update_restores_previous_release(self):
        database = self.paths.database / "x-ui.db"
        with closing(sqlite3.connect(database)) as db:
            db.execute("CREATE TABLE data (value TEXT)")
            db.execute("INSERT INTO data VALUES ('kept')")
            db.commit()
        fresh = self.paths.panel.parent / "fresh-failure"
        fresh.mkdir()
        (fresh / "x-ui").write_bytes(b"new binary")
        (fresh / "x-ui.service.debian").write_bytes(b"new unit")
        (fresh / "x-ui.sh").write_bytes(b"new command")

        def run(args):
            return "3.11.0\n" if args[-1] == "-v" else "active\n"

        with (patch("xui_fork.updater._require_linux_root"),
              patch("xui_fork.updater.os.uname", create=True,
                    return_value=Mock(machine="x86_64")),
              patch("xui_fork.updater.fetch_release", return_value=fresh / "unused"),
              patch("xui_fork.updater.extract_release", return_value=fresh),
              patch("xui_fork.updater.DEBIAN_UNIT_SHA256", file_digest(fresh / "x-ui.service.debian")),
              patch("xui_fork.updater.RELEASE_SCRIPT_SHA256", file_digest(fresh / "x-ui.sh")),
              patch("xui_fork.updater._run", side_effect=run),
              patch("xui_fork.updater._healthy", side_effect=InstallationNotReady("unhealthy")),
              patch("xui_fork.updater.subprocess.run", return_value=Mock(returncode=0))):
            with self.assertRaisesRegex(InstallationNotReady, "unhealthy"):
                update_owned(self.paths)
        self.assertEqual((self.paths.panel / "x-ui").read_bytes(), b"binary")
        self.assertEqual(self.paths.unit.read_bytes(), b"unit")
        self.assertEqual(self.paths.command.read_bytes(), b"command")
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("SELECT value FROM data").fetchone()[0], "kept")
        self.assertEqual(json.loads(self.paths.state.read_text())["hashes"]["binary"],
                         file_digest(self.paths.panel / "x-ui"))
