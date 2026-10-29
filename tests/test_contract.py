import json
import unittest
from unittest.mock import patch

from xui_fork.api_client import ApiClient, ApiError, normalize_embedded_json
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

    def test_token_remote_http_and_unknown_version_rejected(self):
        with self.assertRaisesRegex(ValueError, "TLS"):
            ApiClient("http://example.test", "secret")
        self.assertFalse(version_supported("3.12.0"))
        self.assertTrue(profile_supported("MASQUE", "3.11.0"))
        self.assertFalse(profile_supported("MASQUE", "3.12.0"))
        self.assertEqual(normalize_embedded_json('{"clients":[]}'), {"clients": []})
