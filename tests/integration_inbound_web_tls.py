"""Real VLESS/VMess WebSocket TLS traffic against a disposable official panel."""

from __future__ import annotations

import base64
import http.server
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from integration_inbound_reality import ECHO_ADDRESS, Echo, safe_log_excerpt, token_from_cli, wait_port
from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, WebTlsSpec


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True, timeout=30)


def certificates(root: Path) -> tuple[Path, Path, Path]:
    ca_cert, ca_key = root / "ca.crt", root / "ca.key"
    cert, key, csr = root / "server.crt", root / "server.key", root / "server.csr"
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-noenc", "-days", "10",
        "-subj", "/CN=CI Test CA", "-addext", "basicConstraints=critical,CA:TRUE",
        "-keyout", str(ca_key), "-out", str(ca_cert))
    run("openssl", "req", "-new", "-newkey", "rsa:2048", "-noenc",
        "-subj", "/CN=ci.example.test", "-keyout", str(key), "-out", str(csr))
    extension = root / "server.ext"
    extension.write_text("subjectAltName=DNS:ci.example.test\n"
                         "extendedKeyUsage=serverAuth\n"
                         "basicConstraints=CA:FALSE\n", encoding="utf-8")
    run("openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_cert),
        "-CAkey", str(ca_key), "-CAcreateserial", "-days", "10",
        "-extfile", str(extension), "-out", str(cert))
    return ca_cert, cert, key


