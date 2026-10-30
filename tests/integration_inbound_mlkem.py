"""VLESS ML-KEM768 encryption with XHTTP/TLS and real Xray traffic."""

from __future__ import annotations

import http.server
import json
import os
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
from integration_inbound_web_tls import (
    certificates,
    client_config,
    run,
    verify_raw_subscription,
)

from xui_fork.api_client import ApiClient, normalize_embedded_json
from xui_fork.inbound_manager import InboundManager, MlkemTlsSpec


def main() -> None:
    if os.environ.get("XUI_RUN_INBOUND_MLKEM_E2E") != "1":
        raise RuntimeError("disposable ML-KEM768 E2E must be explicitly enabled")
    credentials = json.loads(Path("/etc/x-ui/fork-credentials.json").read_text())
    api = ApiClient(f"http://127.0.0.1:{credentials['port']}",
                    token_from_cli(Path("/usr/local/x-ui/x-ui")),
                    credentials["web_base_path"])
    xray = Path("/usr/local/x-ui/bin/xray-linux-amd64")
    manager = InboundManager(api, xray=xray)
    with tempfile.TemporaryDirectory(prefix="xui-mlkem-") as directory:
        root = Path(directory)
        ca, cert, key = certificates(root)
        spec = MlkemTlsSpec("DE", "ci", 32226, "127.0.0.1",
                            "ci.example.test", "/ci-mlkem",
                            "ci-mlkem@example.test", cert, key)
        first = manager.ensure_mlkem_tls(spec)
        assert first["created"], "fresh runner should create ML-KEM768 inbound"
        try:
            second = manager.ensure_mlkem_tls(spec)
            assert not second["created"] and second["inbound_id"] == first["inbound_id"]
            detail = api.read(f"inbounds/get/{first['inbound_id']}")
            settings = normalize_embedded_json(detail["settings"])
            assert "fallbacks" not in settings
            encryption = settings["encryption"]
            assert encryption.startswith("mlkem768x25519plus.native.")
            assert settings["decryption"].startswith("mlkem768x25519plus.native.")
            stream = normalize_embedded_json(detail["streamSettings"])
            assert stream["network"] == "xhttp" and stream["security"] == "tls"
            record = api.read(f"clients/get/{spec.client_email}")
            client = record["client"]
            client_id = client["uuid"]
            links = api.read(f"clients/links/{spec.client_email}")
            assert isinstance(links, list) and len(links) == 1
            parsed = urllib.parse.urlparse(links[0])
            query = urllib.parse.parse_qs(parsed.query)
            assert parsed.scheme == "vless" and parsed.username == client_id
            assert parsed.hostname == spec.public_address and parsed.port == spec.port
            assert query.get("type") == ["xhttp"] and query.get("security") == ["tls"]
            assert query.get("sni") == [spec.server_name]
            assert query.get("encryption") == [encryption]
            sub_links = api.read(f"clients/subLinks/{client['subId']}")
            assert links[0] in sub_links
            verify_raw_subscription(api, client["subId"], links[0])
            config = client_config(spec, client_id, ca, 32236)
            config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["encryption"] = encryption
            config_path = root / "client.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run("ip", "address", "add", ECHO_ADDRESS + "/32", "dev", "lo")
            httpd = http.server.ThreadingHTTPServer((ECHO_ADDRESS, 32286), Echo)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                log_path = root / "xray-client.log"
                with log_path.open("wb") as log:
                    process = subprocess.Popen([str(xray), "run", "-config", str(config_path)],
                                               stdout=log, stderr=subprocess.STDOUT)
                    try:
                        wait_port(32236)
                        wait_port(spec.port)
                        last = ""
                        for _ in range(15):
                            result = subprocess.run(
                                ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                                 "--noproxy", "", "--socks5-hostname", "127.0.0.1:32236",
                                 f"http://{ECHO_ADDRESS}:32286/"],
                                capture_output=True, text=True, timeout=10)
                            if result.returncode == 0 and result.stdout == Echo.marker:
                                break
                            last = f"curl exit={result.returncode}: {result.stderr.strip()}"
                            time.sleep(1)
                        else:
                            print(safe_log_excerpt(log_path.read_text(
                                encoding="utf-8", errors="replace")))
                            raise AssertionError(f"VLESS ML-KEM768 traffic failed: {last}")
                    finally:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                run("ip", "address", "del", ECHO_ADDRESS + "/32", "dev", "lo")
            print("VLESS ML-KEM768 API, link, RAW subscription, handshake, traffic PASS")
        finally:
            api.post(f"clients/del/{spec.client_email}", {})
            api.post(f"inbounds/del/{first['inbound_id']}", {})


if __name__ == "__main__":
    main()
