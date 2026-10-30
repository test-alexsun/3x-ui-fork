"""Ownership-scoped repair, reversible uninstall, and uninstall rollback."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from .installer import InstallationNotReady, _run, file_digest
from .planner import Paths


def _state(paths: Paths) -> dict:
    if paths.state.is_symlink():
        raise InstallationNotReady("ownership state must not be a symlink")
    try:
        value = json.loads(paths.state.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallationNotReady("ownership state missing or invalid") from exc
    if value.get("schema") != 1 or not isinstance(value.get("hashes"), dict):
        raise InstallationNotReady("unsupported ownership state")
    return value


def _save_state(path: Path, state: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    candidate = Path(name)
    try:
        os.chmod(candidate, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(candidate, path)
    finally:
        candidate.unlink(missing_ok=True)


def _require_linux_root() -> None:
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise InstallationNotReady("operation requires root on Linux")


def _verify_owned(paths: Paths, state: dict) -> None:
    for key, path in (("unit", paths.unit), ("command", paths.command),
                      ("binary", paths.panel / "x-ui")):
        if not path.is_file() or path.is_symlink() or file_digest(path) != state["hashes"].get(key):
            raise InstallationNotReady(f"owned {key} missing or modified")


def _wait_loopback(port: int) -> None:
    for _ in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(1)
    raise InstallationNotReady("owned panel loopback listener did not become healthy")


def repair_owned(paths: Paths = Paths()) -> dict:
    _require_linux_root()
    state = _state(paths)
    if state.get("status") != "installed":
        raise InstallationNotReady("repair requires installed ownership state")
    if not paths.panel.is_dir() or file_digest(paths.panel / "x-ui") != state["hashes"]["binary"]:
        raise InstallationNotReady("owned panel binary missing or modified")
    repaired: list[str] = []
    if not paths.unit.exists() and not paths.unit.is_symlink():
        source = paths.panel / "x-ui.service"
        if not source.is_file():
            source = paths.panel / "x-ui.service.debian"
        if not source.is_file() or file_digest(source) != state["hashes"]["unit"]:
            raise InstallationNotReady("official unit unavailable for repair")
        shutil.copyfile(source, paths.unit)
        paths.unit.chmod(0o644)
        repaired.append("unit")
        _run(["systemctl", "daemon-reload"])
    if not paths.command.exists() and not paths.command.is_symlink():
        source = paths.panel / "x-ui.sh"
        if not source.is_file() or file_digest(source) != state["hashes"]["command"]:
            raise InstallationNotReady("official CLI unavailable for repair")
        shutil.copyfile(source, paths.command)
        paths.command.chmod(0o755)
        repaired.append("command")
    _verify_owned(paths, state)
    active = subprocess.run(["systemctl", "is-active", "--quiet", "x-ui"], check=False)
    if active.returncode != 0:
        _run(["systemctl", "start", "x-ui"])
        repaired.append("service-start")
    _wait_loopback(int(state["panel_port"]))
    return {"repaired": repaired, "service": "active"}


def uninstall_owned(*, confirmed: bool, paths: Paths = Paths()) -> dict:
    _require_linux_root()
    if not confirmed:
        raise InstallationNotReady("uninstall requires --confirm-uninstall")
    state = _state(paths)
    if state.get("status") != "installed":
        raise InstallationNotReady("installation is not active")
    _verify_owned(paths, state)
    checkpoint = Path(tempfile.mkdtemp(prefix=".xui-uninstall-", dir=paths.panel.parent))
    os.chmod(checkpoint, 0o700)
    shutil.copy2(paths.unit, checkpoint / "x-ui.service")
    shutil.copy2(paths.command, checkpoint / "x-ui-command")
    try:
        _run(["systemctl", "stop", "x-ui"])
        _run(["systemctl", "disable", "x-ui"])
        os.replace(paths.panel, checkpoint / "x-ui")
        paths.unit.unlink()
        paths.command.unlink()
        _run(["systemctl", "daemon-reload"])
        state["status"] = "uninstalled"
        state["checkpoint"] = str(checkpoint)
        _save_state(paths.state, state)
    except Exception:
        if (checkpoint / "x-ui").exists() and not paths.panel.exists():
            os.replace(checkpoint / "x-ui", paths.panel)
        if not paths.unit.exists():
            shutil.copy2(checkpoint / "x-ui.service", paths.unit)
        if not paths.command.exists():
            shutil.copy2(checkpoint / "x-ui-command", paths.command)
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "enable", "x-ui"], check=False)
        subprocess.run(["systemctl", "start", "x-ui"], check=False)
        raise
    return {"uninstalled": True, "user_data_retained": str(paths.database),
            "rollback_checkpoint": str(checkpoint)}


def rollback_uninstall(paths: Paths = Paths()) -> dict:
    _require_linux_root()
    state = _state(paths)
    if state.get("status") != "uninstalled":
        raise InstallationNotReady("only uninstall rollback is supported")
    checkpoint = Path(state.get("checkpoint", ""))
    if (checkpoint.parent != paths.panel.parent or
            not checkpoint.name.startswith(".xui-uninstall-") or
            not checkpoint.is_dir() or checkpoint.is_symlink()):
        raise InstallationNotReady("uninstall checkpoint missing or outside state directory")
    if any((paths.panel.exists(), paths.unit.exists(), paths.command.exists())):
        raise InstallationNotReady("rollback target paths occupied")
    for key, file in (("unit", checkpoint / "x-ui.service"),
                      ("command", checkpoint / "x-ui-command"),
                      ("binary", checkpoint / "x-ui" / "x-ui")):
        if not file.is_file() or file_digest(file) != state["hashes"].get(key):
            raise InstallationNotReady("checkpoint file modified or missing")
    try:
        os.replace(checkpoint / "x-ui", paths.panel)
        shutil.copy2(checkpoint / "x-ui.service", paths.unit)
        shutil.copy2(checkpoint / "x-ui-command", paths.command)
        _run(["systemctl", "daemon-reload"])
        _run(["systemctl", "enable", "x-ui"])
        _run(["systemctl", "start", "x-ui"])
        _wait_loopback(int(state["panel_port"]))
        state["status"] = "installed"
        state.pop("checkpoint", None)
        _save_state(paths.state, state)
    except Exception:
        subprocess.run(["systemctl", "stop", "x-ui"], check=False)
        subprocess.run(["systemctl", "disable", "x-ui"], check=False)
        paths.unit.unlink(missing_ok=True)
        paths.command.unlink(missing_ok=True)
        if paths.panel.is_dir() and not (checkpoint / "x-ui").exists():
            os.replace(paths.panel, checkpoint / "x-ui")
        subprocess.run(["systemctl", "daemon-reload"], check=False)
        raise
    return {"rolled_back": "uninstall", "service": "active"}
