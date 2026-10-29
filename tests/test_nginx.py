import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from xui_fork.nginx_manager import NginxError, apply_managed_config, render_panel_site
from xui_fork.ssl_manager import CertificateError, require_certificate


class NginxTests(unittest.TestCase):
    def test_render_rejects_injection(self):
        with self.assertRaises(ValueError):
            render_panel_site("bad;return 200", PurePosixPath("/cert.pem"), PurePosixPath("/key.pem"), 8080)
        content = render_panel_site("panel.example.org", PurePosixPath("/cert.pem"),
                                    PurePosixPath("/key.pem"), 8080)
        self.assertIn("proxy_pass http://127.0.0.1:8080", content)

    def test_apply_idempotent_and_restore_on_failed_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "3x-ui-fork.conf"
            first = render_panel_site("panel.example.org", PurePosixPath("/cert.pem"),
                                      PurePosixPath("/key.pem"), 8080)
            second = render_panel_site("panel.example.org", PurePosixPath("/cert.pem"),
                                       PurePosixPath("/key.pem"), 8081)
            with patch("xui_fork.nginx_manager._run") as run:
                self.assertTrue(apply_managed_config(target, first))
                self.assertFalse(apply_managed_config(target, first))
                self.assertEqual(run.call_count, 2)
                run.side_effect = OSError("reload failed")
                with self.assertRaisesRegex(NginxError, "restored"):
                    apply_managed_config(target, second)
            self.assertEqual(target.read_text(), first)

    def test_foreign_file_and_missing_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "3x-ui-fork.conf"
            target.write_text("# other owner\n")
            content = render_panel_site("panel.example.org", PurePosixPath("/cert.pem"),
                                        PurePosixPath("/key.pem"), 8080)
            with self.assertRaisesRegex(NginxError, "foreign"):
                apply_managed_config(target, content)
            with self.assertRaises(CertificateError):
                require_certificate(Path(directory) / "none", Path(directory) / "key",
                                    "panel.example.org")
