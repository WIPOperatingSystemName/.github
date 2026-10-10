"""Qualify WSLg setup against temporary configs, never the host configuration."""

import argparse
import base64
import codecs
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("contributor_setup", Path(__file__).parents[1] / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / ".wslgconfig"

    def test_merges_into_existing_section_preserving_comments_and_other_sections(self):
        original = ("; user's configuration\r\n[other]\r\n"
                    "WESTON_RDP_MONITOR_REFRESH_RATE=75\r\n[system-distro-env]\r\n"
                    "WESTON_DEBUG_PROTOCOL=true\r\n"
                    "  WESTON_RDP_MONITOR_REFRESH_RATE = 60  ; keep this comment\r\n")
        raw = codecs.BOM_UTF8 + original.encode()
        self.config.write_bytes(raw)
        backup = setup.write_wslg_rate(self.config, 144)
        self.assertEqual(backup.read_bytes(), raw)
        self.assertEqual(self.config.read_bytes(), codecs.BOM_UTF8 + original.replace(
            " = 60  ;", " = 144  ;").encode())

    def test_adds_key_to_existing_section_and_handles_missing_final_newline(self):
        for original in ("[system-distro-env]", "[system-distro-env]\nOTHER=true"):
            with self.subTest(original=original):
                merged = setup.merge_wslg_rate(original, 144)
                self.assertEqual(merged.count("[system-distro-env]"), 1)
                self.assertEqual(setup.configured_wslg_rate(merged), 144)
                if "OTHER" in original:
                    self.assertIn("OTHER=true", merged)
        self.assertEqual(setup.merge_wslg_rate("[other]\nFOO=bar", 144),
                         "[other]\nFOO=bar\n[system-distro-env]\nWESTON_RDP_MONITOR_REFRESH_RATE=144\n")

    def test_creates_missing_config_and_is_idempotent(self):
        self.assertIsNone(setup.write_wslg_rate(self.config, 144))
        self.assertEqual(setup.configured_wslg_rate(self.config.read_text()), 144)
        original_stat = self.config.stat()
        self.assertIsNone(setup.write_wslg_rate(self.config, 144))
        self.assertEqual(self.config.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertEqual(list(self.config.parent.glob("*.bak*")), [])

    def test_does_not_overwrite_previous_backups(self):
        self.config.write_text("[system-distro-env]\nWESTON_RDP_MONITOR_REFRESH_RATE=60\n")
        first = setup.write_wslg_rate(self.config, 144)
        first_bytes = first.read_bytes()
        second = setup.write_wslg_rate(self.config, 75)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), first_bytes)
        self.assertIn(b"=144", second.read_bytes())

    def test_preserves_utf16_byte_order(self):
        for bom, encoding in ((codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")):
            with self.subTest(encoding=encoding):
                original = "[system-distro-env]\r\n; café\r\nWESTON_RDP_MONITOR_REFRESH_RATE=60\r\n"
                raw = bom + original.encode(encoding)
                self.config.write_bytes(raw)
                backup = setup.write_wslg_rate(self.config, 144)
                self.assertEqual(backup.read_bytes(), raw)
                self.assertEqual(self.config.read_bytes(), bom + original.replace("=60", "=144").encode(encoding))

    def test_refuses_ambiguous_or_invalid_configuration_without_writing(self):
        for original in ("[system-distro-env]\n[system-distro-env]\n",
                         "[system-distro-env]\nWESTON_RDP_MONITOR_REFRESH_RATE=60\n"
                         "WESTON_RDP_MONITOR_REFRESH_RATE=75\n",
                         "[system-distro-env]\nWESTON_RDP_MONITOR_REFRESH_RATE=invalid\n"):
            with self.subTest(original=original):
                self.config.write_text(original)
                with self.assertRaises(setup.SetupError):
                    setup.write_wslg_rate(self.config, 144)
                self.assertEqual(self.config.read_text(), original)
                self.assertEqual(list(self.config.parent.glob("*.bak*")), [])

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary_file(self):
        original = b"[other]\nFOO=bar\n"
        self.config.write_bytes(original)
        with patch.object(setup.os, "replace", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                setup.write_wslg_rate(self.config, 144)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(list(self.config.parent.glob(".wslgconfig-*")), [])

    def test_refuses_symlink_without_changing_target(self):
        target = self.config.with_name("target")
        target.write_bytes(b"original")
        self.config.symlink_to(target)
        with self.assertRaisesRegex(setup.SetupError, "symlink"):
            setup.write_wslg_rate(self.config, 144)
        self.assertEqual(target.read_bytes(), b"original")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / ".wslgconfig"
        self.displays = [dict(name="display1", width=2560, height=1440, primary=True, rate=144),
                         dict(name="display2", width=1920, height=1080, primary=False, rate=60)]
        for name, value in (("is_wsl", True), ("windows_wslg_info", (self.config, self.displays))):
            mock = patch.object(setup, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        stdout = contextlib.redirect_stdout(io.StringIO())
        stdout.__enter__()
        self.addCleanup(stdout.__exit__, None, None, None)

    def test_selects_requested_monitor_and_never_shuts_down_wsl(self):
        with patch.object(setup.sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", side_effect=["invalid", "3", "2"]), \
                patch.object(setup, "verify_wslg_rate", return_value=False) as verify, \
                patch.object(setup.subprocess, "run") as commands:
            setup.configure_wslg("auto")
        self.assertEqual(setup.configured_wslg_rate(self.config.read_text()), 60)
        verify.assert_called_once_with(60)
        commands.assert_not_called()

    def test_enter_keeps_existing_custom_setting_without_backup(self):
        self.config.write_text("[system-distro-env]\nWESTON_RDP_MONITOR_REFRESH_RATE=100\n")
        original = self.config.read_bytes()
        with patch.object(setup.sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", return_value=""), patch.object(setup, "verify_wslg_rate"):
            setup.configure_wslg("auto")
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(list(self.config.parent.glob("*.bak*")), [])

    def test_skips_noninteractive_setup_without_writing(self):
        with patch.object(setup.sys.stdin, "isatty", return_value=False):
            setup.configure_wslg("auto")
        self.assertFalse(self.config.exists())

    def test_explicit_rate_supports_noninteractive_use_and_failed_detection(self):
        with patch.object(setup, "windows_wslg_info", return_value=(self.config, [])), \
                patch.object(setup.sys.stdin, "isatty", return_value=False), \
                patch.object(setup, "verify_wslg_rate"):
            setup.configure_wslg(120)
        self.assertEqual(setup.configured_wslg_rate(self.config.read_text()), 120)

    def test_skip_and_native_linux_never_call_windows(self):
        with patch.object(setup, "windows_wslg_info") as windows:
            setup.configure_wslg("skip")
            with patch.object(setup, "is_wsl", return_value=False):
                setup.configure_wslg("auto")
                with self.assertRaisesRegex(setup.SetupError, "only available inside WSL"):
                    setup.configure_wslg(144)
        windows.assert_not_called()

    def test_verification_uses_latest_log_value_and_reports_missing_log(self):
        log = self.config.with_name("weston.log")
        self.assertFalse(setup.verify_wslg_rate(144, log))
        log.write_text("rdp_monitor_refresh_rate: 60000\nrdp_monitor_refresh_rate: 144000\n")
        self.assertTrue(setup.verify_wslg_rate(144, log))
        self.assertFalse(setup.verify_wslg_rate(60, log))

    def test_check_mode_skips_github_setup_and_does_not_write(self):
        self.config.write_text("[system-distro-env]\nWESTON_RDP_MONITOR_REFRESH_RATE=144\n")
        original = self.config.read_bytes()
        with patch.object(setup.sys, "argv", ["setup.py", "--wslg-refresh-rate", "check"]), \
                patch.object(setup, "verify_wslg_rate", return_value=True) as verify, \
                patch.object(setup, "prepare_checkout") as checkout:
            setup.main()
        verify.assert_called_once_with(144)
        checkout.assert_not_called()
        self.assertEqual(self.config.read_bytes(), original)
        with patch.object(setup, "verify_wslg_rate", return_value=False):
            with self.assertRaisesRegex(setup.SetupError, "verification did not pass"):
                setup.configure_wslg("check")

    def test_rate_arguments(self):
        for value in ("auto", "skip", "check"):
            self.assertEqual(setup.refresh_option(value), value)
        self.assertEqual(setup.refresh_option("144"), 144)
        for value in ("0", "1", "-1", "1001", "144.5", "no"):
            with self.assertRaises(argparse.ArgumentTypeError):
                setup.refresh_option(value)

    def test_windows_query_uses_encoded_command_and_maps_path_with_spaces(self):
        # Exercise the real bridge with synthetic Windows responses, never a shell.
        info = {"config_path": r"C:\Users\Name With Spaces\.wslgconfig", "displays": self.displays}
        with patch.object(setup.shutil, "which", return_value="installed"), \
                patch.object(setup.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, json.dumps(info), "")) as command, \
                patch.object(setup, "run", return_value=subprocess.CompletedProcess(
                    [], 0, "/mnt/c/Users/Name With Spaces/.wslgconfig\n", "")) as mapper:
            config, displays = windows_info()
        self.assertEqual(str(config), "/mnt/c/Users/Name With Spaces/.wslgconfig")
        self.assertEqual(displays, self.displays)
        mapper.assert_called_once_with("wslpath", "-u", info["config_path"])
        encoded = command.call_args.args[0][-1]
        script = base64.b64decode(encoded).decode("utf-16-le")
        self.assertIn("EnumDisplaySettings", script)


# Preserve the real read-only bridge while workflow fixtures mock it.
windows_info = setup.windows_wslg_info


if __name__ == "__main__":
    unittest.main()
