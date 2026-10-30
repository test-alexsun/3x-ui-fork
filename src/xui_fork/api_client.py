"""Minimal bearer API adapter; read-only paths are explicitly allowlisted."""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request


class ApiError(RuntimeError):
    pass


class ApiUncertainError(ApiError):
    """The server may have applied a write before the connection failed."""


READ_PATHS = frozenset({"inbounds/list", "clients/list", "server/status"})
READ_POST_PATHS = frozenset({"setting/all"})
READ_DYNAMIC = re.compile(
    r"^(?:inbounds/get/[1-9][0-9]*|clients/(?:get|links)/[A-Za-z0-9_.+@-]+|"
    r"clients/subLinks/[A-Za-z0-9_-]+)$"
)
WRITE_PATHS = frozenset({"inbounds/add", "clients/add"})
WRITE_DYNAMIC = re.compile(r"^(?:inbounds/del/[1-9][0-9]*|clients/del/[A-Za-z0-9_.+@-]+)$")
OPENAPI_SHA256_311 = "e26231888ccd904831f1bc3440d6e6faecaf721c4550daaaa2eb24abac58625f"
OPENAPI_CANONICAL_SHA256_311 = "e0ca650cd432f8ae7d7ed8d92093bbeae6109a1af2810291c65a055ff6ff722e"
MAX_RESPONSE = 8 * 1024 * 1024
REQUIRED_OPERATIONS = {
    "inbounds/list": "get", "inbounds/get/{id}": "get",
    "inbounds/add": "post", "inbounds/del/{id}": "post",
    "clients/list": "get", "clients/get/{email}": "get",
    "clients/links/{email}": "get", "clients/add": "post",
    "clients/del/{email}": "post",
    "setting/all": "post",
}


def _verify_openapi_shape(document: object) -> None:
    """Check the API surface we use; live specs may contain a random web base path."""
    if not isinstance(document, dict) or document.get("openapi") != "3.0.3":
        raise ApiError("panel OpenAPI is not the tested 3.0.3 format")
    info = document.get("info")
    if not isinstance(info, dict) or info.get("version") != "3.x":
        raise ApiError("panel OpenAPI has an unexpected API version")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ApiError("panel OpenAPI has no path catalog")
    for suffix, method in REQUIRED_OPERATIONS.items():
        matches = [operations for path, operations in paths.items()
                   if path.endswith("/panel/api/" + suffix)]
        if len(matches) != 1 or not isinstance(matches[0], dict) or method not in matches[0]:
            raise ApiError(f"panel OpenAPI lacks {method.upper()} {suffix}")
    components = document.get("components", {})
    schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
    if not isinstance(schemas, dict):
        raise ApiError("panel OpenAPI has no schemas")
    inbound = schemas.get("Inbound", {})
    properties = inbound.get("properties", {}) if isinstance(inbound, dict) else {}
    required = {"id", "listen", "port", "protocol", "remark", "settings",
                "streamSettings", "sniffing", "shareAddr", "shareAddrStrategy"}
    if not isinstance(properties, dict) or not required.issubset(properties):
        raise ApiError("panel OpenAPI inbound schema changed")
    protocol = properties["protocol"]
    if not isinstance(protocol, dict) or "vless" not in protocol.get("enum", []):
        raise ApiError("panel OpenAPI no longer exposes VLESS inbounds")
    client = schemas.get("Client", {})
    fields = client.get("properties", {}) if isinstance(client, dict) else {}
    if not isinstance(fields, dict) or not {"id", "email", "flow", "subId"}.issubset(fields):
        raise ApiError("panel OpenAPI client schema changed")


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

    def _url(self, path: str) -> str:
        suffix = "/".join(p for p in (self.base_path, "panel", "api", path) if p)
        return f"{self.origin}/{suffix}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> bytes:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self._url(path), data=data, headers=headers,
                                         method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=ssl.create_default_context()) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            if method != "GET":
                raise ApiUncertainError(f"API write HTTP {exc.code} at {path}; reconcile") from exc
            raise ApiError(f"API HTTP {exc.code} at {path}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if method != "GET":
                raise ApiUncertainError(f"API write result uncertain at {path}") from exc
            raise ApiError(f"API read failed at {path}: {type(exc).__name__}") from exc
        if len(raw) > MAX_RESPONSE:
            raise ApiError("API response exceeds size limit")
        return raw

    def read(self, path: str) -> object:
        if path not in READ_PATHS and not READ_DYNAMIC.fullmatch(path):
            raise ApiError(f"read path is not allowlisted: {path}")
        try:
            data = json.loads(self._request("GET", path))
        except ValueError as exc:
            raise ApiError(f"invalid API JSON at {path}") from exc
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ApiError(f"API rejected {path}")
        return data.get("obj")

    def read_post(self, path: str) -> object:
        """Official API uses POST for a few read-only endpoints."""
        if path not in READ_POST_PATHS:
            raise ApiError(f"read-only POST path is not allowlisted: {path}")
        try:
            raw = self._request("POST", path, {})
            data = json.loads(raw)
        except ApiUncertainError as exc:
            raise ApiError(f"API read failed at {path}") from exc
        except ValueError as exc:
            raise ApiError(f"invalid API JSON at {path}") from exc
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ApiError(f"API rejected {path}")
        return data.get("obj")

    def verify_contract(self) -> bool:
        body = self._request("GET", "openapi.json")
        actual = hashlib.sha256(body).hexdigest()
        if actual == OPENAPI_SHA256_311:
            return True
        document = None
        try:
            document = json.loads(body)
            canonical = json.dumps(document, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
            canonical_hash = hashlib.sha256(canonical).hexdigest()
            kind = document.get("openapi", "other JSON") if isinstance(document, dict) else "JSON array"
        except ValueError:
            canonical_hash = "invalid"
            kind = "non-JSON"
        if canonical_hash != OPENAPI_CANONICAL_SHA256_311:
            try:
                _verify_openapi_shape(document)
            except ApiError as exc:
                raise ApiError(f"panel OpenAPI differs from tested 3.11.0 contract "
                               f"(raw SHA-256 {actual}; canonical {canonical_hash}; "
                               f"response {kind}): {exc}") from exc
        return True

    def post(self, path: str, payload: dict) -> object:
        if path not in WRITE_PATHS and not WRITE_DYNAMIC.fullmatch(path):
            raise ApiError(f"write path is not allowlisted: {path}")
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")
        try:
            data = json.loads(self._request("POST", path, payload))
        except ValueError as exc:
            raise ApiUncertainError(f"invalid write response at {path}") from exc
        if not isinstance(data, dict) or data.get("success") is not True:
            raise ApiUncertainError(f"API write failed or partly applied at {path}; reconcile before retry")
        return data.get("obj")


def normalize_embedded_json(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value
