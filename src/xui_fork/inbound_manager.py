"""Version-gated inbound/client orchestration through the official REST API."""

from __future__ import annotations

import base64
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
from .ssl_manager import require_certificate


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


@dataclass(frozen=True)
class WebTlsSpec:
    profile: str
    country: str
    subdomain: str
    port: int
    public_address: str
    server_name: str
    ws_path: str
    client_email: str
    cert_file: Path
    key_file: Path

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    @property
    def protocol(self) -> str:
        return "vmess" if self.profile == "VMess WebSocket TLS" else "vless"

    @property
    def network(self) -> str:
        return "xhttp" if self.profile == "VLESS XHTTP TLS" else "ws"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if self.profile not in {"VLESS WebSocket TLS", "VMess WebSocket TLS",
                                "VLESS XHTTP TLS"}:
            raise InboundError(f"web TLS implementation unavailable: {self.profile}")
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535 or not DOMAIN.fullmatch(self.server_name)
                or not EMAIL.fullmatch(self.client_email)
                or not re.fullmatch(r"/[A-Za-z0-9/_-]{1,100}", self.ws_path)):
            raise ValueError("invalid WebSocket TLS inbound identity or transport")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc
        if not self.cert_file.is_absolute() or not self.key_file.is_absolute():
            raise ValueError("TLS certificate and key paths must be absolute")
        require_certificate(self.cert_file, self.key_file, self.server_name)


@dataclass(frozen=True)
class GrpcTlsSpec:
    country: str
    subdomain: str
    port: int
    public_address: str
    server_name: str
    service_name: str
    client_email: str
    cert_file: Path
    key_file: Path

    profile = "Trojan gRPC TLS"
    protocol = "trojan"
    network = "grpc"

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535 or not DOMAIN.fullmatch(self.server_name)
                or not EMAIL.fullmatch(self.client_email)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.service_name)):
            raise ValueError("invalid Trojan gRPC TLS inbound identity or transport")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc
        if not self.cert_file.is_absolute() or not self.key_file.is_absolute():
            raise ValueError("TLS certificate and key paths must be absolute")
        require_certificate(self.cert_file, self.key_file, self.server_name)


@dataclass(frozen=True)
class RealityXhttpSpec:
    country: str
    subdomain: str
    port: int
    public_address: str
    server_name: str
    reality_target: str
    xhttp_path: str
    client_email: str

    profile = "VLESS XHTTP REALITY"

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535 or not DOMAIN.fullmatch(self.server_name)
                or not DOMAIN.fullmatch(self.reality_target)
                or not EMAIL.fullmatch(self.client_email)
                or not re.fullmatch(r"/[A-Za-z0-9/_-]{1,100}", self.xhttp_path)):
            raise ValueError("invalid VLESS XHTTP REALITY inbound identity or transport")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc


@dataclass(frozen=True)
class MlkemTlsSpec:
    country: str
    subdomain: str
    port: int
    public_address: str
    server_name: str
    ws_path: str
    client_email: str
    cert_file: Path
    key_file: Path

    profile = "VLESS Encryption ML-KEM768"
    protocol = "vless"
    network = "xhttp"

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535 or not DOMAIN.fullmatch(self.server_name)
                or not EMAIL.fullmatch(self.client_email)
                or not re.fullmatch(r"/[A-Za-z0-9/_-]{1,100}", self.ws_path)):
            raise ValueError("invalid VLESS Encryption ML-KEM768 identity or transport")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc
        if not self.cert_file.is_absolute() or not self.key_file.is_absolute():
            raise ValueError("TLS certificate and key paths must be absolute")
        require_certificate(self.cert_file, self.key_file, self.server_name)


@dataclass(frozen=True)
class Shadowsocks2022Spec:
    country: str
    subdomain: str
    port: int
    public_address: str
    client_email: str

    profile = "Shadowsocks 2022"
    method = "2022-blake3-aes-256-gcm"

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535 or not EMAIL.fullmatch(self.client_email)):
            raise ValueError("invalid Shadowsocks 2022 inbound identity")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc


