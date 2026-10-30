import contextlib
import io
import unittest

from xui_fork.cli import main


class CliTests(unittest.TestCase):
    def test_unimplemented_modes_fail_instead_of_reporting_success(self):
        for mode in ("install", "update", "repair", "rollback", "uninstall"):
            with self.subTest(mode=mode), contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(main([mode]), 2)
                self.assertIn("error:", error.getvalue())
