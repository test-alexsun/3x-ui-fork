import tempfile
import unittest
from pathlib import Path

from xui_fork.planner import Paths, plan


class PlannerTests(unittest.TestCase):
    def test_fresh_install_plan_and_foreign_install_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = Paths(root / "panel", root / "db", root / "unit", root / "state",
                          root / "3x-ui-fork.conf", root / "x-ui")
            inventory = {"supported": True, "root": True, "commands": {"systemctl": True},
                         "ports": {"2053": True}}
            fresh = plan("install", paths=paths, inventory=inventory)
            self.assertTrue(fresh["ready_to_apply"])
            self.assertEqual(fresh["steps"][2]["effect"], "bind 127.0.0.1 before start")
            paths.database.mkdir()
            conflict = plan("install", paths=paths, inventory=inventory)
            self.assertFalse(conflict["ready_to_apply"])
            self.assertIn("existing panel", conflict["blockers"][0])

    def test_dry_run_reports_blockers_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = Paths(root / "panel", root / "db", root / "unit", root / "state",
                          root / "3x-ui-fork.conf", root / "x-ui")
            inventory = {"supported": False, "root": False,
                         "commands": {"systemctl": True}, "ports": {"2053": False}}
            result = plan("install", paths=paths, inventory=inventory)
            self.assertEqual(len(result["blockers"]), 3)
            self.assertEqual(list(root.iterdir()), [])
