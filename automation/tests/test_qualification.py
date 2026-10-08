import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import controller
import qualify
from test_controller import fixture, revision


class ModuleAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = fixture()
        qualify.git(self.root, "init", "--quiet", "--initial-branch=main", "--template=")
        self.mapping = "\n".join(f'[submodule "{short}"]\npath = {path}\nurl = https://github.com/{common.ORG}/{short}.git'
                                  for short, path in common.MODULES.items())
        (self.root / ".gitmodules").write_text(self.mapping)
        qualify.git(self.root, "add", ".gitmodules")
        for short, path in common.MODULES.items():
            qualify.git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{self.bundle['pins'][short]},{path}")
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "core.hooksPath=/dev/null", "commit", "-m", "fixture"], capture_output=True, check=True)

    def test_validated_pins_and_canonical_urls(self):
        qualify.audit_modules(self.root, self.bundle)

    def test_candidate_cannot_substitute_remote(self):
        (self.root / ".gitmodules").write_text(self.mapping.replace("https://github.com", "https://evil.example"))
        with self.assertRaises(common.Failure):
            qualify.audit_modules(self.root, self.bundle)

    def test_candidate_cannot_add_a_hook_setting(self):
        (self.root / ".gitmodules").write_text(self.mapping + "\nupdate = !some-command\n")
        with self.assertRaises(common.Failure):
            qualify.audit_modules(self.root, self.bundle)

    def test_tree_pin_cannot_differ_from_manifest(self):
        self.bundle["pins"]["settings"] = revision(999)
        with self.assertRaises(common.Failure):
            qualify.audit_modules(self.root, self.bundle)

    def test_fork_heads_are_fetched_from_target_pr_refs(self):
        calls = []
        def fetch(root, short, ref, head):
            calls.append((short, ref, head))
            root.mkdir(parents=True, exist_ok=True)
        with patch.object(qualify, "checkout", side_effect=fetch):
            qualify.fetch_candidate(self.root, self.bundle, revision(3))
        self.assertEqual(calls[0], ("distro", "refs/heads/integration/100", revision(3)))
        self.assertIn(("settings", "refs/pull/2/head", revision(31)), calls)
        self.assertIn(("telorgon", "refs/pull/1/head", revision(30)), calls)

    def test_credential_guard_before_candidate_execution(self):
        with patch.object(qualify, "trusted_dispatch"), patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}), \
                patch.object(qualify, "qualify") as execute:
            with self.assertRaises(common.Failure):
                qualify.main()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
