"""MASQUE CONNECT-IP over HTTP/3/TLS through panel, Xray, TCP and UDP."""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from integration_inbound_reality import (
    ECHO_ADDRESS,
    Echo,
    safe_log_excerpt,
    token_from_cli,
    wait_port,
)
from integration_inbound_shadowsocks2022 import udp_echo, verify_udp
from integration_inbound_web_tls import certificates, run

from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, MasqueSpec


def wait_backend_user(port: int, email: str) -> None:
    config_file = Path("/usr/local/x-ui/bin/config.json")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.5)
            continue
        matches = [row for row in config.get("inbounds", []) if row.get("port") == port]
        if len(matches) == 1 and matches[0].get("protocol") == "masque":
            settings = normalize_embedded_json(matches[0].get("settings", {}))
            users = settings.get("clients", settings.get("users", []))
            if any(c.get("email") == email for c in users if isinstance(c, dict)):
                return
        time.sleep(0.5)
    raise AssertionError("MASQUE client not present in generated Xray config")


def exercise_traffic(xray: Path, config: dict, root: Path) -> None:
    config_path = root / "client.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    run("ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo")
    httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32295), Echo)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.bind((ECHO_ADDRESS, 32296))
    stop = threading.Event()
    udp_thread = threading.Thread(target=udp_echo, args=(udp_server, stop), daemon=True)
    udp_thread.start()
    try:
        log_path = root / "xray-client.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(xray), "run", "-config", str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_port(32242)
                last = ""
                for _ in range(25):
                    result = subprocess.run(
                        ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                         "--noproxy", "", "--socks5-hostname", "127.0.0.1:32242",
                         f"http://{ECHO_ADDRESS}:32295/"],
                        capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and result.stdout == Echo.marker:
                        break
                    last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                    time.sleep(1)
                else:
                    print(safe_log_excerpt(log_path.read_text(
                        encoding="utf-8", errors="replace")))
                    raise AssertionError(f"MASQUE TCP traffic failed: {last}")
                verify_udp(32242, 32296, "MASQUE")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
    finally:
        stop.set()
        udp_thread.join(timeout=2)
        udp_server.close()
        httpd.shutdown()
        thread.join(timeout=5)
        run("ip", "address", "del", ECHO_ADDRESS + "/32", "dev", "lo")


def main() -> None:
    if os.environ.get("XUI_RUN_INBOUND_MASQUE_E2E") != "1":
        raise RuntimeError("disposable MASQUE E2E must be explicitly enabled")
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    api = ApiClient(f"http://127.0.0.1:{credentials['port']}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    xray = Path("/usr/local/x-ui/bin/xray-linux-amd64")
    manager = InboundManager(api, xray=xray)
    with tempfile.TemporaryDirectory(prefix="xui-masque-") as directory:
        root = Path(directory)
        ca, cert, key = certificates(root)
        spec = MasqueSpec("DE", "ci", 32231, "127.0.0.1", "ci.example.test",
                          "ci-masque@example.test", cert, key)
        first = manager.ensure_masque(spec)
        assert first["created"], "fresh runner should create MASQUE inbound"
        try:
            second = manager.ensure_masque(spec)
            assert not second["created"] and second["inbound_id"] == first["inbound_id"]
            detail = api.read(f"inbounds/get/{first['inbound_id']}")
            stream = normalize_embedded_json(detail["streamSettings"])
            assert stream["network"] == "masque" and stream["security"] == "tls"
            assert stream["masqueSettings"]["path"] == spec.path
            record = api.read(f"clients/get/{spec.client_email}")
            client = record["client"]
            wait_backend_user(spec.port, spec.client_email)
            links = api.read(f"clients/links/{spec.client_email}")
            assert links == [], "pinned panel unexpectedly exports MASQUE URI"
            config = {
                "log": {"loglevel": "debug"},
                "inbounds": [{"tag": "ci-socks", "listen": "127.0.0.1", "port": 32242,
                              "protocol": "socks", "settings": {"auth": "noauth", "udp": True}}],
                "outbounds": [{"tag": "ci-masque", "protocol": "masque",
                               "settings": {"address": "127.0.0.1", "port": spec.port},
                               "streamSettings": {
                                   "network": "masque", "security": "tls",
                                   "masqueSettings": {"host": spec.server_name,
                                                      "path": spec.path,
                                                      "user": spec.client_email,
                                                      "pass": client["password"]},
                                   "tlsSettings": {"serverName": spec.server_name,
                                                   "alpn": ["h3"],
                                                   "disableSystemRoot": True,
                                                   "certificates": [{"certificateFile": str(ca),
                                                                     "usage": "verify"}]}}}],
            }
            exercise_traffic(xray, config, root)
            print("MASQUE API, HTTP/3 CONNECT-IP, verified TLS, TCP and UDP traffic PASS")
            print("MASQUE URI share link: upstream unsupported")
        finally:
            api.post(f"clients/del/{spec.client_email}", {})
            api.post(f"inbounds/del/{first['inbound_id']}", {})


if __name__ == "__main__":
    main()