@dataclass(frozen=True)
class Hysteria2Spec:
    country: str
    subdomain: str
    port: int
    public_address: str
    server_name: str
    client_email: str
    cert_file: Path
    key_file: Path

    profile = "Hysteria2"

    @property
    def remark(self) -> str:
        return f"{self.country}-{self.subdomain} | {self.profile}"

    def validate(self, panel_version: str) -> None:
        validate_profile(self.profile, panel_version)
        if (not COUNTRY.fullmatch(self.country) or not SUBDOMAIN.fullmatch(self.subdomain)
                or not 1 <= self.port <= 65535 or not DOMAIN.fullmatch(self.server_name)
                or not EMAIL.fullmatch(self.client_email)):
            raise ValueError("invalid Hysteria2 inbound identity")
        if not DOMAIN.fullmatch(self.public_address):
            try:
                ipaddress.ip_address(self.public_address)
            except ValueError as exc:
                raise ValueError("public address must be a DNS name or IP address") from exc
        if not self.cert_file.is_absolute() or not self.key_file.is_absolute():
            raise ValueError("TLS certificate and key paths must be absolute")
        require_certificate(self.cert_file, self.key_file, self.server_name)


def _ss2022_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


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


def _reality_xhttp_payload(spec: RealityXhttpSpec, private_key: str,
                           public_key: str, short_id: str) -> dict:
    payload = _wire_payload(
        InboundSpec("VLESS REALITY Vision", spec.country, spec.subdomain, spec.port,
                    spec.public_address, spec.server_name, spec.reality_target,
                    spec.client_email), private_key, public_key, short_id)
    stream = normalize_embedded_json(payload["streamSettings"])
    stream.pop("tcpSettings")
    stream["network"] = "xhttp"
    stream["xhttpSettings"] = {"path": spec.xhttp_path, "host": spec.server_name,
                               "mode": "stream-up"}
    payload.update({"remark": spec.remark, "tag": f"in-{spec.port}-xhttp",
                    "disableFlow": True,
                    "streamSettings": json.dumps(stream, separators=(",", ":"))})
    return payload


def _web_tls_payload(spec: WebTlsSpec | GrpcTlsSpec | MlkemTlsSpec,
                     mlkem: tuple[str, str] | None = None) -> dict:
    if spec.protocol == "vless":
        settings = {"clients": [], "decryption": "none", "encryption": "none", "fallbacks": []}
        if isinstance(spec, MlkemTlsSpec):
            if mlkem is None:
                raise ValueError("ML-KEM768 keypair required")
            settings.pop("fallbacks")
            settings["decryption"], settings["encryption"] = mlkem
    elif spec.protocol == "trojan":
        settings = {"clients": [], "fallbacks": []}
    else:
        settings = {"clients": []}
    if spec.network == "grpc":
        transport = {"grpcSettings": {"serviceName": spec.service_name,
                                      "authority": spec.server_name, "multiMode": False}}
    elif spec.network == "xhttp":
        transport = {"xhttpSettings": {"path": spec.ws_path, "host": spec.server_name,
                                       "mode": "stream-up"}}
    else:
        transport = {"wsSettings": {"acceptProxyProtocol": False, "path": spec.ws_path,
                                    "host": spec.server_name, "headers": {},
                                    "heartbeatPeriod": 0}}
    stream = {
        "network": spec.network, "security": "tls", **transport,
        "tlsSettings": {"serverName": spec.server_name, "minVersion": "1.2",
                        "maxVersion": "1.3", "rejectUnknownSni": True,
                        "certificates": [{"certificateFile": str(spec.cert_file),
                                          "keyFile": str(spec.key_file),
                                          "usage": "encipherment"}],
                        "alpn": (["h2", "http/1.1"] if spec.network in {"xhttp", "grpc"}
                                 else ["http/1.1"]), "settings": {"fingerprint": ""}},
    }
    return {
        "up": 0, "down": 0, "total": 0, "remark": spec.remark,
        "enable": True, "expiryTime": 0, "trafficReset": "never",
        "trafficResetDay": 1, "lastTrafficResetTime": 0,
        "listen": "127.0.0.1", "port": spec.port, "protocol": spec.protocol,
        "settings": json.dumps(settings, separators=(",", ":")),
        "streamSettings": json.dumps(stream, separators=(",", ":")),
        "sniffing": json.dumps({"enabled": False}),
        "tag": f"in-{spec.port}-{spec.network}", "shareAddrStrategy": "custom",
        "shareAddr": spec.public_address, "subSortIndex": 1,
        "excludeFromSub": False, "disableFlow": True,
    }
