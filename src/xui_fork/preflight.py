"""Read-only local inventory. No probing endpoint may create credentials."""

from __future__ import annotations

import os
import platform
import shutil
import socket
from pathlib import Path

from .compatibility import SUPPORTED_ARCH, SUPPORTED_OS


def os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            result[key] = value.strip().strip('"')
    return result


def port_available(port: int, family: int = socket.AF_INET) -> bool:
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("::" if family == socket.AF_INET6 else "0.0.0.0", port))
            return True
        except OSError:
            return False


def collect(domain: str | None = None) -> dict:
    if platform.system() != "Linux":
        return {"platform": platform.system(), "supported": False, "reason": "Linux required"}
    release = os_release()
    os_tuple = (release.get("ID", ""), release.get("VERSION_ID", ""))
    arch = platform.machine().lower()
    result = {
        "platform": "Linux", "os": list(os_tuple), "arch": arch,
        "root": os.geteuid() == 0,
        "supported": os_tuple in SUPPORTED_OS and arch in SUPPORTED_ARCH,
        "commands": {name: bool(shutil.which(name)) for name in
                     ("python3", "systemctl", "curl", "nginx", "pg_dump", "x-ui")},
        "panel_path_exists": Path("/usr/local/x-ui").exists(),
        "ports": {str(p): port_available(p) for p in (80, 443)},
    }
    if domain:
        try:
            result["dns"] = sorted({item[4][0] for item in socket.getaddrinfo(domain, None)})
        except socket.gaierror as exc:
            result["dns_error"] = str(exc)
    return result