def client_config(spec: WebTlsSpec, client_id: str, ca_cert: Path, socks_port: int) -> dict:
    user = ({"id": client_id, "encryption": "none"} if spec.protocol == "vless"
            else {"id": client_id, "alterId": 0, "security": "auto"})
    return {
        "log": {"loglevel": "debug"},
        "inbounds": [{"tag": "ci-socks", "listen": "127.0.0.1", "port": socks_port,
                      "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}],
        "outbounds": [{"tag": "ci-web", "protocol": spec.protocol,
                       "settings": {"vnext": [{"address": "127.0.0.1", "port": spec.port,
                                               "users": [user]}]},
                       "streamSettings": {
                           "network": "ws", "security": "tls",
                           "wsSettings": {"path": spec.ws_path,
                                          "headers": {"Host": spec.server_name}},
                           "tlsSettings": {"serverName": spec.server_name,
                                           "alpn": ["http/1.1"],
                                           "disableSystemRoot": True,
                                           "certificates": [{"certificateFile": str(ca_cert),
                                                             "usage": "verify"}]}}}],
    }


def verify_link(link: str, spec: WebTlsSpec, client_id: str) -> None:
    if spec.protocol == "vless":
        parsed = urllib.parse.urlparse(link)
        query = urllib.parse.parse_qs(parsed.query)
        assert parsed.scheme == "vless" and parsed.username == client_id
        assert parsed.hostname == spec.public_address and parsed.port == spec.port
        assert query.get("type") == ["ws"] and query.get("security") == ["tls"]
        assert query.get("sni") == [spec.server_name]
        assert query.get("path") == [spec.ws_path]
    else:
        assert link.startswith("vmess://")
        payload = link.removeprefix("vmess://")
        decoded = base64.b64decode(payload + "=" * (-len(payload) % 4))
        profile = json.loads(decoded)
        assert profile["id"] == client_id and int(profile["port"]) == spec.port
        assert profile["net"] == "ws" and profile["tls"] == "tls"
        assert profile["path"] == spec.ws_path and profile["sni"] == spec.server_name


def verify_raw_subscription(api: ApiClient, sub_id: str, link: str) -> None:
    settings = api.read_post("setting/all")
    assert isinstance(settings, dict) and settings.get("subEnable") is True
    sub_path, sub_port = settings["subPath"], settings["subPort"]
    assert isinstance(sub_path, str) and sub_path.startswith("/") and sub_path.endswith("/")
    assert isinstance(sub_port, int) and 1 <= sub_port <= 65535
    with urllib.request.urlopen(f"http://127.0.0.1:{sub_port}{sub_path}{sub_id}",
                                timeout=10) as response:
        raw = response.read(2 * 1024 * 1024)
        assert response.status == 200
    if settings.get("subEncrypt"):
        raw = base64.b64decode(raw, validate=True)
    assert link.encode() in raw, "RAW subscription omits WebSocket TLS link"


def exercise(api: ApiClient, manager: InboundManager, xray: Path, ca: Path,
             cert: Path, key: Path, root: Path, profile: str, index: int) -> None:
    spec = WebTlsSpec(profile, "DE", "ci", 32220 + index, "127.0.0.1",
                      "ci.example.test", f"/ci-ws-{index}",
                      f"ci-web-{index}@example.test", cert, key)
    first = manager.ensure_websocket_tls(spec)
    assert first["created"], "fresh runner should create WebSocket TLS inbound"
    try:
        second = manager.ensure_websocket_tls(spec)
        assert not second["created"] and second["inbound_id"] == first["inbound_id"]
        detail = api.read(f"inbounds/get/{first['inbound_id']}")
        stream = normalize_embedded_json(detail["streamSettings"])
        assert stream["wsSettings"]["path"] == spec.ws_path
        assert stream["tlsSettings"]["serverName"] == spec.server_name
        record = api.read(f"clients/get/{spec.client_email}")
        client = record["client"]
        client_id = client["uuid"]
        links = api.read(f"clients/links/{spec.client_email}")
        assert isinstance(links, list) and len(links) == 1
        verify_link(links[0], spec, client_id)
        sub_links = api.read(f"clients/subLinks/{client['subId']}")
        assert links[0] in sub_links
        verify_raw_subscription(api, client["subId"], links[0])
        socks_port = 32230 + index
        config_path = root / f"client-{index}.json"
        config_path.write_text(json.dumps(client_config(spec, client_id, ca, socks_port)),
                               encoding="utf-8")
        log_path = root / f"xray-client-{index}.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(xray), "run", "-config", str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_port(socks_port)
                wait_port(spec.port)
                last = ""
                for _ in range(12):
                    result = subprocess.run(
                        ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                         "--noproxy", "", "--socks5-hostname", f"127.0.0.1:{socks_port}",
                         f"http://{ECHO_ADDRESS}:32280/"],
                        capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and result.stdout == Echo.marker:
                        break
                    last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                    time.sleep(1)
                else:
                    print(safe_log_excerpt(log_path.read_text(encoding="utf-8", errors="replace")))
                    raise AssertionError(f"{profile} traffic failed: {last}")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        print(f"{profile}: API, client, link, RAW subscription, verified TLS, traffic PASS")
    finally:
        api.post(f"clients/del/{spec.client_email}", {})
        api.post(f"inbounds/del/{first['inbound_id']}", {})


def main() -> None:
    if os.environ.get("XUI_RUN_INBOUND_WEB_E2E") != "1":
        raise RuntimeError("disposable WebSocket TLS E2E must be explicitly enabled")
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    api = ApiClient(f"http://127.0.0.1:{credentials['port']}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    xray = Path("/usr/local/x-ui/bin/xray-linux-amd64")
    manager = InboundManager(api, xray=xray)
    with tempfile.TemporaryDirectory(prefix="xui-web-e2e-") as directory:
        root = Path(directory)
        ca, cert, key = certificates(root)
        run("ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo")
        httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32280), Echo)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            exercise(api, manager, xray, ca, cert, key, root, "VLESS WebSocket TLS", 1)
            exercise(api, manager, xray, ca, cert, key, root, "VMess WebSocket TLS", 2)
        finally:
            httpd.shutdown()
            thread.join(timeout=5)
            run("ip", "address", "del", ECHO_ADDRESS + "/32", "dev", "lo")


if __name__ == "__main__":
    main()
