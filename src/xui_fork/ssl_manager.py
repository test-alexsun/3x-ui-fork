"""Certificate input validation. Issuance is not enabled without ACME E2E tests."""

from pathlib import Path


def require_certificate(cert: Path, key: Path) -> None:
    if not cert.is_file() or not key.is_file():
        raise ValueError("certificate and key files are required")
