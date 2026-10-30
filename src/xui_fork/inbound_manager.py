"""Version-gated inbound/client orchestration through the official REST API.

The first implemented profile is VLESS REALITY Vision. Other upstream profiles
remain explicitly unimplemented until their wire payloads and traffic are tested.
"""

from __future__ import annotations

import ipaddress
import json
import platform
import re
import secrets
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .api_client import ApiClient, ApiUncertainError, normalize_embedded_json
from .compatibility import profile_supported


class InboundError(RuntimeError):
    pass


class InboundConflict(InboundError):
    pass


COUNTRY = re.compile(r"[A-Z]{2}")
SUBDOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+")
EMAIL = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+")


def validate_profile(name: str, panel_version: str) -> None:
    if not profile_supported(name, panel_version):
        raise ValueError("unsupported profile/version tuple")


@dataclass(frozen=True)
class InboundSpec:
    profile: str
    country: str
    subdomain: str
    port: int
    public_address: str
    server_name: str
    reality_target: str
    client_email: str
    listen: str = "127.0.0.1"

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if self.profile != "VLESS REALITY Vision":
            raise InboundError(f"profile wire implementation unavailable: {self.profile}")
        if (not COUNTRY.fullmatch(self.country) or
                not SUBDOMAIN.fullmatch(self.subdomain) or
                not 1 <= self.port <= 65535 or
                not DOMAIN.fullmatch(self.server_name) or
                not DOMAIN.fullmatch(self.reality_target) or
                not EMAIL.fullmatch(self.client_email)):
            raise ValueError("invalid inbound identity, port, domain or client email")
        if self.listen != "127.0.0.1":
            raise ValueError("initial managed inbound must bind loopback")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc


@dataclass(frozen=True)
class MixedSpec:
    country: str
    subdomain: str
    port: int
    username: str
    password: str

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | Mixed SOCKS5/HTTP"

    def validate(self, panel_version: str) -> None:
        validate_profile("Mixed SOCKS5/HTTP", panel_version)
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535
                or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", self.username)
                or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", self.password)):
            raise ValueError("invalid Mixed inbound identity or account")


def generate_reality_keypair(xray: Path) -> tuple[str, str]:
    if not xray.is_file():
        raise InboundError("pinned Xray binary is unavailable")
    result = subprocess.run([str(xray), "x25519"], check=True, text=True,
                            capture_output=True, timeout=20)
    values = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            label = key.strip().lower().replace(" ", "")
            if label in {"privatekey", "publickey", "password", "password(publickey)"}:
                values[label] = value.strip()
    private = values.get("privatekey")
    public = (values.get("publickey") or values.get("password") or
              values.get("password(publickey)"))
    if not private or not public or not all(re.fullmatch(r"[A-Za-z0-9_-]{43,44}", x)
                                         for x in (private, public)):
        raise InboundError("Xray returned no usable REALITY X25519 keypair")
    return private, public


def _wire_payload(spec: InboundSpec, private_key: str, public_key: str,
                  short_id: str) -> dict:
    settings = {"clients": [], "decryption": "none", "encryption": "none", "fallbacks": []}
    stream = {
        "network": "tcp", "security": "reality", "tcpSettings": {},
        "realitySettings": {
            "show": False, "xver": 0, "target": f"{spec.reality_target}:443",
            "serverNames": [spec.server_name], "privateKey": private_key,
            "shortIds": [short_id],
            "settings": {"publicKey": public_key, "fingerprint": "chrome",
                         "serverName": spec.server_name, "spiderX": "/"},
        },
    }
    return {
        "up": 0, "down": 0, "total": 0, "remark": spec.remark,
        "enable": True, "expiryTime": 0, "trafficReset": "never",
        "trafficResetDay": 1, "lastTrafficResetTime": 0,
        "listen": spec.listen, "port": spec.port, "protocol": "vless",
        "settings": json.dumps(settings, separators=(",", ":")),
        "streamSettings": json.dumps(stream, separators=(",", ":")),
        "sniffing": json.dumps({"enabled": False}),
        "tag": f"in-{spec.port}-tcp", "shareAddrStrategy": "custom",
        "shareAddr": spec.public_address, "subSortIndex": 1,
        "excludeFromSub": False, "disableFlow": False,
    }


