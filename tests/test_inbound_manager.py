import base64
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from xui_fork.inbound_manager import (
    GrpcTlsSpec,
    Hysteria2Spec,
    InboundConflict,
    InboundError,
    InboundManager,
    InboundSpec,
    MixedSpec,
    MlkemTlsSpec,
    RealityXhttpSpec,
    Shadowsocks2022Spec,
    WebTlsSpec,
    WireguardSpec,
    generate_reality_keypair,
    generate_wireguard_keypair,
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
        if path == "server/getNewVlessEnc":
            return {"auths": [{"id": "mlkem768",
                               "decryption": "mlkem768x25519plus.native.600s.server-key",
                               "encryption": "mlkem768x25519plus.native.0rtt.client-key"}]}
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
            if self.rows[0]["protocol"] == "wireguard":
                client = {**client, "privateKey": base64.b64encode(b"c" * 32).decode(),
                          "publicKey": base64.b64encode(b"d" * 32).decode(),
                          "allowedIPs": ["10.66.0.2/32"]}
            self.clients[client["email"]] = {
                "client": {**client, "id": 17, "uuid": client.get("id", ""),
                           "allowedIPs": ",".join(client["allowedIPs"])
                           if self.rows[0]["protocol"] == "wireguard"
                           else client.get("allowedIPs", [])},
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
                                  ("VMess WebSocket TLS", "vmess"),
                                  ("VLESS XHTTP TLS", "vless")):
            with self.subTest(profile=profile):
                api = FakeApi()
                manager = InboundManager(api)
                web = WebTlsSpec(profile, "DE", "lab", 32125, "127.0.0.1",
                                 "ci.example.test", "/ci-ws", "ws@example.test",
                                 Path.cwd() / "ci-cert.pem", Path.cwd() / "ci-key.pem")
                with patch("xui_fork.inbound_manager.require_certificate"):
                    ensure = (manager.ensure_xhttp_tls if profile == "VLESS XHTTP TLS"
                              else manager.ensure_websocket_tls)
                    first = ensure(web)
                    second = ensure(web)
                self.assertTrue(first["created"])
                self.assertFalse(second["created"])
                self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
                self.assertEqual(api.rows[0]["protocol"], protocol)
                stream = json.loads(api.rows[0]["streamSettings"])
                network = "xhttp" if profile == "VLESS XHTTP TLS" else "ws"
                self.assertEqual(stream[network + "Settings"]["path"], "/ci-ws")
                self.assertEqual(stream["tlsSettings"]["serverName"], "ci.example.test")

    def test_trojan_grpc_tls_password_and_idempotence(self):
        api = FakeApi()
        manager = InboundManager(api)
        grpc = GrpcTlsSpec("DE", "lab", 32126, "127.0.0.1",
                           "ci.example.test", "ci-grpc", "grpc@example.test",
                           Path.cwd() / "ci-cert.pem", Path.cwd() / "ci-key.pem")
        with patch("xui_fork.inbound_manager.require_certificate"):
            first = manager.ensure_trojan_grpc_tls(grpc)
            second = manager.ensure_trojan_grpc_tls(grpc)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        self.assertEqual(api.rows[0]["protocol"], "trojan")
        stream = json.loads(api.rows[0]["streamSettings"])
        self.assertEqual(stream["grpcSettings"]["serviceName"], "ci-grpc")
        self.assertIn("h2", stream["tlsSettings"]["alpn"])
        password = api.clients[grpc.client_email]["client"]["password"]
        self.assertGreaterEqual(len(password), 20)
        self.assertEqual(json.loads(api.rows[0]["settings"])["clients"][0]["password"],
                         password)

    def test_reality_xhttp_payload_client_and_idempotence(self):
        api = FakeApi()
        manager = InboundManager(api, xray=Path("/fixture/xray"))
        xhttp = RealityXhttpSpec("DE", "lab", 32127, "127.0.0.1",
                                 "www.cloudflare.com", "www.cloudflare.com",
                                 "/ci-reality", "xhttp@example.test")
        with patch("xui_fork.inbound_manager.generate_reality_keypair",
                   return_value=("a" * 43, "b" * 43)):
            first = manager.ensure_reality_xhttp(xhttp)
            second = manager.ensure_reality_xhttp(xhttp)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        stream = json.loads(api.rows[0]["streamSettings"])
        self.assertEqual(stream["network"], "xhttp")
        self.assertEqual(stream["security"], "reality")
        self.assertEqual(stream["xhttpSettings"]["path"], "/ci-reality")
        self.assertEqual(stream["realitySettings"]["settings"]["publicKey"], "b" * 43)
        self.assertEqual(api.rows[0]["disableFlow"], True)
        client = json.loads(api.rows[0]["settings"])["clients"][0]
        self.assertEqual(client["flow"], "")

    def test_mlkem_tls_uses_official_pair_without_fallbacks(self):
        api = FakeApi()
        manager = InboundManager(api)
        mlkem = MlkemTlsSpec("DE", "lab", 32128, "127.0.0.1",
                             "ci.example.test", "/ci-mlkem", "mlkem@example.test",
                             Path.cwd() / "ci-cert.pem", Path.cwd() / "ci-key.pem")
        with patch("xui_fork.inbound_manager.require_certificate"):
            first = manager.ensure_mlkem_tls(mlkem)
            second = manager.ensure_mlkem_tls(mlkem)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        settings = json.loads(api.rows[0]["settings"])
        self.assertNotIn("fallbacks", settings)
        self.assertTrue(settings["decryption"].startswith("mlkem768x25519plus.native."))
        self.assertTrue(settings["encryption"].startswith("mlkem768x25519plus.native."))
        self.assertEqual(json.loads(api.rows[0]["streamSettings"])["network"], "xhttp")

    def test_shadowsocks_2022_server_and_client_keys_are_stable(self):
        api = FakeApi()
        manager = InboundManager(api)
        ss = Shadowsocks2022Spec("DE", "lab", 32129, "127.0.0.1",
                                 "ss@example.test")
        first = manager.ensure_shadowsocks_2022(ss)
        detail = json.loads(api.rows[0]["settings"])
        server_key = detail["password"]
        client_key = detail["clients"][0]["password"]
        second = manager.ensure_shadowsocks_2022(ss)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        self.assertEqual(detail["method"], "2022-blake3-aes-256-gcm")
        self.assertEqual(detail["network"], "tcp,udp")
        self.assertEqual(json.loads(api.rows[0]["settings"])["password"], server_key)
        self.assertEqual(api.clients[ss.client_email]["client"]["password"], client_key)

    def test_hysteria2_tls_quic_auth_and_idempotence(self):
        api = FakeApi()
        manager = InboundManager(api)
        hy = Hysteria2Spec("DE", "lab", 32130, "127.0.0.1",
                           "ci.example.test", "hy@example.test",
                           Path.cwd() / "ci-cert.pem", Path.cwd() / "ci-key.pem")
        with patch("xui_fork.inbound_manager.require_certificate"):
            first = manager.ensure_hysteria2(hy)
            second = manager.ensure_hysteria2(hy)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        stream = json.loads(api.rows[0]["streamSettings"])
        self.assertEqual(stream["network"], "hysteria")
        self.assertEqual(stream["hysteriaSettings"]["version"], 2)
        self.assertEqual(stream["tlsSettings"]["alpn"], ["h3"])
        settings = json.loads(api.rows[0]["settings"])
        self.assertEqual(settings["version"], 2)
        self.assertEqual(settings["clients"][0]["auth"],
                         api.clients[hy.client_email]["client"]["auth"])

    def test_wireguard_panel_allocated_peer_and_idempotence(self):
        api = FakeApi()
        manager = InboundManager(api, xray=Path("/fixture/xray"))
        wg = WireguardSpec("DE", "lab", 32131, "127.0.0.1", "wg@example.test")
        with patch("xui_fork.inbound_manager.generate_wireguard_keypair",
                   return_value=(base64.b64encode(b"a" * 32).decode(),
                                 base64.b64encode(b"b" * 32).decode())):
            first = manager.ensure_wireguard(wg)
            second = manager.ensure_wireguard(wg)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(api.posts, ["inbounds/add", "clients/add"])
        settings = json.loads(api.rows[0]["settings"])
        self.assertEqual(settings["subnetIp"], "10.66.0.0")
        self.assertEqual(settings["subnetCidr"], 24)
        self.assertTrue(settings["noKernelTun"])
        self.assertEqual(settings["clients"][0]["allowedIPs"], ["10.66.0.2/32"])

    def test_wireguard_key_parser_rejects_bad_output(self):
        private = base64.b64encode(b"a" * 32).decode()
        public = base64.b64encode(b"b" * 32).decode()
        with (patch.object(Path, "is_file", return_value=True),
              patch("xui_fork.inbound_manager.subprocess.run",
                    return_value=Mock(stdout=f"PrivateKey: {private}\nPassword (PublicKey): {public}\n"))):
            self.assertEqual(generate_wireguard_keypair(Path("/fixture/xray")),
                             (private, public))
        with (patch.object(Path, "is_file", return_value=True),
              patch("xui_fork.inbound_manager.subprocess.run",
                    return_value=Mock(stdout="PrivateKey: invalid\nPublicKey: invalid\n"))):
            with self.assertRaises(InboundError):
                generate_wireguard_keypair(Path("/fixture/xray"))
