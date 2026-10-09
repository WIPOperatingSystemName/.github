"""Exercise data-only validation and the handoff to the paid review."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import controller
import security_review
import static_checks as checks
from test_controller import fixture, revision


class StaticTests(unittest.TestCase):
    def setUp(self):
        self.bundle = fixture()
        self.data = {"bundle_digest": self.bundle["digest"], "changes": [{"repository": "distro", "files": [
            {"path": "tools/check.py", "after": "raise RuntimeError('must never run')\n"}]}]}
        self.mapping = "\n".join(f'[submodule "{short}"]\npath = {path}\nurl = https://github.com/{common.ORG}/{short}.git'
                                  for short, path in common.MODULES.items())

    def report(self):
        return {"policy": checks.POLICY, "bundle_digest": self.bundle["digest"], "integration_head": revision(3),
                "source_digest": controller.digest(self.data), "checks": checks.CHECKS,
                "files_checked": 1, "build_and_boot": "not_run"}

    def test_python_source_is_parsed_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executed"
            self.data["changes"][0]["files"][0]["after"] = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            self.assertEqual(checks.parse_changes(self.data), 1)
            self.assertFalse(marker.exists())

    def test_malformed_python_json_and_toml_are_rejected(self):
        for path, content in [("bad.py", "def invalid(:"), ("bad.json", '{"unterminated":'), ("Cargo.toml", "[bad")]:
            with self.subTest(path=path):
                self.data["changes"][0]["files"][0].update(path=path, after=content)
                with self.assertRaises(common.Failure):
                    checks.parse_changes(self.data)

    def test_rust_and_deleted_sources_are_not_claimed_as_compiled(self):
        self.data["changes"][0]["files"] = [{"path": "src/main.rs", "after": "fn main() {}"},
                                             {"path": "old.py", "after": None}]
        self.assertEqual(checks.parse_changes(self.data), 2)
        self.assertEqual(self.report()["build_and_boot"], "not_run")

    def test_module_mapping_rejects_redirects_hooks_and_extra_sections(self):
        checks.module_mapping(self.mapping)
        for text in [self.mapping.replace("https://github.com", "https://evil.example"),
                     self.mapping + "\nupdate = !some-command\n", self.mapping + "\n[DEFAULT]\nupdate = checkout\n",
                     self.mapping + '\n[submodule "extra"]\npath = sources/extra\nurl = https://evil.example\n']:
            with self.subTest(text=text[-80:]), self.assertRaises(common.Failure):
                checks.module_mapping(text)

    def test_recipe_metadata_requires_immutable_sources_and_runtime_dependencies(self):
        document = {"schema": 1, "package": {"version": "1.0", "revision": 1},
                    "dependencies": {"runtime": []}, "sources": [{"url": "https://example.invalid/source.tar", "sha256": "a" * 64}]}
        checks.recipe(document)
        for field, value in [("revision", 0), ("revision", True), ("version", "")]:
            bad = copy.deepcopy(document)
            bad["package"][field] = value
            with self.assertRaises(common.Failure):
                checks.recipe(bad)
        bad = copy.deepcopy(document)
        bad["sources"][0]["sha256"] = "main"
        with self.assertRaises(common.Failure):
            checks.recipe(bad)
        bad = copy.deepcopy(document)
        del bad["dependencies"]["runtime"]
        with self.assertRaises(common.Failure):
            checks.recipe(bad)

    def test_receipts_reject_other_inputs_and_false_runtime_claims(self):
        for extra in [{"bundle_digest": "other"}, {"integration_head": revision(9)}, {"source_digest": "bad"},
                      {"checks": []}, {"files_checked": 0}, {"build_and_boot": "passed"}]:
            with self.subTest(extra=extra), self.assertRaises(common.Failure):
                checks.validate_report({**self.report(), **extra}, self.bundle, revision(3))

    def test_modified_source_artifact_cannot_reach_paid_review(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path.cwd()
            try:
                os.chdir(directory)
                Path("static-checks.json").write_text(json.dumps(self.report()))
                Path("checked-source.json").write_text(json.dumps(self.data))
                self.assertEqual(checks.load_checked_data(self.bundle, revision(3))[0], self.data)
                changed = copy.deepcopy(self.data)
                changed["changes"][0]["files"][0]["after"] = "print('substitution')"
                Path("checked-source.json").write_text(json.dumps(changed))
                with self.assertRaises(common.Failure):
                    checks.load_checked_data(self.bundle, revision(3))
            finally:
                os.chdir(old)

    def test_main_writes_only_hashed_source_and_explicit_static_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path.cwd()
            try:
                os.chdir(directory)
                env = {"HUB_PR": "99", "HUB_HEAD": revision(3), "GITHUB_STEP_SUMMARY": str(Path(directory) / "summary.md")}
                with patch.dict(os.environ, env), patch.object(checks, "trusted_dispatch"), \
                        patch.object(checks, "load_bundle", return_value=({}, self.bundle)), patch.object(checks, "fresh"), \
                        patch.object(checks, "candidate_data", return_value=self.data), patch.object(checks, "source", return_value=self.mapping):
                    checks.main()
                data, report = checks.load_checked_data(self.bundle, revision(3))
                self.assertEqual(data, self.data)
                self.assertEqual(report, self.report())
                self.assertIn("not run", Path(env["GITHUB_STEP_SUMMARY"]).read_text())
            finally:
                os.chdir(old)

    def test_syntax_failure_stops_before_generating_review_inputs(self):
        self.data["changes"][0]["files"][0]["after"] = "def invalid(:"
        with tempfile.TemporaryDirectory() as directory:
            old = Path.cwd()
            try:
                os.chdir(directory)
                with patch.dict(os.environ, {"HUB_PR": "99", "HUB_HEAD": revision(3)}), \
                        patch.object(checks, "trusted_dispatch"), patch.object(checks, "load_bundle", return_value=({}, self.bundle)), \
                        patch.object(checks, "fresh"), patch.object(checks, "candidate_data", return_value=self.data), \
                        patch.object(checks, "source", return_value=self.mapping), self.assertRaises(common.Failure):
                    checks.main()
                self.assertFalse(Path("checked-source.json").exists())
                self.assertFalse(Path("static-checks.json").exists())
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