def _inbounds(api: ApiClient) -> list[dict]:
    rows = api.read("inbounds/list")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise InboundError("unexpected inbound list response")
    return rows


def _matching(rows: list[dict], spec: InboundSpec | MixedSpec) -> dict | None:
    matches = [row for row in rows if row.get("remark") == spec.remark]
    if len(matches) > 1:
        raise InboundConflict("multiple inbounds share the managed remark")
    return matches[0] if matches else None


def _verify_inbound(row: dict, spec: InboundSpec) -> int:
    if row.get("protocol") != "vless" or row.get("port") != spec.port:
        raise InboundConflict("existing inbound has different protocol or port")
    stream = normalize_embedded_json(row.get("streamSettings"))
    if not isinstance(stream, dict) or stream.get("network") != "tcp" or stream.get("security") != "reality":
        raise InboundConflict("existing inbound has incompatible transport/security")
    inbound_id = row.get("id")
    if not isinstance(inbound_id, int) or inbound_id < 1:
        raise InboundError("inbound response lacks valid ID")
    return inbound_id


def _client_record(api: ApiClient, email: str) -> dict | None:
    rows = api.read("clients/list")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise InboundError("unexpected client list response")
    if not any(row.get("email") == email for row in rows):
        return None
    result = api.read(f"clients/get/{email}")
    if not isinstance(result, dict):
        return None
    return result


def _verify_client(record: dict, email: str, client_id: str, inbound_id: int) -> None:
    client = record.get("client", record)
    if not isinstance(client, dict) or client.get("email") != email:
        raise InboundError("client read-back does not match email")
    # The client registry exposes a numeric database id and a separate Xray UUID.
    actual_id = client.get("uuid")
    if actual_id != client_id:
        raise InboundConflict("existing client identity differs from requested UUID")
    links = record.get("inboundIds", [])
    if inbound_id not in links:
        raise InboundError("client was not attached to created inbound")


