"""Owned SQLite installation update with an offline database checkpoint."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from .backup_manager import restore_sqlite_to_new_file, sqlite_backup, verify
from .installer import (
    DEBIAN_UNIT_SHA256,
    RELEASE_SCRIPT_SHA256,
    InstallationNotReady,
    _run,
    extract_release,
    fetch_release,
    file_digest,
)
from .lifecycle import _require_linux_root, _save_state, _state, _verify_owned
from .planner import Paths


def _healthy(port: int) -> None:
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise InstallationNotReady("updated panel loopback listener did not become healthy")


def _restore_database(snapshot: Path, database: Path) -> None:
    verify(snapshot)
    candidate = database.with_name(".x-ui-rollback.db")
    if candidate.exists() or candidate.is_symlink():
        raise InstallationNotReady("database rollback target occupied")
    restore_sqlite_to_new_file(snapshot, candidate)
    for suffix in ("-wal", "-shm"):
        database.with_name(database.name + suffix).unlink(missing_ok=True)
    os.replace(candidate, database)


def update_owned(paths: Paths = Paths()) -> dict:
    """Replace only installer-owned binaries; retain panel data and user files."""
    _require_linux_root()
    state = _state(paths)
    if state.get("status") != "installed":
        raise InstallationNotReady("update requires installed ownership state")
    _verify_owned(paths, state)
    if (not (paths.database / "x-ui.db").is_file() or
            paths.service_env.exists() or paths.service_env.is_symlink()):
        raise InstallationNotReady("update currently supports owned SQLite installs without PG env")
    if _run(["systemctl", "is-active", "x-ui"]).strip() != "active":
        raise InstallationNotReady("update requires an active owned panel")
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64",
            "arm64": "arm64"}.get(os.uname().machine)
    if arch is None:
        raise InstallationNotReady("release architecture unsupported")
    with tempfile.TemporaryDirectory(prefix=".xui-update-stage-", dir=paths.panel.parent) as staging:
        stage = Path(staging)
        archive = fetch_release(arch, stage)
        fresh = extract_release(archive, stage / "unpacked")
        fresh_binary = fresh / "x-ui"
        unit = fresh / "x-ui.service.debian"
        command = fresh / "x-ui.sh"
        if (file_digest(unit) != DEBIAN_UNIT_SHA256 or
                file_digest(command) != RELEASE_SCRIPT_SHA256 or
                _run([str(fresh_binary), "-v"]).strip() != "3.11.0"):
            raise InstallationNotReady("staged release differs from pinned official version")
        unit_bytes = unit.read_bytes()
        command_bytes = command.read_bytes()
        if (file_digest(fresh_binary) == state["hashes"]["binary"] and
                file_digest(unit) == state["hashes"]["unit"] and
                file_digest(command) == state["hashes"]["command"]):
            return {"changed": False, "reason": "owned installation already matches pinned release"}
        checkpoint = Path(tempfile.mkdtemp(prefix=".xui-update-", dir=paths.panel.parent))
        os.chmod(checkpoint, 0o700)
        shutil.copy2(paths.unit, checkpoint / "x-ui.service")
        shutil.copy2(paths.command, checkpoint / "x-ui-command")
        stop_attempted = False
        swapped = False
        try:
            stop_attempted = True
            _run(["systemctl", "stop", "x-ui"])
            snapshot = sqlite_backup(paths.database / "x-ui.db", checkpoint / "database")
            verify(snapshot)
            os.replace(paths.panel, checkpoint / "x-ui")
            swapped = True
            os.replace(fresh, paths.panel)
            paths.unit.write_bytes(unit_bytes)
            paths.command.write_bytes(command_bytes)
            paths.unit.chmod(0o644)
            paths.command.chmod(0o755)
            _run(["systemctl", "daemon-reload"])
            _run(["systemctl", "start", "x-ui"])
            _healthy(int(state["panel_port"]))
            if _run(["systemctl", "is-active", "x-ui"]).strip() != "active":
                raise InstallationNotReady("updated service is inactive")
            state["update_previous_version"] = state.get("panel_version")
            state["update_previous_hashes"] = state["hashes"].copy()
            state["panel_version"] = "3.11.0"
            state["hashes"] = {"binary": file_digest(paths.panel / "x-ui"),
                               "unit": file_digest(paths.unit),
                               "command": file_digest(paths.command)}
            state["update_checkpoint"] = str(checkpoint)
            state["update_snapshot"] = str(snapshot)
            _save_state(paths.state, state)
            return {"changed": True, "panel_version": "3.11.0",
                    "rollback_checkpoint": str(checkpoint), "database_snapshot": str(snapshot)}
        except Exception as exc:
            if stop_attempted:
                subprocess.run(["systemctl", "stop", "x-ui"], check=False)
                try:
                    if swapped:
                        if paths.panel.is_dir():
                            shutil.rmtree(paths.panel)
                        os.replace(checkpoint / "x-ui", paths.panel)
                        shutil.copy2(checkpoint / "x-ui.service", paths.unit)
                        shutil.copy2(checkpoint / "x-ui-command", paths.command)
                        _restore_database(snapshot, paths.database / "x-ui.db")
                except Exception as recovery_exc:
                    raise InstallationNotReady(
                        f"update failed and rollback is incomplete; inspect {checkpoint}") from recovery_exc
                finally:
                    subprocess.run(["systemctl", "daemon-reload"], check=False)
                    restarted = subprocess.run(["systemctl", "start", "x-ui"], check=False)
                if restarted.returncode != 0:
                    raise InstallationNotReady(
                        f"update and automatic rollback failed; inspect {checkpoint}") from exc
            raise


def rollback_update(*, restore_data: bool = False, paths: Paths = Paths()) -> dict:
    """Restore the previous owned release; database restore requires explicit consent."""
    _require_linux_root()
    state = _state(paths)
    if state.get("status") != "installed" or not state.get("update_checkpoint"):
        raise InstallationNotReady("no completed update checkpoint")
    _verify_owned(paths, state)
    checkpoint = Path(state["update_checkpoint"])
    if (checkpoint.parent != paths.panel.parent or not checkpoint.name.startswith(".xui-update-")
            or not checkpoint.is_dir() or checkpoint.is_symlink()):
        raise InstallationNotReady("update checkpoint path is invalid")
    previous = state.get("update_previous_hashes")
    if not isinstance(previous, dict):
        raise InstallationNotReady("previous ownership hashes unavailable")
    for key, item in (("binary", checkpoint / "x-ui" / "x-ui"),
                      ("unit", checkpoint / "x-ui.service"),
                      ("command", checkpoint / "x-ui-command")):
        if not item.is_file() or item.is_symlink() or file_digest(item) != previous.get(key):
            raise InstallationNotReady("previous owned release modified or missing")
    if state.get("update_previous_version") != state.get("panel_version") and not restore_data:
        raise InstallationNotReady("version rollback requires --restore-data for SQLite schema")
    snapshot = Path(state.get("update_snapshot", ""))
    if restore_data:
        if snapshot.parent.parent != checkpoint:
            raise InstallationNotReady("database checkpoint path is invalid")
        verify(snapshot)
    current = checkpoint / "current"
    if current.exists() or current.is_symlink():
        raise InstallationNotReady("rollback staging path occupied")
    shutil.copy2(paths.unit, checkpoint / "current.service")
    shutil.copy2(paths.command, checkpoint / "current-command")
    stop_attempted = False
    swapped = False
    try:
        stop_attempted = True
        _run(["systemctl", "stop", "x-ui"])
        current_snapshot = None
        if restore_data:
            current_snapshot = sqlite_backup(paths.database / "x-ui.db", checkpoint / "current-db")
        os.replace(paths.panel, current)
        swapped = True
        os.replace(checkpoint / "x-ui", paths.panel)
        shutil.copy2(checkpoint / "x-ui.service", paths.unit)
        shutil.copy2(checkpoint / "x-ui-command", paths.command)
        if restore_data:
            _restore_database(snapshot, paths.database / "x-ui.db")
        _run(["systemctl", "daemon-reload"])
        _run(["systemctl", "start", "x-ui"])
        _healthy(int(state["panel_port"]))
        state["hashes"] = previous
        state["panel_version"] = state["update_previous_version"]
        for key in ("update_checkpoint", "update_snapshot", "update_previous_hashes",
                    "update_previous_version"):
            state.pop(key, None)
        _save_state(paths.state, state)
        return {"rolled_back": "update", "database_restored": restore_data,
                "replaced_release_retained": str(current)}
    except Exception as exc:
        if stop_attempted:
            subprocess.run(["systemctl", "stop", "x-ui"], check=False)
            try:
                if swapped:
                    if paths.panel.is_dir():
                        os.replace(paths.panel, checkpoint / "x-ui")
                    os.replace(current, paths.panel)
                    shutil.copy2(checkpoint / "current.service", paths.unit)
                    shutil.copy2(checkpoint / "current-command", paths.command)
                    if restore_data and current_snapshot is not None:
                        _restore_database(current_snapshot, paths.database / "x-ui.db")
            except Exception as recovery_exc:
                raise InstallationNotReady(
                    f"rollback recovery incomplete; inspect {checkpoint}") from recovery_exc
            finally:
                subprocess.run(["systemctl", "daemon-reload"], check=False)
                restarted = subprocess.run(["systemctl", "start", "x-ui"], check=False)
            if restarted.returncode != 0:
                raise InstallationNotReady(
                    f"rollback failed; current release and checkpoint retained at {checkpoint}") from exc
        raise
