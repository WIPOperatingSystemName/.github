"""Exercise setup with real local Git repositories and a fake GitHub CLI."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("contributor_setup", Path(__file__).parents[1] / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
REAL_RUN = setup.run


def command(*args):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, check=True).stdout.strip()


class FakeGitHub:
    def __init__(self):
        self.forks = {}
        self.creations = []
        self.logins = 0

    def run(self, *args, **kwargs):
        if args[0] != "gh":
            return REAL_RUN(*args, **kwargs)
        if args[1:3] == ("auth", "status"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ("auth", "login"):
            self.logins += 1
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1:3] == ("auth", "setup-git"):
            assert args[3:] == ("--hostname", "github.com")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[1] == "api":
            assert args[2:4] == ("--hostname", "github.com")
            endpoint = args[4]
            if endpoint == "user":
                output = "contributor\n"
            else:
                repository = endpoint.split("/")[2]
                assert endpoint == f"repos/{setup.ORG}/{repository}/forks?per_page=100"
                assert "--paginate" in args
                output = self.forks.get(repository, "")
                if output:
                    output += "\n"
            return subprocess.CompletedProcess(args, 0, output, "")
        if args[1:3] == ("repo", "fork"):
            assert args[4:] == ("--clone=false", "--remote=false")
            repository = args[3].rsplit("/", 1)[1]
            self.creations.append(repository)
            self.forks[repository] = f"contributor/{repository}"
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"Unexpected GitHub command: {args}")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "work folder"
        # Keep local tests independent from the developer's Git configuration.
        self.environment = patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": str(Path(self.temp.name) / "no-global-config"),
            "GIT_CONFIG_NOSYSTEM": "1",
        })
        self.environment.start()
        self.distro = self.workspace / "distro"
        self.checkouts = {"distro": self.distro}
        self.checkouts.update({name: self.distro / relative for name, relative in setup.MODULES.items()})
        for name, path in self.checkouts.items():
            path.mkdir(parents=True)
            command("git", "init", "--initial-branch=main", path)
            command("git", "-C", path, "config", "user.name", "Test Contributor")
            command("git", "-C", path, "config", "user.email", "contributor@example.test")
            command("git", "-C", path, "remote", "add", "origin",
                    f"https://github.com/{setup.ORG}/{name}.git")
            (path / "README.md").write_text("Original content\n")
            command("git", "-C", path, "add", "README.md")
            command("git", "-C", path, "commit", "-m", "Initial fixture")
        (self.distro / ".gitmodules").write_text("".join(
            f'[submodule "{name}"]\n\tpath = {relative}\n\turl = https://github.com/{setup.ORG}/{name}.git\n'
            for name, relative in setup.MODULES.items()
        ))
        command("git", "-C", self.distro, "add", ".gitmodules")
        command("git", "-C", self.distro, "commit", "-m", "Component mapping")

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def invoke(self, github):
        with patch.object(setup, "run", github.run), patch.object(setup.shutil, "which", return_value="installed"), \
                patch.object(setup.sys, "argv", ["setup.py", "--workspace", str(self.workspace)]), \
                contextlib.redirect_stdout(io.StringIO()):
            setup.main()

    def test_full_setup_creates_seven_forks_then_reruns_without_changes(self):
        sdk = self.checkouts["telorgon"]
        command("git", "-C", sdk, "switch", "-c", "feature/in-progress")
        (sdk / "README.md").write_text("Staged contribution\n")
        command("git", "-C", sdk, "add", "README.md")
        (sdk / "README.md").write_text("More unstaged work\n")
        (sdk / "new-file.txt").write_text("Untracked work\n")
        original_head = command("git", "-C", sdk, "rev-parse", "HEAD")
        original_index = command("git", "-C", sdk, "diff", "--cached")
        original_status = command("git", "-C", sdk, "status", "--porcelain")
        original_modules = (self.distro / ".gitmodules").read_bytes()
        github = FakeGitHub()
        self.invoke(github)
        self.invoke(github)
        self.assertEqual(github.creations, list(self.checkouts))
        for name, path in self.checkouts.items():
            self.assertEqual(command("git", "-C", path, "remote", "get-url", "origin"),
                             f"https://github.com/{setup.ORG}/{name}.git")
            self.assertEqual(command("git", "-C", path, "remote", "get-url", "fork"),
                             f"https://github.com/contributor/{name}.git")
            self.assertEqual(command("git", "-C", path, "config", "remote.pushDefault"), "fork")
        self.assertEqual(command("git", "-C", sdk, "branch", "--show-current"), "feature/in-progress")
        self.assertEqual(command("git", "-C", sdk, "rev-parse", "HEAD"), original_head)
        self.assertEqual(command("git", "-C", sdk, "diff", "--cached"), original_index)
        self.assertEqual(command("git", "-C", sdk, "status", "--porcelain"), original_status)
        self.assertEqual((self.distro / ".gitmodules").read_bytes(), original_modules)

    def test_reuses_renamed_personal_forks(self):
        github = FakeGitHub()
        github.forks = {name: f"contributor/my-{name}" for name in self.checkouts}
        self.invoke(github)
        self.assertEqual(github.creations, [])
        self.assertEqual(command("git", "-C", self.distro, "remote", "get-url", "fork"),
                         "https://github.com/contributor/my-distro.git")

    def test_refuses_unrelated_checkout_before_using_github(self):
        command("git", "-C", self.distro, "remote", "set-url", "origin", "https://github.com/other/distro.git")
        github = FakeGitHub()
        with self.assertRaisesRegex(setup.SetupError, "origin must point"):
            self.invoke(github)
        self.assertEqual(github.creations, [])

    def test_refuses_unexpected_submodule_urls_before_initializing(self):
        command("git", "-C", self.distro, "config", "--file", ".gitmodules",
                "submodule.shell.url", "https://github.com/other/shell.git")
        with self.assertRaisesRegex(setup.SetupError, "Unexpected submodule URL"):
            setup.prepare_checkout(self.workspace)

    def test_refuses_cached_submodule_url_override(self):
        command("git", "-C", self.distro, "config", "submodule.shell.url", "https://github.com/other/shell.git")
        with self.assertRaisesRegex(setup.SetupError, "Unexpected local submodule URL"):
            setup.prepare_checkout(self.workspace)

    def test_preserves_existing_conflicting_fork_remote(self):
        path = self.checkouts["telorgon"]
        command("git", "-C", path, "remote", "add", "fork", "https://github.com/other/telorgon.git")
        with self.assertRaisesRegex(setup.SetupError, "left unchanged"):
            setup.connect_fork(path, "contributor/telorgon")
        self.assertEqual(command("git", "-C", path, "remote", "get-url", "fork"),
                         "https://github.com/other/telorgon.git")

    def test_refuses_conflicting_explicit_push_destination(self):
        path = self.checkouts["telorgon"]
        command("git", "-C", path, "remote", "add", "fork", "git@github.com:contributor/telorgon.git")
        command("git", "-C", path, "config", "remote.fork.pushurl", "https://github.com/other/telorgon.git")
        with self.assertRaisesRegex(setup.SetupError, "left unchanged"):
            setup.connect_fork(path, "contributor/telorgon")

    def test_fork_creation_waits_for_github_visibility(self):
        github = FakeGitHub()
        with patch.object(setup, "run", github.run), \
                patch.object(setup, "find_fork", side_effect=[None, None, "contributor/shell"]), \
                patch.object(setup.time, "sleep") as sleep, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.ensure_fork("shell", "contributor"), "contributor/shell")
        self.assertEqual(github.creations, ["shell"])
        sleep.assert_called_once_with(2)

    def test_missing_dependency_stops_before_creating_any_fork(self):
        github = FakeGitHub()
        with patch.object(setup.shutil, "which", return_value=None), \
                patch.object(setup.sys, "argv", ["setup.py", "--workspace", str(self.workspace)]), \
                patch.object(setup, "run", github.run), self.assertRaisesRegex(setup.SetupError, "Install git"):
            setup.main()
        self.assertEqual(github.creations, [])

    def test_accepts_canonical_ssh_and_https_remotes_without_credentials(self):
        expected = "contributor/telorgon"
        for url in ("https://github.com/Contributor/telorgon.git", "git@github.com:Contributor/telorgon.git"):
            self.assertEqual(setup.repo_name(url), expected)
        for url in ("https://token@github.com/contributor/telorgon.git", "https://other.test/contributor/telorgon.git"):
            self.assertIsNone(setup.repo_name(url))


if __name__ == "__main__":
    unittest.main()
