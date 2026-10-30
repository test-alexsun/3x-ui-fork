import hashlib
import json
import unittest
import urllib.error
from unittest.mock import patch

from xui_fork.api_client import (
    REQUIRED_OPERATIONS,
    ApiClient,
    ApiError,
    ApiUncertainError,
    normalize_embedded_json,
)
from xui_fork.compatibility import profile_supported, version_supported


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return json.dumps(self.payload).encode()


class ContractTests(unittest.TestCase):
    def test_api_path_and_success_envelope(self):
        client = ApiClient("https://example.test", "secret", "admin/")
        with patch("urllib.request.urlopen", return_value=Response({"success": True, "obj": []})) as open_:
            self.assertEqual(client.read("inbounds/list"), [])
            request = open_.call_args.args[0]
            self.assertEqual(request.full_url, "https://example.test/admin/panel/api/inbounds/list")
        with patch("urllib.request.urlopen", return_value=Response({"success": False, "msg": "no"})):
            with self.assertRaisesRegex(ApiError, "rejected"):
                client.read("inbounds/list")
        with self.assertRaisesRegex(ApiError, "allowlisted"):
            client.read("server/getDb")
        with patch("urllib.request.urlopen", return_value=Response({"success": True, "obj": {"subPort": 2096}})):
            self.assertEqual(client.read_post("setting/all"), {"subPort": 2096})
        with self.assertRaisesRegex(ApiError, "allowlisted"):
            client.read_post("setting/update")

    def test_token_remote_http_and_unknown_version_rejected(self):
        with self.assertRaisesRegex(ValueError, "TLS"):
            ApiClient("http://example.test", "secret")
        self.assertFalse(version_supported("3.12.0"))
        self.assertTrue(profile_supported("MASQUE", "3.11.0"))
        self.assertFalse(profile_supported("MASQUE", "3.12.0"))
        self.assertEqual(normalize_embedded_json('{"clients":[]}'), {"clients": []})

    def test_write_result_is_never_retried_after_timeout(self):
        client = ApiClient("https://example.test", "secret")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")) as open_:
            with self.assertRaises(ApiUncertainError):
                client.post("inbounds/add", {"remark": "example"})
            self.assertEqual(open_.call_count, 1)
        with self.assertRaisesRegex(ApiError, "allowlisted"):
            client.post("server/updatePanel", {})
        with patch("urllib.request.urlopen", return_value=Response({"success": False})):
            with self.assertRaisesRegex(ApiUncertainError, "partly applied"):
                client.post("clients/add", {"client": {"email": "example"}})

    def test_semantic_openapi_digest_accepts_formatting_only(self):
        client = ApiClient("https://example.test", "secret")
        document = {"openapi": "3.0.3", "paths": {"/b": {}, "/a": {}}}
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        with (patch("xui_fork.api_client.OPENAPI_CANONICAL_SHA256_311", digest),
              patch("urllib.request.urlopen", return_value=Response(document))):
            self.assertTrue(client.verify_contract())
        with patch("urllib.request.urlopen", return_value=Response({"other": "spec"})):
            with self.assertRaisesRegex(ApiError, "differs"):
                client.verify_contract()

    def test_dynamic_web_base_path_accepts_required_contract_only(self):
        client = ApiClient("https://example.test", "secret")
        properties = dict.fromkeys(("id", "listen", "port", "protocol", "remark",
                                    "settings", "streamSettings", "sniffing", "shareAddr",
                                    "shareAddrStrategy"), {"type": "string"})
        properties["protocol"] = {"enum": ["vless"]}
        document = {
            "openapi": "3.0.3", "info": {"version": "3.x"},
            "paths": {"/random/panel/api/" + path: {method: {}}
                      for path, method in REQUIRED_OPERATIONS.items()},
            "components": {"schemas": {
                "Inbound": {"properties": properties},
                "Client": {"properties": dict.fromkeys(("id", "email", "flow", "subId"), {})},
            }},
        }
        with patch("urllib.request.urlopen", return_value=Response(document)):
            self.assertTrue(client.verify_contract())
        del document["paths"]["/random/panel/api/clients/add"]
        with patch("urllib.request.urlopen", return_value=Response(document)):
            with self.assertRaisesRegex(ApiError, "clients/add"):
                client.verify_contract()