def _inbounds(api: ApiClient) -> list[dict]:
    rows = api.read("inbounds/list")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise InboundError("unexpected inbound list response")
    return rows


def _matching(rows: list[dict], spec: InboundSpec | MixedSpec | WebTlsSpec |
              GrpcTlsSpec | RealityXhttpSpec | MlkemTlsSpec |
              Shadowsocks2022Spec | Hysteria2Spec) -> dict | None:
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


def _new_mlkem_auth(api: ApiClient) -> tuple[str, str]:
    response = api.read("server/getNewVlessEnc")
    auths = response.get("auths") if isinstance(response, dict) else None
    matches = [item for item in auths if isinstance(item, dict) and item.get("id") == "mlkem768"] if isinstance(auths, list) else []
    if len(matches) != 1:
        raise InboundError("official panel returned no unique ML-KEM768 authentication")
    auth = matches[0]
    decryption, encryption = auth.get("decryption"), auth.get("encryption")
    prefix = "mlkem768x25519plus.native."
    if (not isinstance(decryption, str) or not isinstance(encryption, str)
            or not decryption.startswith(prefix) or not encryption.startswith(prefix)
            or len(decryption) <= len(prefix) or len(encryption) <= len(prefix)):
        raise InboundError("official panel returned invalid ML-KEM768 key format")
    return decryption, encryption


