"""Pinned upstream artifact acquisition. Host mutation still requires E2E gates."""

from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

from .compatibility import load_capabilities

MAX_ARCHIVE = 512 * 1024 * 1024
OFFICIAL_RELEASE = "https://github.com/MHSanaei/3x-ui/releases/download/v3.11.0"
INSTALLER_URL = ("https://raw.githubusercontent.com/MHSanaei/3x-ui/"
                 "c621ba9014a6aa21fd7c9ecf45655e44e24ebf13/install.sh")
INSTALLER_BLOB_SHA1 = "dd67e6c0935f5f1f1858ea5b4cef24107e91dc69"


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


def require_release_artifacts() -> None:
    raise InstallationNotReady(
        "installation is gated: isolated install, API and full rollback E2E are pending"
    )
