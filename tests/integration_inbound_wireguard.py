"""WireGuard peer through the official panel and real Xray TCP/UDP traffic."""

from __future__ import annotations

import base64
import http.server
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

from integration_inbound_reality import (
    ECHO_ADDRESS,
    Echo,
    safe_log_excerpt,
    token_from_cli,
    wait_port,
)
from integration_inbound_shadowsocks2022 import udp_echo, verify_udp
from integration_inbound_web_tls import run, verify_raw_subscription

from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, WireguardSpec


def wait_backend_peer(port: int, public_key: str) -> None:
    config_file = Path("/usr/local/x-ui/bin/config.json")
    peer_hex = base64.b64decode(public_key).hex()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.5)
            continue
        matches = [row for row in config.get("inbounds", []) if row.get("port") == port]
        if len(matches) == 1 and matches[0].get("protocol") == "wireguard":
            settings = normalize_embedded_json(matches[0].get("settings", {}))
            if any(c.get("publicKey") in {peer_hex, public_key}
                   for c in settings.get("peers", []) if isinstance(c, dict)):
                return
        time.sleep(0.5)
    raise AssertionError("WireGuard peer not present in generated Xray config")


def exercise_traffic(xray: Path, config: dict, root: Path) -> None:
    config_path = root / "client.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    run("ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo")
    httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32291), Echo)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.bind((ECHO_ADDRESS, 32292))
    stop = threading.Event()
    udp_thread = threading.Thread(target=udp_echo, args=(udp_server, stop), daemon=True)
    udp_thread.start()
    try:
        log_path = root / "xray-client.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(xray), "run", "-config", str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_port(32239)
                last = ""
                for _ in range(25):
                    result = subprocess.run(
                        ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                         "--noproxy", "", "--socks5-hostname", "127.0.0.1:32239",
                         f"http://{ECHO_ADDRESS}:32291/"],
                        capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and result.stdout == Echo.marker:
                        break
                    last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                    time.sleep(1)
                else:
                    print(safe_log_excerpt(log_path.read_text(
                        encoding="utf-8", errors="replace")))
                    raise AssertionError(f"WireGuard TCP traffic failed: {last}")
                verify_udp(32239, 32292, "WireGuard")
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
    if os.environ.get("XUI_RUN_INBOUND_WIREGUARD_E2E") != "1":
        raise RuntimeError("disposable WireGuard E2E must be explicitly enabled")
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    api = ApiClient(f"http://127.0.0.1:{credentials['port']}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    xray = Path("/usr/local/x-ui/bin/xray-linux-amd64")
    manager = InboundManager(api, xray=xray)
    with tempfile.TemporaryDirectory(prefix="xui-wg-") as directory:
        root = Path(directory)
        spec = WireguardSpec("DE", "ci", 32229, "127.0.0.1", "ci-wg@example.test")
        first = manager.ensure_wireguard(spec)
        assert first["created"], "fresh runner should create WireGuard inbound"
        try:
            second = manager.ensure_wireguard(spec)
            assert not second["created"] and second["inbound_id"] == first["inbound_id"]
            detail = api.read(f"inbounds/get/{first['inbound_id']}")
            settings = normalize_embedded_json(detail["settings"])
            assert detail["protocol"] == "wireguard"
            assert settings["mtu"] == spec.mtu and settings["noKernelTun"] is True
            assert settings["subnetIp"] == "10.66.0.0" and settings["subnetCidr"] == 24
            record = api.read(f"clients/get/{spec.client_email}")
            client = record["client"]
            assert len(client["allowedIPs"]) == 1
            wait_backend_peer(spec.port, client["publicKey"])
            links = api.read(f"clients/links/{spec.client_email}")
            assert isinstance(links, list) and len(links) == 1
            parsed = urllib.parse.urlparse(links[0])
            query = urllib.parse.parse_qs(parsed.query)
            assert parsed.scheme == "wireguard"
            assert urllib.parse.unquote(parsed.username) == client["privateKey"]
            assert parsed.hostname == spec.public_address and parsed.port == spec.port
            assert query.get("address") == client["allowedIPs"]
            assert query.get("mtu") == [str(spec.mtu)]
            assert len(query.get("publickey", [])) == 1
            sub_links = api.read(f"clients/subLinks/{client['subId']}")
            assert links[0] in sub_links
            verify_raw_subscription(api, client["subId"], links[0])
            config = {
                "log": {"loglevel": "debug"},
                "inbounds": [{"tag": "ci-socks", "listen": "127.0.0.1", "port": 32239,
                              "protocol": "socks", "settings": {"auth": "noauth", "udp": True}}],
                "outbounds": [{"tag": "ci-wg", "protocol": "wireguard",
                               "settings": {"secretKey": client["privateKey"],
                                            "address": client["allowedIPs"],
                                            "peers": [{"publicKey": query["publickey"][0],
                                                       "endpoint": f"127.0.0.1:{spec.port}",
                                                       "allowedIPs": ["0.0.0.0/0"]}],
                                            "noKernelTun": True, "mtu": spec.mtu}}],
            }
            exercise_traffic(xray, config, root)
            print("WireGuard API, peer, link, RAW subscription, TCP and UDP traffic PASS")
        finally:
            api.post(f"clients/del/{spec.client_email}", {})
            api.post(f"inbounds/del/{first['inbound_id']}", {})


if __name__ == "__main__":
    main()
