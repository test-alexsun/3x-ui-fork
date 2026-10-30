"""Disposable GitHub runner E2E for official VLESS REALITY Vision."""

from __future__ import annotations

import base64
import http.server
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, InboundSpec, MixedSpec


class Echo(http.server.BaseHTTPRequestHandler):
    marker = uuid.uuid4().hex

    def do_GET(self):
        body = self.marker.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


# Official 3x-ui blocks geoip:private by default. A public IP assigned to the
# disposable runner's loopback lets us test traffic without weakening that rule.
ECHO_ADDRESS = "8.8.8.8"


def wait_port(port: int, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise AssertionError(f"loopback port {port} did not become ready")


def token_from_cli(binary: Path) -> str:
    output = subprocess.run([str(binary), "setting", "-getApiToken"], check=True,
                            capture_output=True, text=True, timeout=20).stdout
    match = re.search(r"(?m)^apiToken:\s*(\S+)\s*$", output)
    if match is None:
        raise AssertionError("official CLI did not return an API token")
    return match.group(1)


def safe_log_excerpt(text: str) -> str:
    selected = "\n".join(text.splitlines()[-80:])[-6500:]
    selected = re.sub(r"[A-Za-z0-9_-]{40,}", "[redacted]", selected)
    return re.sub(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b",
                  "[redacted-uuid]", selected)


def main() -> None:
    if os.environ.get("XUI_RUN_INBOUND_E2E") != "1":
        raise RuntimeError("disposable inbound E2E must be explicitly enabled")
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    port = credentials["port"]
    xray = Path("/usr/local/x-ui/bin/xray-linux-amd64")
    api = ApiClient(f"http://127.0.0.1:{port}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    spec = InboundSpec("VLESS REALITY Vision", "DE", "ci", 32121, "127.0.0.1",
                       "www.cloudflare.com", "www.cloudflare.com", "ci-reality@example.test")
    manager = InboundManager(api, xray=xray)
    created = False
    try:
        first = manager.ensure_reality_vision(spec)
        created = first["created"]
        assert created, "fresh runner should create a new inbound"
        second = manager.ensure_reality_vision(spec)
        assert not second["created"] and second["inbound_id"] == first["inbound_id"]
        detail = api.read(f"inbounds/get/{first['inbound_id']}")
        stream = normalize_embedded_json(detail["streamSettings"])
        reality = stream["realitySettings"]
        record = api.read(f"clients/get/{spec.client_email}")
        client = record.get("client", record)
        client_id = client["uuid"]
        sub_links = api.read(f"clients/subLinks/{client['subId']}")
        assert isinstance(sub_links, list) and any(
            isinstance(link, str) and link.startswith("vless://") for link in sub_links)
        settings = api.read_post("setting/all")
        assert isinstance(settings, dict) and settings.get("subEnable") is True
        sub_path = settings["subPath"]
        sub_port = settings["subPort"]
        assert isinstance(sub_path, str) and sub_path.startswith("/") and sub_path.endswith("/")
        assert isinstance(sub_port, int) and 1 <= sub_port <= 65535
        subscription_url = f"http://127.0.0.1:{sub_port}{sub_path}{client['subId']}"
        with urllib.request.urlopen(subscription_url, timeout=10) as response:
            raw_subscription = response.read(2 * 1024 * 1024)
            assert response.status == 200
        if settings.get("subEncrypt"):
            raw_subscription = base64.b64decode(raw_subscription, validate=True)
        assert any(link.encode() in raw_subscription for link in sub_links), (
            "RAW subscription omits official client link")
        short_id = reality["shortIds"][0]
        public_key = reality["settings"]["publicKey"]
        config = {
            "log": {"loglevel": "debug"},
            "inbounds": [{"tag": "ci-socks", "listen": "127.0.0.1", "port": 32122,
                          "protocol": "socks", "settings": {"auth": "noauth", "udp": False}}],
            "outbounds": [{"tag": "ci-vless", "protocol": "vless",
                           "settings": {"vnext": [{"address": "127.0.0.1", "port": spec.port,
                                                   "users": [{"id": client_id,
                                                              "encryption": "none",
                                                              "flow": "xtls-rprx-vision"}]}]},
                           "streamSettings": {"network": "tcp", "security": "reality",
                                              "realitySettings": {
                                                  "serverName": spec.server_name,
                                                  "fingerprint": "chrome",
                                                  "publicKey": public_key,
                                                  "shortId": short_id,
                                                  "spiderX": "/"}}}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "client.json"
            config_file.write_text(json.dumps(config), encoding="utf-8")
            subprocess.run(["ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo"],
                           check=True, capture_output=True, timeout=10)
            httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32180), Echo)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            with (root / "xray-client.log").open("wb") as log:
                process = subprocess.Popen([str(xray), "run", "-config", str(config_file)],
                                           stdout=log, stderr=subprocess.STDOUT)
                try:
                    wait_port(32122)
                    wait_port(spec.port)
                    last = ""
                    for _ in range(20):
                        result = subprocess.run(
                            ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                             "--noproxy", "", "--socks5-hostname", "127.0.0.1:32122",
                             f"http://{ECHO_ADDRESS}:32180/"],
                            capture_output=True, text=True, timeout=10)
                        if result.returncode == 0 and result.stdout == Echo.marker:
                            break
                        last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                        time.sleep(1)
                    else:
                        client_log = safe_log_excerpt((root / "xray-client.log").read_text(
                            encoding="utf-8", errors="replace"))
                        panel_log = subprocess.run(
                            ["journalctl", "-u", "x-ui", "-n", "100", "--no-pager"],
                            capture_output=True, text=True, timeout=10)
                        print("Xray client diagnostics:\n" + client_log)
                        print("Panel Xray diagnostics:\n" + safe_log_excerpt(panel_log.stdout))
                        raise AssertionError(f"VLESS REALITY client traffic failed: {last}")
                    mixed = MixedSpec("DE", "ci", 32124, "ciuser123", "ci-" + uuid.uuid4().hex)
                    mixed_first = manager.ensure_mixed(mixed)
                    assert mixed_first["created"]
                    try:
                        mixed_second = manager.ensure_mixed(mixed)
                        assert not mixed_second["created"]
                        wait_port(mixed.port)
                        for proxy_args in (
                            ["--socks5-hostname", f"127.0.0.1:{mixed.port}"],
                            ["--proxy", f"http://127.0.0.1:{mixed.port}"],
                        ):
                            result = subprocess.run(
                                ["curl", "--silent", "--show-error", "--fail", "--max-time", "10",
                                 "--noproxy", "", "--proxy-user",
                                 f"{mixed.username}:{mixed.password}", *proxy_args,
                                 f"http://{ECHO_ADDRESS}:32180/"],
                                capture_output=True, text=True, timeout=12)
                            assert result.returncode == 0 and result.stdout == Echo.marker, (
                                f"Mixed traffic failed: curl exit={result.returncode}: "
                                f"{result.stderr.strip()}")
                    finally:
                        api.post(f"inbounds/del/{mixed_first['inbound_id']}", {})
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    httpd.shutdown()
                    thread.join(timeout=5)
                    subprocess.run(["ip", "address", "del", ECHO_ADDRESS + "/32",
                                    "dev", "lo"], check=True, capture_output=True, timeout=10)
        print("VLESS REALITY Vision API, client, share link, RAW subscription, "
              "idempotence and traffic: PASS")
        print("Mixed SOCKS5/HTTP API, account, idempotence and both proxy modes: PASS")
    finally:
        if created:
            api.post(f"clients/del/{spec.client_email}", {})
            api.post(f"inbounds/del/{first['inbound_id']}", {})


if __name__ == "__main__":
    main()
