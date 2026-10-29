"""Certificate/key consistency and SAN/expiry checks before Nginx apply."""

from __future__ import annotations

import ssl
import time
from pathlib import Path


class CertificateError(RuntimeError):
    pass


def require_certificate(cert: Path, key: Path, hostname: str,
                        min_valid_seconds: int = 7 * 86400) -> None:
    if not cert.is_file() or not key.is_file():
        raise CertificateError("certificate and key files are required")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(str(cert), str(key))
        details = ssl._ssl._test_decode_cert(str(cert))  # stdlib's PEM decoder
    except (ssl.SSLError, ValueError, OSError) as exc:
        raise CertificateError("certificate, key, or hostname validation failed") from exc
    dns_names = {value.lower() for kind, value in details.get("subjectAltName", ())
                 if kind == "DNS"}
    if hostname.lower() not in dns_names:
        raise CertificateError("certificate SAN does not include the exact hostname")
    expires = details.get("notAfter")
    if not expires or ssl.cert_time_to_seconds(expires) <= time.time() + min_valid_seconds:
        raise CertificateError("certificate expires too soon")
