"""Native TUIC v5 through official 3x-ui, sing-box, TCP and UDP echo."""

from __future__ import annotations

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
from integration_inbound_web_tls import certificates, run, verify_raw_subscription

from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, TuicSpec


def wait_native_backend(port: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = subprocess.run(["ss", "-H", "-lun"], capture_output=True, text=True,
                                timeout=5, check=True)
        if any(f"127.0.0.1:{port}" in line for line in result.stdout.splitlines()):
            return
        time.sleep(0.5)
    raise AssertionError("native TUIC UDP listener not present")


def exercise_traffic(sing_box: Path, config: dict, root: Path) -> None:
    config_path = root / "client.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    run("ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo")
    httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32293), Echo)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.bind((ECHO_ADDRESS, 32294))
    stop = threading.Event()
    udp_thread = threading.Thread(target=udp_echo, args=(udp_server, stop), daemon=True)
    udp_thread.start()
    try:
        log_path = root / "sing-box-client.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(sing_box), "run", "-c", str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_port(32241)
                last = ""
                for _ in range(25):
                    result = subprocess.run(
                        ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                         "--noproxy", "", "--socks5-hostname", "127.0.0.1:32241",
                         f"http://{ECHO_ADDRESS}:32293/"],
                        capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and result.stdout == Echo.marker:
                        break
                    last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                    time.sleep(1)
                else:
                    print(safe_log_excerpt(log_path.read_text(
                        encoding="utf-8", errors="replace")))
                    raise AssertionError(f"TUIC TCP traffic failed: {last}")
                verify_udp(32241, 32294, "TUIC v5")
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
    if os.environ.get("XUI_RUN_INBOUND_TUIC_E2E") != "1":
        raise RuntimeError("disposable TUIC E2E must be explicitly enabled")
    sing_box = Path("/tmp/sing-box-1.14.4-linux-amd64-glibc/sing-box")
    assert sing_box.is_file(), "pinned compatible sing-box client unavailable"
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    api = ApiClient(f"http://127.0.0.1:{credentials['port']}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    manager = InboundManager(api)
    with tempfile.TemporaryDirectory(prefix="xui-tuic-") as directory:
        root = Path(directory)
        ca, cert, key = certificates(root)
        spec = TuicSpec("DE", "ci", 32230, "127.0.0.1",
                        "ci.example.test", "ci-tuic@example.test", cert, key)
        first = manager.ensure_tuic_v5(spec)
        assert first["created"], "fresh runner should create TUIC inbound"
        try:
            second = manager.ensure_tuic_v5(spec)
            assert not second["created"] and second["inbound_id"] == first["inbound_id"]
            detail = api.read(f"inbounds/get/{first['inbound_id']}")
            settings = normalize_embedded_json(detail["settings"])
            assert detail["protocol"] == "tuic"
            assert settings["server"]["alpn"] == ["h3"]
            record = api.read(f"clients/get/{spec.client_email}")
            client = record["client"]
            assert client["uuid"] and client["password"]
            wait_native_backend(spec.port)
            links = api.read(f"clients/links/{spec.client_email}")
            assert isinstance(links, list) and len(links) == 1
            parsed = urllib.parse.urlparse(links[0])
            query = urllib.parse.parse_qs(parsed.query)
            assert parsed.scheme == "tuic" and parsed.username == client["uuid"]
            assert urllib.parse.unquote(parsed.password) == client["password"]
            assert parsed.hostname == spec.public_address and parsed.port == spec.port
            assert query.get("sni") == [spec.server_name]
            assert query.get("alpn") == ["h3"]
            assert query.get("udp_relay_mode") == ["native"]
            sub_links = api.read(f"clients/subLinks/{client['subId']}")
            sub_link_present = links[0] in sub_links
            raw_sub_present = False
            if sub_link_present:
                try:
                    verify_raw_subscription(api, client["subId"], links[0])
                except AssertionError as exc:
                    if "omits TLS share link" not in str(exc):
                        raise
                else:
                    raw_sub_present = True
            config = {
                "log": {"level": "warn"},
                "inbounds": [{"type": "socks", "tag": "ci-socks",
                              "listen": "127.0.0.1", "listen_port": 32241}],
                "outbounds": [{"type": "tuic", "tag": "ci-tuic",
                               "server": "127.0.0.1", "server_port": spec.port,
                               "uuid": client["uuid"], "password": client["password"],
                               "congestion_control": "bbr", "udp_relay_mode": "native",
                               "zero_rtt_handshake": False,
                               "tls": {"enabled": True, "server_name": spec.server_name,
                                       "alpn": ["h3"], "certificate_path": str(ca)}}],
                "route": {"final": "ci-tuic"},
            }
            exercise_traffic(sing_box, config, root)
            print("TUIC v5 native API, link, verified TLS, TCP and UDP traffic PASS")
            print(f"TUIC v5 subscription: subLinks={sub_link_present}, RAW={raw_sub_present}")
        finally:
            api.post(f"clients/del/{spec.client_email}", {})
            api.post(f"inbounds/del/{first['inbound_id']}", {})


if __name__ == "__main__":
    main()
