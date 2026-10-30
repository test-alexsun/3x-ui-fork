"""Pinned official release acquisition and clean installation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

from .compatibility import load_capabilities
from .planner import Paths, plan

MAX_ARCHIVE = 512 * 1024 * 1024
OFFICIAL_RELEASE = "https://github.com/MHSanaei/3x-ui/releases/download/v3.11.0"
INSTALLER_URL = ("https://raw.githubusercontent.com/MHSanaei/3x-ui/"
                 "c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/install.sh")
INSTALLER_BLOB_SHA1 = "dd67e6c0935f5f1f1858ea5b4cef24107e91dc69"
RELEASE_SCRIPT_SHA256 = "26c229d5fb3b184e81581b4b223b801582ca7cf5908aaedeb8d1c7c70ad4cc25"
DEBIAN_UNIT_SHA256 = "95cb6e39499601148404cadf3b4d75b0489301ff7e7ab565cd9db21d23be957c"


class InstallationNotReady(RuntimeError):
    pass


def _download(url: str, destination: Path, expected_digest: str,
              algorithm: str = "sha256") -> Path:
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise InstallationNotReady("artifact destination must be a new file in an existing directory")
    fd, candidate = tempfile.mkstemp(prefix=".xui-download-", dir=destination.parent)
    os.close(fd)
    candidate_path = Path(candidate)
    try:
        with urllib.request.urlopen(url, timeout=30) as response, candidate_path.open("wb") as out:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise InstallationNotReady("upstream artifact exceeds size limit")
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if algorithm == "git-blob-sha1":
            hasher = hashlib.sha1(f"blob {candidate_path.stat().st_size}\0".encode())
        else:
            hasher = hashlib.sha256()
        with candidate_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != expected_digest:
            raise InstallationNotReady("upstream artifact digest mismatch")
        os.replace(candidate_path, destination)
        return destination
    finally:
        candidate_path.unlink(missing_ok=True)


def fetch_release(arch: str, directory: Path) -> Path:
    digests = load_capabilities()["release_assets"]
    if arch not in digests:
        raise InstallationNotReady("unsupported release architecture")
    name = f"x-ui-linux-{arch}.tar.gz"
    archive = _download(f"{OFFICIAL_RELEASE}/{name}", directory / name, digests[arch])
    try:
        with tarfile.open(archive, "r:gz") as tar:
            names = set(tar.getnames())
            if not {"x-ui/x-ui", "x-ui/x-ui.sh"}.issubset(names):
                raise InstallationNotReady("release archive lacks expected panel files")
            for member in tar:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                    raise InstallationNotReady("release archive contains unsafe entries")
    except (tarfile.TarError, OSError) as exc:
        archive.unlink(missing_ok=True)
        raise InstallationNotReady("release archive is invalid") from exc
    except InstallationNotReady:
        archive.unlink(missing_ok=True)
        raise
    return archive


def fetch_official_installer(directory: Path) -> Path:
    return _download(INSTALLER_URL, directory / "official-install.sh",
                     INSTALLER_BLOB_SHA1, "git-blob-sha1")


def extract_release(archive: Path, destination: Path) -> Path:
    """Extract only regular members beneath x-ui into a new staging directory."""
    if destination.exists() or not destination.parent.is_dir():
        raise InstallationNotReady("release staging destination must be new")
    destination.mkdir(mode=0o700)
    total = 0
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                relative = PurePosixPath(member.name)
                if (relative.is_absolute() or ".." in relative.parts or
                        not relative.parts or relative.parts[0] != "x-ui"):
                    raise InstallationNotReady("unsafe release member path")
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    total += member.size
                    if total > 1024 * 1024 * 1024:
                        raise InstallationNotReady("unpacked release exceeds size limit")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = tar.extractfile(member)
                    if source is None:
                        raise InstallationNotReady("release member cannot be read")
                    with source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(member.mode & 0o755)
                else:
                    raise InstallationNotReady("release contains special file or link")
        panel = destination / "x-ui"
        if not (panel / "x-ui").is_file() or not (panel / "x-ui.sh").is_file():
            raise InstallationNotReady("release is missing official binaries")
        if not any((panel / name).is_file() for name in
                   ("x-ui.service", "x-ui.service.debian")):
            raise InstallationNotReady("release is missing systemd unit")
        return panel
    except Exception:
        shutil.rmtree(destination)
        raise


def _run(args: list[str], *, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(args, cwd=cwd, check=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Args can contain the freshly generated administrator password.
        raise InstallationNotReady(f"{Path(args[0]).name} {args[1] if len(args) > 1 else ''} failed") from None
    return result.stdout


def _write_private_json(path: Path, value: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install_clean(*, panel_port: int = 2053, paths: Paths = Paths()) -> dict:
    """Install the pinned official release on a genuinely empty Linux host.

    The panel is configured for loopback before the service is first started.
    No Nginx, ACME, firewall or inbound changes are made by this operation.
    """
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise InstallationNotReady("clean installation requires root on Linux")
    assessment = plan("install", paths=paths, panel_port=panel_port)
    if not assessment["ready_to_apply"]:
        raise InstallationNotReady("install preflight blocked: " + "; ".join(assessment["blockers"]))
    if paths.panel != Path("/usr/local/x-ui") or paths.database != Path("/etc/x-ui"):
        raise InstallationNotReady("official systemd unit requires standard panel and database paths")
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64",
            "arm64": "arm64"}.get(platform.machine().lower())
    if arch is None:
        raise InstallationNotReady("release architecture unsupported")
    created: list[Path] = []
    service_start_attempted = False
    service_enable_attempted = False
    with tempfile.TemporaryDirectory(prefix=".3x-ui-fork-", dir=paths.panel.parent) as staging:
        staged = Path(staging)
        archive = fetch_release(arch, staged)
        unpacked = extract_release(archive, staged / "unpacked")
        unit_source = unpacked / "x-ui.service.debian"
        if (file_digest(unpacked / "x-ui.sh") != RELEASE_SCRIPT_SHA256 or
                file_digest(unit_source) != DEBIAN_UNIT_SHA256):
            raise InstallationNotReady("release script or Debian unit differs from pinned source")
        unit_bytes = unit_source.read_bytes()
        if b"ExecStart=/usr/local/x-ui/x-ui" not in unit_bytes:
            raise InstallationNotReady("official unit has an unexpected ExecStart")
        if _run([str(unpacked / "x-ui"), "-v"]).strip() != "3.11.0":
            raise InstallationNotReady("release binary version differs from pinned version")
        username = "admin_" + secrets.token_urlsafe(9)
        password = secrets.token_urlsafe(32)
        base_path = secrets.token_urlsafe(18)
        try:
            if any(path.exists() or path.is_symlink() for path in
                   (paths.panel, paths.database, paths.unit, paths.command,
                    paths.state, paths.service_env)):
                raise InstallationNotReady("installation target changed after preflight")
            os.replace(unpacked, paths.panel)
            created.append(paths.panel)
            (paths.panel / "x-ui").chmod(0o755)
            (paths.panel / "x-ui.sh").chmod(0o755)
            (paths.panel / "bin" / f"xray-linux-{arch}").chmod(0o755)
            paths.database.mkdir(mode=0o700)
            created.append(paths.database)
            binary = str(paths.panel / "x-ui")
            _run([binary, "setting", "-username", username, "-password", password,
                  "-port", str(panel_port), "-webBasePath", base_path], cwd=paths.panel)
            _run([binary, "setting", "-listenIP", "127.0.0.1"], cwd=paths.panel)
            observed = _run([binary, "setting", "-show", "-getListen"], cwd=paths.panel)
            if (not re.search(r"(?m)^\s*listenIP:\s*127\.0\.0\.1\s*$", observed)
                    or not re.search(rf"(?m)^\s*port:\s*{panel_port}\s*$", observed)):
                raise InstallationNotReady("loopback and port settings were not confirmed")
            created.append(paths.unit)
            paths.unit.write_bytes(unit_bytes)
            paths.unit.chmod(0o644)
            created.append(paths.command)
            paths.command.write_bytes((paths.panel / "x-ui.sh").read_bytes())
            paths.command.chmod(0o755)
            _run(["systemctl", "daemon-reload"])
            service_enable_attempted = True
            _run(["systemctl", "enable", "x-ui"])
            service_start_attempted = True
            _run(["systemctl", "start", "x-ui"])
            for _ in range(20):
                try:
                    with socket.create_connection(("127.0.0.1", panel_port), timeout=1):
                        break
                except OSError:
                    time.sleep(1)
            else:
                raise InstallationNotReady("panel loopback listener did not become healthy")
            if _run(["systemctl", "is-active", "x-ui"]).strip() != "active":
                raise InstallationNotReady("panel service is not active")
            secrets_file = paths.database / "fork-credentials.json"
            _write_private_json(secrets_file, {"username": username, "password": password,
                                               "web_base_path": base_path, "port": panel_port})
            paths.state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            created.append(paths.state)
            _write_private_json(paths.state, {"schema": 1, "panel_version": "3.11.0",
                                              "panel_port": panel_port, "web_base_path": base_path,
                                              "status": "installed",
                                              "managed_paths": [str(p) for p in created],
                                              "hashes": {
                                                  "unit": file_digest(paths.unit),
                                                  "command": file_digest(paths.command),
                                                  "binary": file_digest(paths.panel / "x-ui")}})
            return {"panel_version": "3.11.0", "listen": "127.0.0.1",
                    "panel_port": panel_port, "credentials_file": str(secrets_file),
                    "state_file": str(paths.state)}
        except Exception:
            if service_start_attempted:
                subprocess.run(["systemctl", "stop", "x-ui"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if service_enable_attempted:
                subprocess.run(["systemctl", "disable", "x-ui"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for item in reversed(created):
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink(missing_ok=True)
            if paths.unit in created:
                subprocess.run(["systemctl", "daemon-reload"], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            raise