class InboundManager:
    def __init__(self, api: ApiClient, *, panel_version: str = "3.11.0",
                 xray: Path | None = None):
        self.api = api
        self.panel_version = panel_version
        arch = "amd64" if platform.machine().lower() in {"x86_64", "amd64"} else "arm64"
        self.xray = xray or Path(f"/usr/local/x-ui/bin/xray-linux-{arch}")

    def ensure_websocket_tls(self, spec: WebTlsSpec, *, client_id: str | None = None) -> dict:
        if spec.network != "ws":
            raise InboundError("expected WebSocket TLS profile")
        return self._ensure_web_tls(spec, client_id=client_id)

    def ensure_xhttp_tls(self, spec: WebTlsSpec, *, client_id: str | None = None) -> dict:
        if spec.profile != "VLESS XHTTP TLS":
            raise InboundError("expected VLESS XHTTP TLS profile")
        return self._ensure_web_tls(spec, client_id=client_id)

    def ensure_trojan_grpc_tls(self, spec: GrpcTlsSpec) -> dict:
        return self._ensure_web_tls(spec)

    def ensure_mlkem_tls(self, spec: MlkemTlsSpec) -> dict:
        return self._ensure_web_tls(spec)

    def _ensure_web_tls(self, spec: WebTlsSpec | GrpcTlsSpec | MlkemTlsSpec,
                        *, client_id: str | None = None) -> dict:
        spec.validate(self.panel_version)
        self.api.verify_contract()
        rows = _inbounds(self.api)
        for row in rows:
            if row.get("port") == spec.port and row.get("remark") != spec.remark:
                raise InboundConflict("inbound port already belongs to another profile")
        existing = _matching(rows, spec)
        created = False
        expected_mlkem = None
        if existing is None:
            if isinstance(spec, MlkemTlsSpec):
                expected_mlkem = _new_mlkem_auth(self.api)
            try:
                self.api.post("inbounds/add", _web_tls_payload(spec, expected_mlkem))
            except ApiUncertainError:
                existing = _matching(_inbounds(self.api), spec)
                if existing is None:
                    raise
            else:
                created = True
            existing = _matching(_inbounds(self.api), spec)
            if existing is None:
                raise InboundError("TLS inbound write returned success but read-back is missing")
        inbound_id = existing.get("id")
        if not isinstance(inbound_id, int) or inbound_id < 1 or existing.get("protocol") != spec.protocol:
            raise InboundConflict("existing TLS inbound identity differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        if not isinstance(detail, dict) or detail.get("port") != spec.port:
            raise InboundError("TLS inbound detail read-back missing")
        stream = normalize_embedded_json(detail.get("streamSettings"))
        transport = stream.get(f"{spec.network}Settings", {}) if isinstance(stream, dict) else {}
        tls = stream.get("tlsSettings", {}) if isinstance(stream, dict) else {}
        transport_key = "serviceName" if spec.network == "grpc" else "path"
        transport_value = (spec.service_name if spec.network == "grpc" else spec.ws_path)
        if (not isinstance(stream, dict) or not isinstance(transport, dict)
                or not isinstance(tls, dict) or stream.get("network") != spec.network
                or stream.get("security") != "tls"
                or transport.get(transport_key) != transport_value
                or tls.get("serverName") != spec.server_name):
            raise InboundConflict("existing TLS transport differs")
        if isinstance(spec, MlkemTlsSpec):
            inbound_settings = normalize_embedded_json(detail.get("settings"))
            if not isinstance(inbound_settings, dict):
                raise InboundConflict("ML-KEM768 settings missing")
            observed = (inbound_settings.get("decryption"),
                        inbound_settings.get("encryption"))
            if (not all(isinstance(value, str) and
                        value.startswith("mlkem768x25519plus.native.") for value in observed)
                    or "fallbacks" in inbound_settings
                    or (expected_mlkem is not None and observed != expected_mlkem)):
                raise InboundConflict("ML-KEM768 authentication differs")
        record = _client_record(self.api, spec.client_email)
        if record is not None and client_id is None:
            field = "password" if spec.protocol == "trojan" else "uuid"
            client_id = record.get("client", record).get(field)
        client_id = client_id or (secrets.token_urlsafe(18) if spec.protocol == "trojan"
                                  else str(uuid.uuid4()))
        if spec.protocol != "trojan" and uuid.UUID(client_id).version != 4:
            raise ValueError("client_id must be a UUIDv4")
        if record is None:
            client = {"email": spec.client_email, "subId": secrets.token_hex(8), "enable": True,
                      "limitIp": 0, "totalGB": 0, "expiryTime": 0,
                      "tgId": 0, "comment": "", "reset": 0,
                      "resetDay": 0, "resetWeekday": 0, "resetMax": 0}
            if spec.protocol == "trojan":
                client["password"] = client_id
            else:
                client["id"] = client_id
                if spec.protocol == "vless":
                    client["flow"] = ""
                else:
                    client.update({"security": "auto", "alterId": 0})
            try:
                self.api.post("clients/add", {"client": client, "inboundIds": [inbound_id]})
            except ApiUncertainError:
                record = _client_record(self.api, spec.client_email)
                if record is None:
                    raise
            record = _client_record(self.api, spec.client_email)
        if record is None:
            raise InboundError("TLS client read-back missing")
        if spec.protocol == "trojan":
            observed = record.get("client", record)
            if (observed.get("email") != spec.client_email
                    or observed.get("password") != client_id
                    or inbound_id not in record.get("inboundIds", [])):
                raise InboundConflict("Trojan client identity or attachment differs")
        else:
            _verify_client(record, spec.client_email, client_id, inbound_id)
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        settings = normalize_embedded_json(detail.get("settings"))
        clients = settings.get("clients", []) if isinstance(settings, dict) else []
        identity_field = "password" if spec.protocol == "trojan" else "id"
        if not any(c.get("email") == spec.client_email and c.get(identity_field) == client_id
                   for c in clients if isinstance(c, dict)):
            raise InboundError("TLS backend settings omit client")
        links = self.api.read(f"clients/links/{spec.client_email}")
        if not isinstance(links, list) or not links:
            raise InboundError("TLS client share link missing")
        return {"inbound_id": inbound_id, "remark": spec.remark,
                "client_email": spec.client_email, "created": created,
                "links_verified": True}

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

    def ensure_hysteria2(self, spec: Hysteria2Spec) -> dict:
        spec.validate(self.panel_version)
        self.api.verify_contract()
        rows = _inbounds(self.api)
        for row in rows:
            if row.get("port") == spec.port and row.get("remark") != spec.remark:
                raise InboundConflict("inbound port already belongs to another profile")
        existing = _matching(rows, spec)
        created = False
        if existing is None:
            stream = {
                "network": "hysteria", "security": "tls",
                "hysteriaSettings": {"version": 2, "udpIdleTimeout": 60},
                "tlsSettings": {"serverName": spec.server_name,
                                "minVersion": "1.3", "maxVersion": "1.3",
                                "alpn": ["h3"], "rejectUnknownSni": True,
                                "certificates": [{"certificateFile": str(spec.cert_file),
                                                  "keyFile": str(spec.key_file),
                                                  "usage": "encipherment"}],
                                "settings": {"fingerprint": ""}},
            }
            payload = {"up": 0, "down": 0, "total": 0, "remark": spec.remark,
                       "enable": True, "expiryTime": 0, "trafficReset": "never",
                       "trafficResetDay": 1, "lastTrafficResetTime": 0,
                       "listen": "127.0.0.1", "port": spec.port,
                       "protocol": "hysteria",
                       "settings": json.dumps({"version": 2, "clients": []}),
                       "streamSettings": json.dumps(stream, separators=(",", ":")),
                       "sniffing": json.dumps({"enabled": False}),
                       "tag": f"in-{spec.port}-hysteria",
                       "shareAddrStrategy": "custom", "shareAddr": spec.public_address,
                       "subSortIndex": 1, "excludeFromSub": False,
                       "disableFlow": True}
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
                raise InboundError("Hysteria2 write returned success but read-back missing")
        inbound_id = existing.get("id")
        if (not isinstance(inbound_id, int) or inbound_id < 1
                or existing.get("protocol") != "hysteria"):
            raise InboundConflict("existing Hysteria2 inbound identity differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        settings = normalize_embedded_json(detail.get("settings")) if isinstance(detail, dict) else None
        stream = normalize_embedded_json(detail.get("streamSettings")) if isinstance(detail, dict) else None
        transport = stream.get("hysteriaSettings", {}) if isinstance(stream, dict) else {}
        tls = stream.get("tlsSettings", {}) if isinstance(stream, dict) else {}
        if (not isinstance(detail, dict) or detail.get("port") != spec.port
                or not isinstance(settings, dict) or settings.get("version") != 2
                or not isinstance(stream, dict) or not isinstance(transport, dict)
                or not isinstance(tls, dict) or stream.get("network") != "hysteria"
                or stream.get("security") != "tls" or transport.get("version") != 2
                or tls.get("serverName") != spec.server_name
                or "h3" not in tls.get("alpn", [])):
            raise InboundConflict("existing Hysteria2 transport differs")
        record = _client_record(self.api, spec.client_email)
        if record is None:
            client = {"auth": secrets.token_urlsafe(18),
                      "email": spec.client_email, "subId": secrets.token_hex(8),
                      "enable": True, "limitIp": 0, "totalGB": 0,
                      "expiryTime": 0, "tgId": 0, "comment": "",
                      "reset": 0, "resetDay": 0, "resetWeekday": 0, "resetMax": 0}
            try:
                self.api.post("clients/add", {"client": client, "inboundIds": [inbound_id]})
            except ApiUncertainError:
                record = _client_record(self.api, spec.client_email)
                if record is None:
                    raise
            record = _client_record(self.api, spec.client_email)
        if not isinstance(record, dict):
            raise InboundError("Hysteria2 client read-back missing")
        observed = record.get("client", record)
        auth = observed.get("auth") if isinstance(observed, dict) else None
        if (not isinstance(auth, str) or len(auth) < 16
                or observed.get("email") != spec.client_email
                or inbound_id not in record.get("inboundIds", [])):
            raise InboundConflict("Hysteria2 client identity or attachment differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        settings = normalize_embedded_json(detail.get("settings"))
        if not any(c.get("email") == spec.client_email and c.get("auth") == auth
                   for c in settings.get("clients", []) if isinstance(c, dict)):
            raise InboundError("Hysteria2 backend settings omit client")
        links = self.api.read(f"clients/links/{spec.client_email}")
        if not isinstance(links, list) or not links:
            raise InboundError("Hysteria2 share link missing")
        return {"inbound_id": inbound_id, "remark": spec.remark,
                "client_email": spec.client_email, "created": created,
                "links_verified": True}

    def ensure_shadowsocks_2022(self, spec: Shadowsocks2022Spec) -> dict:
        spec.validate(self.panel_version)
        self.api.verify_contract()
        rows = _inbounds(self.api)
        for row in rows:
            if row.get("port") == spec.port and row.get("remark") != spec.remark:
                raise InboundConflict("inbound port already belongs to another profile")
        existing = _matching(rows, spec)
        created = False
        if existing is None:
            settings = {"method": spec.method, "password": _ss2022_key(),
                        "network": "tcp,udp", "clients": [], "ivCheck": False}
            payload = {"up": 0, "down": 0, "total": 0, "remark": spec.remark,
                       "enable": True, "expiryTime": 0, "trafficReset": "never",
                       "trafficResetDay": 1, "lastTrafficResetTime": 0,
                       "listen": "127.0.0.1", "port": spec.port,
                       "protocol": "shadowsocks",
                       "settings": json.dumps(settings, separators=(",", ":")),
                       "streamSettings": json.dumps({"network": "tcp", "security": "none"}),
                       "sniffing": json.dumps({"enabled": False}),
                       "tag": f"in-{spec.port}-tcp", "shareAddrStrategy": "custom",
                       "shareAddr": spec.public_address, "subSortIndex": 1,
                       "excludeFromSub": False, "disableFlow": True}
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
                raise InboundError("Shadowsocks 2022 write returned success but read-back missing")
        inbound_id = existing.get("id")
        if (not isinstance(inbound_id, int) or inbound_id < 1
                or existing.get("protocol") != "shadowsocks"):
            raise InboundConflict("existing Shadowsocks 2022 inbound identity differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        settings = normalize_embedded_json(detail.get("settings")) if isinstance(detail, dict) else None
        stream = normalize_embedded_json(detail.get("streamSettings")) if isinstance(detail, dict) else None
        if (not isinstance(detail, dict) or detail.get("port") != spec.port
                or not isinstance(settings, dict) or not isinstance(stream, dict)
                or settings.get("method") != spec.method
                or settings.get("network") != "tcp,udp"
                or stream.get("network") != "tcp" or stream.get("security") != "none"):
            raise InboundConflict("existing Shadowsocks 2022 settings differ")
        server_key = settings.get("password")
        try:
            valid_server_key = len(base64.b64decode(server_key, validate=True)) == 32
        except (ValueError, TypeError):
            valid_server_key = False
        if not valid_server_key:
            raise InboundConflict("existing Shadowsocks 2022 server key invalid")
        record = _client_record(self.api, spec.client_email)
        if record is None:
            client = {"method": "", "password": _ss2022_key(),
                      "email": spec.client_email, "subId": secrets.token_hex(8),
                      "enable": True, "limitIp": 0, "totalGB": 0,
                      "expiryTime": 0, "tgId": 0, "comment": "",
                      "reset": 0, "resetDay": 0, "resetWeekday": 0, "resetMax": 0}
            try:
                self.api.post("clients/add", {"client": client, "inboundIds": [inbound_id]})
            except ApiUncertainError:
                record = _client_record(self.api, spec.client_email)
                if record is None:
                    raise
            record = _client_record(self.api, spec.client_email)
        if not isinstance(record, dict):
            raise InboundError("Shadowsocks 2022 client read-back missing")
        observed = record.get("client", record)
        client_key = observed.get("password") if isinstance(observed, dict) else None
        try:
            valid_client_key = len(base64.b64decode(client_key, validate=True)) == 32
        except (ValueError, TypeError):
            valid_client_key = False
        if (not valid_client_key or observed.get("email") != spec.client_email
                or inbound_id not in record.get("inboundIds", [])):
            raise InboundConflict("Shadowsocks 2022 client identity or attachment differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        settings = normalize_embedded_json(detail.get("settings"))
        if not any(c.get("email") == spec.client_email and c.get("password") == client_key
                   for c in settings.get("clients", []) if isinstance(c, dict)):
            raise InboundError("Shadowsocks 2022 backend settings omit client")
        links = self.api.read(f"clients/links/{spec.client_email}")
        if not isinstance(links, list) or not links:
            raise InboundError("Shadowsocks 2022 share link missing")
        return {"inbound_id": inbound_id, "remark": spec.remark,
                "client_email": spec.client_email, "created": created,
                "links_verified": True}

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

    def ensure_reality_xhttp(self, spec: RealityXhttpSpec,
                             *, client_id: str | None = None) -> dict:
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
            payload = _reality_xhttp_payload(spec, private, public, secrets.token_hex(8))
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
                raise InboundError("XHTTP REALITY write returned success but read-back is missing")
        inbound_id = existing.get("id")
        if not isinstance(inbound_id, int) or inbound_id < 1 or existing.get("protocol") != "vless":
            raise InboundConflict("existing XHTTP REALITY inbound identity differs")
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        stream = normalize_embedded_json(detail.get("streamSettings")) if isinstance(detail, dict) else None
        xhttp = stream.get("xhttpSettings", {}) if isinstance(stream, dict) else {}
        reality = stream.get("realitySettings", {}) if isinstance(stream, dict) else {}
        if (not isinstance(detail, dict) or detail.get("port") != spec.port
                or not isinstance(stream, dict) or not isinstance(xhttp, dict)
                or not isinstance(reality, dict)
                or stream.get("network") != "xhttp" or stream.get("security") != "reality"
                or xhttp.get("path") != spec.xhttp_path
                or xhttp.get("host") != spec.server_name
                or reality.get("target") != f"{spec.reality_target}:443"
                or spec.server_name not in reality.get("serverNames", [])):
            raise InboundConflict("existing XHTTP REALITY transport differs")
        record = _client_record(self.api, spec.client_email)
        if record is not None and client_id is None:
            client_id = record.get("client", record).get("uuid")
        client_id = client_id or str(uuid.uuid4())
        if uuid.UUID(client_id).version != 4:
            raise ValueError("client_id must be a UUIDv4")
        if record is None:
            client = {"id": client_id, "flow": "", "email": spec.client_email,
                      "subId": secrets.token_hex(8), "enable": True, "limitIp": 0,
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
            raise InboundError("XHTTP REALITY client read-back missing")
        _verify_client(record, spec.client_email, client_id, inbound_id)
        detail = self.api.read(f"inbounds/get/{inbound_id}")
        settings = normalize_embedded_json(detail.get("settings"))
        clients = settings.get("clients", []) if isinstance(settings, dict) else []
        if not any(c.get("email") == spec.client_email and c.get("id") == client_id
                   for c in clients if isinstance(c, dict)):
            raise InboundError("XHTTP REALITY backend settings omit client")
        links = self.api.read(f"clients/links/{spec.client_email}")
        if not isinstance(links, list) or not links:
            raise InboundError("XHTTP REALITY client share link missing")
        return {"inbound_id": inbound_id, "remark": spec.remark,
                "client_email": spec.client_email, "created": created,
                "links_verified": True}
