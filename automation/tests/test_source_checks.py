import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_checks as checks


class SourceChecksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "--quiet", "--allow-empty", "-m", "Fixture")
        return self.git("rev-parse", "HEAD")

    def test_committed_source_is_parsed_without_execution_or_worktree_substitution(self):
        marker = self.root / "executed"
        path = self.root / "app.py"
        path.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
        self.commit()
        path.write_text("invalid syntax sentinel !!!")
        result = checks.check(self.root, "settings")
        self.assertEqual(result["files_parsed"], 1)
        self.assertEqual(result["build_and_boot"], "not_run")
        self.assertFalse(marker.exists())

    def test_changes_include_renames_and_ignore_deleted_and_unchanged_invalid_files(self):
        (self.root / "unchanged.py").write_text("invalid !!!")
        (self.root / "deleted.py").write_text("invalid !!!")
        (self.root / "old.json").write_text('{}')
        base = self.commit()
        (self.root / "deleted.py").unlink()
        (self.root / "old.json").rename(self.root / "new.json")
        (self.root / "app.py").write_text("value = 1\n")
        head = self.commit()
        self.assertEqual(checks.check(self.root, "settings", base),
                         {"revision": head, "files_parsed": 2, "build_and_boot": "not_run"})

    def test_new_branch_zero_base_checks_full_tree(self):
        (self.root / "app.py").write_text("invalid !!!")
        self.commit()
        with self.assertRaises(checks.Failure):
            checks.check(self.root, "settings", "0" * 40)

    def test_symlinks_including_type_changes_are_rejected(self):
        path = self.root / "app.py"
        path.write_text("value = 1\n")
        base = self.commit()
        path.unlink()
        path.symlink_to("/etc/passwd")
        self.commit()
        with self.assertRaisesRegex(checks.Failure, "regular file"):
            checks.check(self.root, "settings", base)

    def test_invalid_sources_do_not_echo_parser_excerpts_or_raw_filename(self):
        for path, content in [('private\n::error::app.py', b'private-source-sentinel !!!'),
                              ('app.json', b'{private-source-sentinel}'),
                              ('app.toml', b'private-source-sentinel = ['),
                              ('app.py', b'\xff')]:
            with self.subTest(path=path), self.assertRaises(checks.Failure) as raised:
                checks.parse_source("settings", path, content)
            self.assertNotIn("private-source-sentinel", str(raised.exception))
            self.assertNotIn("\n::error::", str(raised.exception))

    def test_missing_base_and_revision_expressions_fail(self):
        self.commit()
        for base in ["HEAD~1", "--help", "f" * 40]:
            with self.subTest(base=base), self.assertRaises(checks.Failure):
                checks.check(self.root, "settings", base)

    def test_distro_mapping_is_validated_even_when_unchanged(self):
        mapping = "\n".join(f'[submodule "{name}"]\npath = {path}\n'
                            f'url = https://github.com/WIPOperatingSystemName/{name}.git'
                            for name, path in checks.MODULES.items())
        checks.module_mapping(mapping)
        (self.root / ".gitmodules").write_text(mapping.replace("/telorgon.git", "/other.git"))
        base = self.commit()
        (self.root / "app.py").write_text("value = 1\n")
        self.commit()
        with self.assertRaisesRegex(checks.Failure, "mapping"):
            checks.check(self.root, "distro", base)

    def test_recipes_require_pins_revisions_and_runtime_dependencies(self):
        document = {"schema": 1, "package": {"version": "1.0", "revision": 1},
                    "dependencies": {"runtime": []},
                    "sources": [{"url": "https://example.invalid/source.tar", "sha256": "a" * 64}]}
        checks.recipe(document)
        for section, field, value in [("package", "revision", True), ("package", "version", ""),
                                      ("dependencies", "runtime", "missing")]:
            changed = copy.deepcopy(document)
            changed[section][field] = value
            with self.subTest(field=field), self.assertRaises(checks.Failure):
                checks.recipe(changed)
        changed = copy.deepcopy(document)
        changed["sources"][0]["sha256"] = "mutable"
        with self.assertRaises(checks.Failure):
            checks.recipe(changed)
        with self.assertRaises(checks.Failure):
            checks.parse_source("distro", "packages/test/package.toml", b'schema = 1\n')


if __name__ == "__main__":
    unittest.main()
