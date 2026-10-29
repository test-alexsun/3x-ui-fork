"""Minimal bearer API adapter; read-only paths are explicitly allowlisted."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request


class ApiError(RuntimeError):
    pass


READ_PATHS = frozenset({"inbounds/list", "clients/list", "server/status"})


class ApiClient:
    def __init__(self, origin: str, token: str, base_path: str = "", timeout: float = 10):
        parsed = urllib.parse.urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise ValueError("origin must be an HTTP(S) origin without a path")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("bearer token requires TLS for remote API")
        if not token:
            raise ValueError("existing bearer token required")
        self.origin = origin.rstrip("/")
        if any(part in {".", ".."} for part in base_path.split("/")) or "?" in base_path:
            raise ValueError("invalid web base path")
        self.base_path = base_path.strip("/")
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "ApiClient":
        return cls(os.environ["XUI_API_ORIGIN"], os.environ["XUI_API_TOKEN"],
                   os.environ.get("XUI_WEB_BASE_PATH", ""))

    def read(self, path: str) -> object:
        if path not in READ_PATHS:
            raise ApiError(f"read path is not allowlisted: {path}")
        suffix = "/".join(p for p in (self.base_path, "panel", "api", path) if p)
        url = f"{self.origin}/{suffix}"
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=ssl.create_default_context()) as response:
                data = json.load(response)
        except (urllib.error.URLError, ValueError) as exc:
            raise ApiError(f"API read failed for {path}: {type(exc).__name__}") from exc
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ApiError(f"API rejected {path}")
        return data.get("obj")


def normalize_embedded_json(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value
