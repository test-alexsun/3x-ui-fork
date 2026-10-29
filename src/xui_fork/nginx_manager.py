"""Deterministic, ownership-scoped Nginx panel site with verified rollback."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

MARKER = "# managed-by: 3x-ui-fork\n"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")


class NginxError(RuntimeError):
    pass


def render_panel_site(domain: str, cert: Path, key: Path, panel_port: int) -> str:
    if not DOMAIN_RE.fullmatch(domain) or not 1 <= panel_port <= 65535:
        raise ValueError("invalid domain or panel port")
    for path in (cert, key):
        if not path.is_absolute() or any(char in str(path) for char in " \n\r;{}"):
            raise ValueError("certificate paths must be absolute and contain no Nginx syntax")
    return (MARKER + "server {\n"
            "    listen 443 ssl;\n"
            "    listen [::]:443 ssl;\n"
            f"    server_name {domain};\n"
            f"    ssl_certificate {cert};\n"
            f"    ssl_certificate_key {key};\n"
            "    ssl_protocols TLSv1.2 TLSv1.3;\n"
            "    location / {\n"
            f"        proxy_pass http://127.0.0.1:{panel_port};\n"
            "        proxy_http_version 1.1;\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "        proxy_set_header X-Forwarded-Proto https;\n"
            "        proxy_set_header Upgrade $http_upgrade;\n"
            "        proxy_set_header Connection \"upgrade\";\n"
            "    }\n"
            "}\n")


def _run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def apply_managed_config(target: Path, content: str, nginx: str = "nginx") -> bool:
    """Apply only our include. Restore previous bytes on syntax or reload failure."""
    if target.name != "3x-ui-fork.conf" or not target.parent.is_dir():
        raise NginxError("target must be an existing conf.d/3x-ui-fork.conf parent")
    if not content.startswith(MARKER):
        raise NginxError("managed marker missing")
    if target.is_symlink():
        raise NginxError("managed target must not be a symlink")
    previous = target.read_bytes() if target.exists() else None
    if previous is not None and not previous.startswith(MARKER.encode()):
        raise NginxError("foreign file at managed target")
    desired = content.encode("utf-8")
    if previous == desired:
        return False
    candidate: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".3x-ui-fork-",
                                         suffix=".candidate", delete=False) as stream:
            stream.write(desired)
            stream.flush()
            os.fsync(stream.fileno())
            candidate = Path(stream.name)
        os.chmod(candidate, 0o644)
        # A second read catches a local race before the atomic replacement.
        current = target.read_bytes() if target.exists() else None
        if _digest(current) != _digest(previous):
            raise NginxError("managed file changed during apply")
        os.replace(candidate, target)
        candidate = None
        try:
            _run(nginx, "-t")
            _run(nginx, "-s", "reload")
        except (OSError, subprocess.CalledProcessError) as exc:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".3x-ui-fork-",
                                                 delete=False) as old:
                    old.write(previous)
                    old.flush()
                    os.fsync(old.fileno())
                    old_path = Path(old.name)
                os.replace(old_path, target)
            raise NginxError("Nginx validation or reload failed; previous include restored") from exc
        return True
    finally:
        if candidate is not None:
            candidate.unlink(missing_ok=True)