class InboundManager:
    def __init__(self, api: ApiClient, *, panel_version: str = "3.11.0",
                 xray: Path | None = None):
        self.api = api
        self.panel_version = panel_version
        arch = "amd64" if platform.machine().lower() in {"x86_64", "amd64"} else "arm64"
        self.xray = xray or Path(f"/usr/local/x-ui/bin/xray-linux-{arch}")

    def ensure_mixed(self, spec: MixedSpec) -> dict:
        spec.validate(self.panel_version)
        self.api.verify_contract()
        rows = _inbounds(self.api)
        for row in rows:
            if row.get("port") == spec.port and row.get("remark") != spec.remark:
                raise InboundConflict("inbound port already belongs to another profile")
        existing = _matching(rows, spec)
        created = False
        if existing is None:
            payload = {
                "up": 0, "down": 0, "total": 0, "remark": spec.remark,
                "enable": True, "expiryTime": 0, "trafficReset": "never",
                "trafficResetDay": 1, "lastTrafficResetTime": 0,
                "listen": "127.0.0.1", "port": spec.port, "protocol": "mixed",
                "settings": json.dumps({"auth": "password", "accounts": [
                    {"user": spec.username, "pass": spec.password}],
                    "udp": False, "ip": "127.0.0.1"}, separators=(",", ":")),
                "streamSettings": json.dumps({"network": "tcp", "security": "none"}),
                "sniffing": json.dumps({"enabled": False}),
                "tag": f"in-{spec.port}-tcp", "shareAddrStrategy": "listen",
                "shareAddr": "", "subSortIndex": 1, "excludeFromSub": True,
                "disableFlow": True,
            }
            try:
                self.api.post("inbounds/add", payload)
            except ApiUncertainError:
                existing = _matching(_inbounds(self.api), spec)
                if existing is None:
                    raise
            else:
                created = True
            existing = _matching(_inbounds(self.api), spec)
            if existing is None:
                raise InboundError("Mixed write returned success but read-back is missing")
        inbound_id = existing.get("id")
        if not isinstance(inbound_id, int) or inbound_id < 1 or existing.get("protocol") != "mixed":
            raise InboundConflict("existing Mixed inbound identity differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        if not isinstance(detail, dict) or detail.get("port") != spec.port:
            raise InboundError("Mixed inbound detail read-back missing")
        settings = normalize_embedded_json(detail.get("settings"))
        if (not isinstance(settings, dict) or settings.get("auth") != "password"
                or {"user": spec.username, "pass": spec.password} not in settings.get("accounts", [])):
            raise InboundConflict("existing Mixed account differs")
        return {"inbound_id": inbound_id, "remark": spec.remark, "created": created,
                "account_verified": True}

    def ensure_reality_vision(self, spec: InboundSpec, *, client_id: str | None = None) -> dict:
        spec.validate(self.panel_version)
        self.api.verify_contract()
        rows = _inbounds(self.api)
        for row in rows:
            if row.get("port") == spec.port and row.get("remark") != spec.remark:
                raise InboundConflict("inbound port already belongs to another profile")
        existing = _matching(rows, spec)
        created = False
        if existing is None:
            private, public = generate_reality_keypair(self.xray)
            short_id = secrets.token_hex(8)
            payload = _wire_payload(spec, private, public, short_id)
            try:
                self.api.post("inbounds/add", payload)
            except ApiUncertainError:
                # A timeout can occur after commit. Reconcile; never retry POST blindly.
                existing = _matching(_inbounds(self.api), spec)
                if existing is None:
                    raise
            else:
                created = True
            existing = _matching(_inbounds(self.api), spec)
            if existing is None:
                raise InboundError("inbound write returned success but read-back is missing")
        inbound_id = _verify_inbound(existing, spec)
        record = _client_record(self.api, spec.client_email)
        if record is not None and client_id is None:
            existing_client = record.get("client", record)
            client_id = existing_client.get("uuid")
        client_id = client_id or str(uuid.uuid4())
        if uuid.UUID(client_id).version != 4:
            raise ValueError("client_id must be a UUIDv4")
        if record is None:
            sub_id = secrets.token_urlsafe(12).replace("-", "a").replace("_", "b")[:16]
            client = {"id": client_id, "flow": "xtls-rprx-vision",
                      "email": spec.client_email, "subId": sub_id,
                      "enable": True, "security": "", "limitIp": 0,
                      "totalGB": 0, "expiryTime": 0, "tgId": 0,
                      "comment": "", "reset": 0, "resetDay": 0,
                      "resetWeekday": 0, "resetMax": 0}
            try:
                self.api.post("clients/add", {"client": client, "inboundIds": [inbound_id]})
            except ApiUncertainError:
                record = _client_record(self.api, spec.client_email)
                if record is None:
                    raise
            record = _client_record(self.api, spec.client_email)
        if record is None:
            raise InboundError("client write returned success but read-back is missing")
        _verify_client(record, spec.client_email, client_id, inbound_id)
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        if not isinstance(detail, dict):
            raise InboundError("inbound detail read-back missing")
        settings = normalize_embedded_json(detail.get("settings"))
        clients = settings.get("clients", []) if isinstance(settings, dict) else []
        if not any(c.get("email") == spec.client_email and c.get("id") == client_id
                   for c in clients if isinstance(c, dict)):
            raise InboundError("inbound backend settings omit created client")
        links = self.api.read(f"clients/links/{spec.client_email}")
        if not links:
            raise InboundError("official panel returned no client connection link")
        return {"inbound_id": inbound_id, "remark": spec.remark,
                "client_email": spec.client_email, "created": created,
                "links_verified": True}
