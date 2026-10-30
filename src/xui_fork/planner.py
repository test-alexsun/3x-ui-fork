"""Read-only, deterministic system plans. No credentials are generated here."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .preflight import collect


@dataclass(frozen=True)
class Paths:
    panel: Path = Path("/usr/local/x-ui")
    database: Path = Path("/etc/x-ui")
    unit: Path = Path("/etc/systemd/system/x-ui.service")
    state: Path = Path("/var/lib/3x-ui-fork/state.json")
    nginx: Path = Path("/etc/nginx/conf.d/3x-ui-fork.conf")
    command: Path = Path("/usr/bin/x-ui")
    service_env: Path = Path("/etc/default/x-ui")


@dataclass(frozen=True)
class Step:
    operation: str
    target: str
    effect: str


def plan(action: str, *, paths: Paths = Paths(), domain: str | None = None,
         panel_port: int = 2053, inventory: dict | None = None) -> dict:
    if action not in {"install", "update", "repair", "uninstall"}:
        raise ValueError("unsupported planned action")
    if not 1 <= panel_port <= 65535:
        raise ValueError("panel port out of range")
    observed = collect(domain, (80, 443, panel_port)) if inventory is None else inventory
    owned = paths.state.exists() or paths.state.is_symlink()
    panel = paths.panel.exists() or paths.panel.is_symlink()
    database = paths.database.exists() or paths.database.is_symlink()
    unit = paths.unit.exists() or paths.unit.is_symlink()
    command = paths.command.exists() or paths.command.is_symlink()
    service_env = paths.service_env.exists() or paths.service_env.is_symlink()
    blockers: list[str] = []
    steps: list[Step] = []
    if not observed.get("supported"):
        blockers.append("unsupported OS or architecture")
    if action == "install":
        if any((owned, panel, database, unit, command, service_env)):
            blockers.append("existing panel, data, unit, or ownership state; use update/adoption")
        if not observed.get("root"):
            blockers.append("root privileges required")
        if not observed.get("commands", {}).get("systemctl"):
            blockers.append("systemd/systemctl dependency unavailable")
        port_state = observed.get("ports", {}).get(str(panel_port))
        if port_state is None:
            blockers.append("panel port status unavailable")
        elif not port_state:
            blockers.append("panel port already in use")
        steps = [
            Step("download", "official 3x-ui v3.11.0", "download into isolated staging"),
            Step("verify", "release SHA-256 and archive entries", "reject mismatch"),
            Step("configure", "new SQLite DB and panel settings", "bind 127.0.0.1 before start"),
            Step("apply", paths.panel.as_posix(), "install verified official files"),
            Step("apply", paths.unit.as_posix(), "install official systemd unit"),
            Step("apply", paths.command.as_posix(), "install official CLI script"),
            Step("verify", "x-ui.service and loopback listener", "record ownership only after health"),
        ]
    elif action == "update":
        if not (owned and panel and database and unit):
            blockers.append("update requires complete owned installation")
        steps = [Step("backup", paths.database.as_posix(), "consistent database checkpoint"),
                 Step("stage", paths.panel.as_posix(), "keep old binary tree"),
                 Step("apply", paths.panel.as_posix(), "replace with pinned official release"),
                 Step("verify", "service and loopback listener", "rollback on failure")]
    elif action == "repair":
        if not owned:
            blockers.append("repair requires ownership state")
        if not unit and panel:
            steps.append(Step("repair", paths.unit.as_posix(), "restore owned official unit"))
        if not command and panel:
            steps.append(Step("repair", paths.command.as_posix(), "restore owned official CLI"))
        if not steps:
            steps.append(Step("check", "owned installation", "no file changes planned"))
    else:
        if not owned:
            blockers.append("uninstall requires ownership state")
        steps = [Step("stop", "x-ui.service", "stop owned service"),
                 Step("remove", paths.panel.as_posix(), "remove owned binary tree only"),
                 Step("retain", paths.database.as_posix(), "keep user data and certificates")]
    return {"action": action, "ready_to_apply": not blockers,
            "blockers": blockers, "observed": observed,
            "steps": [asdict(step) for step in steps]}
