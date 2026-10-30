"""Official Shadowsocks 2022 multi-user TCP and UDP traffic E2E."""

from __future__ import annotations

import http.server
import json
import os
import socket
import struct
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
from integration_inbound_web_tls import run, verify_raw_subscription

from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, Shadowsocks2022Spec


def udp_echo(server: socket.socket, stop: threading.Event) -> None:
    server.settimeout(0.5)
    while not stop.is_set():
        try:
            _, address = server.recvfrom(4096)
        except socket.timeout:
            continue
        server.sendto(Echo.marker.encode(), address)


def verify_udp(socks_port: int, echo_port: int) -> None:
    def receive_exact(connection: socket.socket, count: int) -> bytes:
        data = b""
        while len(data) < count:
            part = connection.recv(count - len(data))
            if not part:
                raise AssertionError("SOCKS5 UDP association closed early")
            data += part
        return data

    with socket.create_connection(("127.0.0.1", socks_port), timeout=5) as control:
        control.settimeout(5)
        control.sendall(b"\x05\x01\x00")
        assert receive_exact(control, 2) == b"\x05\x00", "SOCKS5 no-auth negotiation failed"
        control.sendall(b"\x05\x03\x00\x01" + b"\x00" * 6)
        response = receive_exact(control, 10)
        assert len(response) == 10 and response[:4] == b"\x05\x00\x00\x01"
        relay_port = struct.unpack("!H", response[8:10])[0]
        packet = (b"\x00\x00\x00\x01" + socket.inet_aton(ECHO_ADDRESS)
                  + struct.pack("!H", echo_port) + b"ss2022-udp")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(4)
            for _ in range(5):
                client.sendto(packet, ("127.0.0.1", relay_port))
                try:
                    received, _ = client.recvfrom(4096)
                except socket.timeout:
                    continue
                assert received.endswith(Echo.marker.encode()), "UDP echo marker mismatch"
                return
        raise AssertionError("Shadowsocks 2022 UDP traffic did not reach echo")


def exercise_traffic(xray: Path, config: dict, root: Path, inbound_port: int) -> None:
    config_path = root / "client.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    run("ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo")
    httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32287), Echo)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_server.bind((ECHO_ADDRESS, 32288))
    stop = threading.Event()
    udp_thread = threading.Thread(target=udp_echo, args=(udp_server, stop), daemon=True)
    udp_thread.start()
    try:
        log_path = root / "xray-client.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen([str(xray), "run", "-config", str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_port(32237)
                wait_port(inbound_port)
                last = ""
                for _ in range(12):
                    result = subprocess.run(
                        ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                         "--noproxy", "", "--socks5-hostname", "127.0.0.1:32237",
                         f"http://{ECHO_ADDRESS}:32287/"],
                        capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and result.stdout == Echo.marker:
                        break
                    last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                    time.sleep(1)
                else:
                    print(safe_log_excerpt(log_path.read_text(
                        encoding="utf-8", errors="replace")))
                    raise AssertionError(f"Shadowsocks 2022 TCP traffic failed: {last}")
                verify_udp(32237, 32288)
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
    if os.environ.get("XUI_RUN_INBOUND_SS2022_E2E") != "1":
        raise RuntimeError("disposable Shadowsocks 2022 E2E must be explicitly enabled")
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    api = ApiClient(f"http://127.0.0.1:{credentials['port']}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    xray = Path("/usr/local/x-ui/bin/xray-linux-amd64")
    manager = InboundManager(api, xray=xray)
    spec = Shadowsocks2022Spec("DE", "ci", 32227, "127.0.0.1",
                               "ci-ss2022@example.test")
    first = manager.ensure_shadowsocks_2022(spec)
    assert first["created"], "fresh runner should create Shadowsocks 2022 inbound"
    try:
        second = manager.ensure_shadowsocks_2022(spec)
        assert not second["created"] and second["inbound_id"] == first["inbound_id"]
        detail = api.read(f"inbounds/get/{first['inbound_id']}")
        settings = normalize_embedded_json(detail["settings"])
        assert settings["method"] == spec.method and settings["network"] == "tcp,udp"
        server_key = settings["password"]
        record = api.read(f"clients/get/{spec.client_email}")
        client = record["client"]
        client_key = client["password"]
        assert any(c.get("password") == client_key for c in settings["clients"])
        links = api.read(f"clients/links/{spec.client_email}")
        assert isinstance(links, list) and len(links) == 1
        parsed = urllib.parse.urlparse(links[0])
        assert parsed.scheme == "ss" and parsed.hostname == spec.public_address
        assert parsed.port == spec.port
        userinfo = urllib.parse.unquote(links[0].split("@", 1)[0].removeprefix("ss://"))
        assert userinfo == f"{spec.method}:{server_key}:{client_key}"
        sub_links = api.read(f"clients/subLinks/{client['subId']}")
        assert links[0] in sub_links
        verify_raw_subscription(api, client["subId"], links[0])
        config = {
            "log": {"loglevel": "debug"},
            "inbounds": [{"tag": "ci-socks", "listen": "127.0.0.1", "port": 32237,
                          "protocol": "socks", "settings": {"auth": "noauth", "udp": True}}],
            "outbounds": [{"tag": "ci-ss2022", "protocol": "shadowsocks",
                           "settings": {"servers": [{"address": "127.0.0.1",
                                                    "port": spec.port,
                                                    "method": spec.method,
                                                    "password": f"{server_key}:{client_key}"}]}}],
        }
        with tempfile.TemporaryDirectory(prefix="xui-ss2022-") as directory:
            exercise_traffic(xray, config, Path(directory), spec.port)
        print("Shadowsocks 2022 API, link, RAW subscription, TCP and UDP traffic PASS")
    finally:
        api.post(f"clients/del/{spec.client_email}", {})
        api.post(f"inbounds/del/{first['inbound_id']}", {})


if __name__ == "__main__":
    main()
