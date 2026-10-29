import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xui_fork.installer import InstallationNotReady, _download, fetch_release


class InstallerTests(unittest.TestCase):
    def test_download_verifies_digest_and_never_keeps_bad_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact"
            body = b"verified upstream bytes"
            with patch("urllib.request.urlopen", return_value=io.BytesIO(body)):
                result = _download("https://example.test/artifact", target,
                                   hashlib.sha256(body).hexdigest())
            self.assertEqual(result.read_bytes(), body)
            with self.assertRaises(InstallationNotReady):
                _download("https://example.test/artifact", target, "0" * 64)
            bad = Path(directory) / "bad"
            with patch("urllib.request.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaisesRegex(InstallationNotReady, "digest mismatch"):
                    _download("https://example.test/artifact", bad, "0" * 64)
            self.assertFalse(bad.exists())

    def test_unknown_arch_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("urllib.request.urlopen") as open_:
                with self.assertRaisesRegex(InstallationNotReady, "architecture"):
                    fetch_release("mips", Path(directory))
                open_.assert_not_called()
