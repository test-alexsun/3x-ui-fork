import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from xui_fork.inbound_manager import (
    InboundConflict,
    InboundError,
    InboundManager,
    InboundSpec,
    MixedSpec,
    WebTlsSpec,
    generate_reality_keypair,
)


class FakeApi:
    def __init__(self):
        self.rows = []
        self.clients = {}
        self.posts = []

    def verify_contract(self):
        return True

    def read(self, path):
        if path == "inbounds/list":
            return self.rows
        if path.startswith("inbounds/get/"):
            return self.rows[0]
        if path == "clients/list":
            return [entry["client"] for entry in self.clients.values()]
        if path.startswith("clients/get/"):
            return self.clients.get(path.removeprefix("clients/get/"))
        if path.startswith("clients/links/"):
            return ["vless://verified"]
        raise AssertionError(path)

    def post(self, path, payload):
        self.posts.append(path)
        if path == "inbounds/add":
            self.rows.append({**payload, "id": 9})
        elif path == "clients/add":
            client = payload["client"]
            self.clients[client["email"]] = {
                "client": {**client, "id": 17, "uuid": client["id"]},
                "inboundIds": payload["inboundIds"],
            }
            settings = json.loads(self.rows[0]["settings"])
            settings["clients"].append(client)
            self.rows[0]["settings"] = json.dumps(settings)
        else:
            raise AssertionError(path)
        return {}


def spec(profile="VLESS REALITY Vision"):
    return InboundSpec(profile, "DE", "lab", 32121, "127.0.0.1",
                       "www.cloudflare.com", "www.cloudflare.com", "lab@example.test")


class InboundManagerTests(unittest.TestCase):
    def test_create_client_verify_and_idempotent_read(self):
        api = FakeApi()
        manager = InboundManager(api, xray=Path("/fixture/xray"))
        client_id = str(uuid.uuid4())
        with patch("xui_fork.inbound_manager.generate_reality_keypair",
                   return_value=("a" * 43, "b" * 43)):
            first = manager.ensure_reality_vision(spec(), client_id=client_id)
            second = manager.ensure_reality_vision(spec())
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        self.assertEqual(api.clients[spec().client_email]["client"]["uuid"], client_id)
        self.assertIsInstance(api.rows[0]["settings"], str)
        self.assertEqual(json.loads(api.rows[0]["streamSettings"])["security"], "reality")

    def test_foreign_port_and_unsupported_profile_fail_before_write(self):
        api = FakeApi()
        api.rows = [{"port": 32121, "remark": "foreign"}]
        manager = InboundManager(api, xray=Path("/fixture/xray"))
        with self.assertRaises(InboundConflict):
            manager.ensure_reality_vision(spec())
        with self.assertRaisesRegex(InboundError, "unavailable"):
            manager.ensure_reality_vision(spec("TUIC v5"))
        self.assertEqual(api.posts, [])

    def test_keypair_parser_requires_real_xray_output(self):
        for output in (
            "Private key: " + "a" * 43 + "\nPublic key: " + "b" * 43 + "\n",
            "PrivateKey: " + "a" * 43 + "\nPassword (PublicKey): " + "b" * 43 + "\n",
        ):
            with (patch.object(Path, "is_file", return_value=True),
                  patch("xui_fork.inbound_manager.subprocess.run",
                        return_value=Mock(stdout=output))):
                self.assertEqual(generate_reality_keypair(Path("/fixture/xray")),
                                 ("a" * 43, "b" * 43))

    def test_mixed_account_and_idempotence(self):
        api = FakeApi()
        manager = InboundManager(api)
        mixed = MixedSpec("DE", "lab", 32124, "labuser01", "a" * 24)
        first = manager.ensure_mixed(mixed)
        second = manager.ensure_mixed(mixed)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add"])
        self.assertEqual(json.loads(api.rows[0]["settings"])["accounts"][0]["user"],
                         mixed.username)
        self.assertEqual(api.rows[0]["shareAddrStrategy"], "listen")
        with self.assertRaises(InboundConflict):
            manager.ensure_mixed(MixedSpec("DE", "lab", 32124, "labuser01", "b" * 24))

    def test_websocket_tls_payload_and_client_readback(self):
        for profile, protocol in (("VLESS WebSocket TLS", "vless"),
                                  ("VMess WebSocket TLS", "vmess")):
            with self.subTest(profile=profile):
                api = FakeApi()
                manager = InboundManager(api)
                web = WebTlsSpec(profile, "DE", "lab", 32125, "127.0.0.1",
                                 "ci.example.test", "/ci-ws", "ws@example.test",
                                 Path.cwd() / "ci-cert.pem", Path.cwd() / "ci-key.pem")
                with patch("xui_fork.inbound_manager.require_certificate"):
                    first = manager.ensure_websocket_tls(web)
                    second = manager.ensure_websocket_tls(web)
                self.assertTrue(first["created"])
                self.assertFalse(second["created"])
                self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
                self.assertEqual(api.rows[0]["protocol"], protocol)
                stream = json.loads(api.rows[0]["streamSettings"])
                self.assertEqual(stream["wsSettings"]["path"], "/ci-ws")
                self.assertEqual(stream["tlsSettings"]["serverName"], "ci.example.test")
