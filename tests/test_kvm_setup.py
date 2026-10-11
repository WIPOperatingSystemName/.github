"""Exercise KVM setup without changing host groups or invoking sudo."""

import contextlib
import grp
import importlib.util
import io
import os
from pathlib import Path
import pwd
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("contributor_setup", Path(__file__).parents[1] / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class KvmSetupTests(unittest.TestCase):
    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.user = SimpleNamespace(pw_name="contributor", pw_uid=1000, pw_gid=1000)
        self.group = SimpleNamespace(gr_gid=991, gr_mem=[])
        stack.enter_context(patch.object(setup.sys, "platform", "linux"))
        stack.enter_context(patch.object(setup.os, "getuid", return_value=1000))
        stack.enter_context(patch.object(pwd, "getpwuid", return_value=self.user))
        self.groups = stack.enter_context(patch.object(setup.os, "getgroups", return_value=[1000]))
        self.access = stack.enter_context(patch.object(setup.os, "access", return_value=False))
        self.device = stack.enter_context(patch.object(setup.Path, "stat", return_value=SimpleNamespace(st_gid=991)))
        self.lookup = stack.enter_context(patch.object(grp, "getgrnam", return_value=self.group))
        self.terminal = stack.enter_context(patch.object(setup.sys.stdin, "isatty", return_value=True))
        stack.enter_context(patch.object(setup.shutil, "which", return_value="installed"))
        self.run = stack.enter_context(patch.object(setup, "run"))
        self.output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def test_adds_actual_normal_user_preserving_other_groups(self):
        with patch.dict(os.environ, {"USER": "root", "SUDO_USER": "someone-else"}):
            self.assertFalse(setup.configure_kvm("auto"))
        self.run.assert_called_once_with("sudo", "usermod", "-aG", "kvm", "--", "contributor", interactive=True)
        self.assertIn("existing group memberships were preserved", self.output.getvalue())
        self.assertIn("newgrp kvm", self.output.getvalue())
        self.assertIn("--kvm check", self.output.getvalue())

    def test_rerun_with_pending_membership_only_requests_new_session(self):
        self.group.gr_mem = ["contributor"]
        self.assertFalse(setup.configure_kvm("auto"))
        self.run.assert_not_called()
        self.assertIn("already belongs to kvm", self.output.getvalue())
        self.assertIn("Log out", self.output.getvalue())

    def test_accessible_device_needs_no_group_change(self):
        self.access.return_value = True
        self.assertTrue(setup.configure_kvm("auto"))
        self.access.assert_called_once_with(Path("/dev/kvm"), os.R_OK | os.W_OK)
        self.run.assert_not_called()
        self.assertIn("QEMU will probe KVM at launch", self.output.getvalue())

    def test_active_supplementary_or_primary_group_cannot_fix_denied_access(self):
        for primary in (False, True):
            with self.subTest(primary=primary):
                self.groups.return_value = [1000] if primary else [1000, 991]
                self.user.pw_gid = 991 if primary else 1000
                self.assertFalse(setup.configure_kvm("auto"))
        self.run.assert_not_called()
        self.assertIn("check device permissions", self.output.getvalue())

    def test_missing_device_does_not_try_to_create_groups_or_enable_virtualization(self):
        self.device.side_effect = FileNotFoundError
        self.assertFalse(setup.configure_kvm("auto"))
        self.lookup.assert_not_called()
        self.run.assert_not_called()
        self.assertIn("group membership cannot enable it", self.output.getvalue())

    def test_missing_group_or_different_device_owner_does_not_modify_user(self):
        self.lookup.side_effect = KeyError("kvm")
        self.assertFalse(setup.configure_kvm("auto"))
        self.lookup.side_effect = None
        self.device.return_value.st_gid = 992
        self.assertFalse(setup.configure_kvm("auto"))
        self.run.assert_not_called()

    def test_noninteractive_setup_prints_manual_command_without_sudo(self):
        self.terminal.return_value = False
        self.assertFalse(setup.configure_kvm("auto"))
        self.run.assert_not_called()
        self.assertIn("sudo usermod -aG kvm -- contributor", self.output.getvalue())
        self.assertIn("skipped without an interactive terminal", self.output.getvalue())

    def test_check_is_read_only_even_in_an_interactive_terminal(self):
        self.assertFalse(setup.configure_kvm("check"))
        self.run.assert_not_called()
        self.access.return_value = True
        self.assertTrue(setup.configure_kvm("check"))
        self.run.assert_not_called()

    def test_skip_and_non_linux_leave_host_untouched(self):
        self.assertFalse(setup.configure_kvm("skip"))
        with patch.object(setup.sys, "platform", "darwin"):
            self.assertFalse(setup.configure_kvm("auto"))
        self.device.assert_not_called()
        self.run.assert_not_called()

    def test_refuses_to_configure_root(self):
        self.user.pw_uid = 0
        with self.assertRaisesRegex(setup.SetupError, "normal Linux user"):
            setup.configure_kvm("auto")
        self.run.assert_not_called()

    def test_failed_usermod_does_not_report_success(self):
        self.run.side_effect = setup.SetupError("sudo usermod failed")
        with self.assertRaisesRegex(setup.SetupError, "usermod failed"):
            setup.configure_kvm("auto")
        self.assertNotIn("Added contributor", self.output.getvalue())

    def test_missing_sudo_or_usermod_reports_required_tools(self):
        with patch.object(setup.shutil, "which", return_value=None):
            with self.assertRaisesRegex(setup.SetupError, "requires sudo and usermod"):
                setup.configure_kvm("auto")
        self.run.assert_not_called()

    def test_check_cli_skips_workspace_github_and_wslg_setup(self):
        with patch.object(setup.sys, "argv", ["setup.py", "--kvm", "check"]), \
                patch.object(setup, "prepare_checkout") as checkout, \
                patch.object(setup, "configure_wslg") as wslg:
            self.access.return_value = True
            setup.main()
            self.access.return_value = False
            with self.assertRaisesRegex(setup.SetupError, "verification did not pass"):
                setup.main()
        checkout.assert_not_called()
        wslg.assert_not_called()
        self.run.assert_not_called()

    def test_workspace_cli_defaults_to_auto_and_honors_skip(self):
        for arguments, expected in (([], "auto"), (["--kvm", "skip"], "skip")):
            with self.subTest(arguments=arguments), \
                    patch.object(setup.sys, "argv", ["setup.py", *arguments]), \
                    patch.object(setup, "prepare_checkout", return_value={}), \
                    patch.object(setup, "login", return_value="contributor"), \
                    patch.object(setup, "configure_kvm", return_value=False) as kvm, \
                    patch.object(setup, "configure_wslg"):
                setup.main()
                kvm.assert_called_once_with(expected)


if __name__ == "__main__":
    unittest.main()
