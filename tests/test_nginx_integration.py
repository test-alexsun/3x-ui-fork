import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from xui_fork.nginx_manager import render_panel_site
from xui_fork.ssl_manager import require_certificate


@unittest.skipUnless(shutil.which("nginx") and shutil.which("openssl"),
                     "Nginx/OpenSSL unavailable")
class NginxSyntaxIntegration(unittest.TestCase):
    def test_generated_panel_site_passes_real_nginx_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            cert = root / "cert.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", str(key), "-out", str(cert), "-days", "30",
                            "-subj", "/CN=panel.example.test",
                            "-addext", "subjectAltName=DNS:panel.example.test"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            require_certificate(cert, key, "panel.example.test")
            site = root / "site.conf"
            site.write_text(render_panel_site("panel.example.test", cert, key, 18080))
            config = root / "nginx.conf"
            config.write_text(f"error_log stderr notice;\npid {root / 'nginx.pid'};\n"
                              f"events {{}}\nhttp {{ include {site}; }}\n")
            subprocess.run(["nginx", "-t", "-p", str(root), "-c", str(config)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
