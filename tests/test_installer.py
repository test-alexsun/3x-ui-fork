import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xui_fork.installer import InstallationNotReady, _download, extract_release, fetch_release


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

    def test_extract_release_rejects_traversal_and_accepts_official_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "release.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name in ("x-ui/x-ui", "x-ui/x-ui.sh", "x-ui/x-ui.service.debian"):
                    body = b"unit" if name.endswith(".debian") else b"binary"
                    info = tarfile.TarInfo(name)
                    info.size = len(body)
                    tar.addfile(info, io.BytesIO(body))
            self.assertTrue((extract_release(archive, root / "stage") / "x-ui").is_file())
            bad = root / "bad.tar.gz"
            with tarfile.open(bad, "w:gz") as tar:
                info = tarfile.TarInfo("../escape")
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
            with self.assertRaisesRegex(InstallationNotReady, "unsafe"):
                extract_release(bad, root / "bad-stage")
            self.assertFalse((root / "escape").exists())
