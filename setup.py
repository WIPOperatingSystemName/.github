#!/usr/bin/env python3
"""Prepare one contributor workspace with canonical checkouts and personal forks."""

import argparse
import base64
import codecs
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time


ORG = "WIPOperatingSystemName"
MODULES = {
    "telorgon": "sources/telorgon",
    "bootloader": "sources/telorgon-bootloader",
    "file-explorer": "sources/telorgon-file-explorer",
    "portal-picker": "sources/telorgon-portal-picker",
    "settings": "sources/telorgon-settings-app",
    "shell": "sources/test-shell",
}


class SetupError(Exception):
    pass


def is_wsl():
    return sys.platform == "linux" and "microsoft" in platform.release().lower()


def refresh_option(value):
    if value in {"auto", "skip", "check"}:
        return value
    if value.isdecimal() and 2 <= int(value) <= 1000:
        return int(value)
    raise argparse.ArgumentTypeError("use auto, skip, check, or an integer refresh rate from 2 to 1000 Hz")


def windows_wslg_info():
    """Query active modes, never the monitor's advertised maximum, through WSL interop."""
    if not shutil.which("powershell.exe") or not shutil.which("wslpath"):
        raise SetupError("WSLg setup needs Windows interop (powershell.exe and wslpath).")
    script = Path(__file__).with_name("scripts") / "wslg-display-info.ps1"
    encoded = base64.b64encode(script.read_text().encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True, text=True, encoding="utf-8-sig", timeout=30,
        )
        if result.returncode:
            raise SetupError("Cannot query Windows displays; check Windows interop or use --wslg-refresh-rate skip.")
        info = json.loads(result.stdout)
        if not isinstance(info["config_path"], str) or not isinstance(info["displays"], list):
            raise ValueError("Invalid Windows response")
        for display in info["displays"]:
            if (not isinstance(display, dict) or not isinstance(display.get("name"), str)
                    or any(not isinstance(display.get(key), int) for key in ("width", "height", "rate"))):
                raise ValueError("Invalid Windows display")
        mapped = run("wslpath", "-u", info["config_path"]).stdout.strip()
        if not mapped or not Path(mapped).is_absolute():
            raise ValueError("Invalid configuration path")
        return Path(mapped), info["displays"]
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        raise SetupError("Cannot read Windows display settings; use --wslg-refresh-rate skip to continue without them.") from error


WSLG_KEY = "WESTON_RDP_MONITOR_REFRESH_RATE"


def wslg_entries(text):
    """Find one unambiguous section/key without rewriting unrelated INI content."""
    section = None
    sections, keys = [], []
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        header = re.fullmatch(r"\s*\[([^\]]+)\]\s*(?:[;#].*)?", line.rstrip("\r\n"))
        if header:
            section = header[1].strip().lower()
            if section == "system-distro-env":
                sections.append(index)
        elif section == "system-distro-env":
            match = re.fullmatch(r"(\s*" + WSLG_KEY + r"\s*=\s*)([^;#\r\n]*)(.*)",
                                 line.rstrip("\r\n"), re.IGNORECASE)
            if match:
                keys.append((index, match))
    if len(sections) > 1 or len(keys) > 1:
        raise SetupError("Duplicate WSLg sections or refresh-rate entries; resolve them before rerunning setup.")
    return lines, sections, keys


def read_wslg_config(path):
    if path.is_symlink():
        raise SetupError("WSLg configuration is a symlink; edit it manually.")
    raw = path.read_bytes() if path.exists() else b""
    encoding = "utf-8"
    for bom, candidate in ((codecs.BOM_UTF8, "utf-8-sig"),
                           (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if raw.startswith(bom):
            encoding = candidate
            break
    try:
        return raw, raw.decode(encoding), encoding
    except UnicodeError as error:
        raise SetupError("Cannot decode .wslgconfig; save it as UTF-8 or UTF-16 before rerunning setup.") from error


def configured_wslg_rate(text):
    _, _, keys = wslg_entries(text)
    if not keys:
        return None
    value = keys[0][1][2].strip()
    if not value.isdecimal() or not 2 <= int(value) <= 1000:
        raise SetupError("Existing WSLg refresh rate is invalid; correct it before rerunning setup.")
    return int(value)


def merge_wslg_rate(text, rate):
    lines, sections, keys = wslg_entries(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    if keys:
        index, match = keys[0]
        ending = lines[index][len(lines[index].rstrip("\r\n")):]
        trailing = match[2][len(match[2].rstrip()):]
        lines[index] = f"{match[1]}{rate}{trailing}{match[3]}{ending}"
    else:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        if sections:
            lines.insert(sections[0] + 1, f"{WSLG_KEY}={rate}{newline}")
        else:
            lines.extend([f"[system-distro-env]{newline}", f"{WSLG_KEY}={rate}{newline}"])
    return "".join(lines)


def write_wslg_rate(path, rate):
    raw, text, encoding = read_wslg_config(path)
    if configured_wslg_rate(text) == rate:
        return None
    updated = merge_wslg_rate(text, rate).encode(encoding)
    # Preserve the original UTF-16 byte order, including its BOM.
    if raw.startswith(codecs.BOM_UTF16_BE):
        updated = codecs.BOM_UTF16_BE + merge_wslg_rate(text, rate).encode("utf-16-be")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        for suffix in [".bak"] + [f".bak.{n}" for n in range(1, 1000)]:
            candidate = path.with_name(path.name + suffix)
            try:
                with candidate.open("xb") as stream:
                    stream.write(raw)
                backup = candidate
                break
            except FileExistsError:
                continue
        if backup is None:
            raise SetupError("Cannot create a new .wslgconfig backup; existing backups were preserved.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".wslgconfig-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return backup


def verify_wslg_rate(rate, log=Path("/mnt/wslg/weston.log")):
    try:
        values = re.findall(r"rdp_monitor_refresh_rate:\s*(\d+)", log.read_text(errors="replace"))
    except OSError:
        values = []
    if values and int(values[-1]) == rate * 1000:
        print(f"Verified: WSLg is configured to present at {rate} Hz (Weston log).")
        return True
    print(f"WSLg has not been verified at {rate} Hz in {log}.")
    print("Save work in every WSL session, then run in Windows PowerShell: wsl --shutdown")
    print("Reopen Ubuntu and rerun this helper with --wslg-refresh-rate check.")
    print("This restarts all WSL distributions. Setup does not shut them down automatically.")
    return False


def configure_wslg(option):
    if option == "skip":
        return
    if not is_wsl():
        if option != "auto":
            raise SetupError("WSLg refresh-rate setup is only available inside WSL.")
        return
    path, displays = windows_wslg_info()
    _, text, _ = read_wslg_config(path)
    current = configured_wslg_rate(text)
    if option == "check":
        if current is None:
            raise SetupError("No WSLg refresh rate is configured. Rerun setup with --wslg-refresh-rate auto.")
        if not verify_wslg_rate(current):
            raise SetupError("WSLg refresh-rate verification did not pass.")
        return
    if option == "auto":
        if not sys.stdin.isatty():
            print("WSLg refresh-rate setup skipped without an interactive terminal; use --wslg-refresh-rate <Hz> to configure it.")
            return
        valid = [d for d in displays if isinstance(d.get("rate"), int) and 2 <= d["rate"] <= 1000]
        if not valid:
            print("No active Windows refresh rate detected; use --wslg-refresh-rate <Hz> or the manual setup guide.")
            return
        print("\nActive Windows displays (WSLg uses one global presentation rate):")
        for index, display in enumerate(valid, 1):
            print(f"  {index}: {display['name']}, {display['width']}x{display['height']}, {display['rate']} Hz"
                  + (" (primary)" if display.get("primary") else ""))
        if current is not None:
            print(f"Existing WSLg setting: {current} Hz. Enter keeps this setting.")
        else:
            print("Select the display where you will use QEMU. Enter skips this step.")
        while True:
            answer = input("Display number, or Enter to keep/skip: ").strip()
            if not answer:
                if current is not None:
                    verify_wslg_rate(current)
                return
            if answer.isdecimal() and 1 <= int(answer) <= len(valid):
                option = valid[int(answer) - 1]["rate"]
                break
            print("Choose a listed display number, or press Enter.")
    backup = write_wslg_rate(path, option)
    print(f"WSLg presentation rate: {option} Hz in {path}.")
    if backup:
        print(f"Original configuration saved to {backup}.")
    verify_wslg_rate(option)


def run(*args, cwd=None, check=True, interactive=False):
    result = subprocess.run(
        [str(arg) for arg in args], cwd=cwd, text=True,
        capture_output=not interactive,
    )
    if check and result.returncode:
        # Don't print arbitrary command output, which can contain credential URLs.
        raise SetupError(f"{args[0]} {args[1]} failed; check access and rerun setup.")
    return result


def git(path, *args, check=True):
    return run("git", "-C", path, *args, check=check)


def repo_name(url):
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        url.strip(),
    )
    return match[1].lower() if match else None


def check_checkout(path, repository):
    root = git(path, "rev-parse", "--show-toplevel", check=False)
    if root.returncode or Path(root.stdout.strip()).resolve() != path.resolve():
        raise SetupError(f"{path} exists but is not the expected repository checkout.")
    origin = git(path, "config", "--get-all", "remote.origin.url", check=False)
    if origin.returncode or [repo_name(u) for u in origin.stdout.splitlines()] != [
        f"{ORG}/{repository}".lower()
    ]:
        raise SetupError(f"{path}: origin must point to {ORG}/{repository}.")


def prepare_checkout(workspace):
    distro = workspace / "distro"
    if not distro.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        print("Cloning distro and its pinned components...", flush=True)
        run("git", "clone", f"https://github.com/{ORG}/distro.git", distro)
    check_checkout(distro, "distro")
    paths = git(distro, "config", "--file", ".gitmodules", "--get-regexp",
                r"^submodule\..*\.path$").stdout.splitlines()
    expected = {f"submodule.{name}.path {path}" for name, path in MODULES.items()}
    if set(paths) != expected:
        raise SetupError("Distro submodules differ from the supported six components.")
    # Validate every URL before initializing any submodule.
    for name in MODULES:
        url = git(distro, "config", "--file", ".gitmodules", "--get",
                  f"submodule.{name}.url").stdout.strip()
        if repo_name(url) != f"{ORG}/{name}".lower():
            raise SetupError(f"Unexpected submodule URL for {name}.")
        cached = git(distro, "config", "--local", "--get-all",
                     f"submodule.{name}.url", check=False)
        if cached.returncode == 0 and any(repo_name(u) != f"{ORG}/{name}".lower()
                                          for u in cached.stdout.splitlines()):
            raise SetupError(f"Unexpected local submodule URL for {name}; left unchanged.")
    checkouts = {"distro": distro}
    for name, relative in MODULES.items():
        path = distro / relative
        if not path.resolve().is_relative_to(distro.resolve()):
            raise SetupError(f"{name}: component path leaves the distro checkout.")
        if not (path / ".git").exists():
            # Only missing checkouts are initialized. Existing feature branches stay put.
            git(distro, "submodule", "update", "--init", "--recursive", "--", relative)
        check_checkout(path, name)
        checkouts[name] = path
    return checkouts


def login():
    if run("gh", "auth", "status", "--hostname", "github.com", check=False).returncode:
        run("gh", "auth", "login", "--hostname", "github.com",
            "--git-protocol", "https", "--web", interactive=True)
    name = run("gh", "api", "--hostname", "github.com", "user",
               "--jq", ".login").stdout.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", name):
        raise SetupError("GitHub did not return a valid account login.")
    return name


def find_fork(repository, owner):
    query = f".[] | select((.owner.login | ascii_downcase) == {json.dumps(owner.lower())}) | .full_name"
    names = run("gh", "api", "--hostname", "github.com",
                f"repos/{ORG}/{repository}/forks?per_page=100", "--paginate",
                "--jq", query).stdout.splitlines()
    if len(names) > 1 or any(
        not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", name)
        or name.split("/")[0].lower() != owner.lower() for name in names
    ):
        raise SetupError(f"Cannot identify your fork of {repository}.")
    return names[0] if names else None


def ensure_fork(repository, owner):
    existing = find_fork(repository, owner)
    if existing:
        return existing
    print(f"Creating your fork of {repository}...", flush=True)
    run("gh", "repo", "fork", f"https://github.com/{ORG}/{repository}",
        "--clone=false", "--remote=false")
    # GitHub creates forks asynchronously; a later rerun also reuses a completed fork.
    for attempt in range(15):
        found = find_fork(repository, owner)
        if found:
            return found
        if attempt < 14:
            time.sleep(2)
    raise SetupError(f"GitHub is still creating the {repository} fork. Rerun setup shortly.")


def connect_fork(path, full_name):
    urls = git(path, "config", "--get-all", "remote.fork.url", check=False)
    pushes = git(path, "config", "--get-all", "remote.fork.pushurl", check=False)
    for result in (urls, pushes):
        if result.returncode == 0 and any(repo_name(u) != full_name.lower()
                                          for u in result.stdout.splitlines()):
            raise SetupError(f"{path}: existing fork remote points elsewhere; left unchanged.")
    if urls.returncode:
        git(path, "remote", "add", "fork", f"https://github.com/{full_name}.git")
    git(path, "config", "--local", "remote.pushDefault", "fork")
    git(path, "config", "--local", "push.default", "current")
    print(f"{path.name}: origin = organization; fork = {full_name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path,
                        default=Path(__file__).resolve().parent.parent,
                        help="workfolder containing distro (default: parent of this .github checkout)")
    parser.add_argument("--wslg-refresh-rate", type=refresh_option, default="auto", metavar="auto|skip|check|Hz",
                        help="offer Windows display selection in WSL (default: auto), skip it, verify after restart, or set Hz")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SetupError("Install Python 3.11 or newer.")
    if args.wslg_refresh_rate == "check":
        try:
            configure_wslg("check")
        except OSError as error:
            raise SetupError(f"Cannot read WSLg configuration: {error}") from error
        return
    for command in ("git", "gh"):
        if not shutil.which(command):
            raise SetupError(f"Install {command} first (GitHub CLI is the gh package).")
    checkouts = prepare_checkout(args.workspace.expanduser().resolve())
    owner = login()
    print(f"Setting up personal forks for {owner}: distro and six components.", flush=True)
    # All forks must be identified before changing any local remote.
    forks = {name: ensure_fork(name, owner) for name in checkouts}
    run("gh", "auth", "setup-git", "--hostname", "github.com")
    for name, path in checkouts.items():
        connect_fork(path, forks[name])
    try:
        configure_wslg(args.wslg_refresh_rate)
    except (SetupError, OSError) as error:
        if args.wslg_refresh_rate != "auto":
            raise SetupError(f"WSLg configuration failed: {error}") from error
        print(f"WSLg refresh-rate setup skipped: {error}")
    print(f"\nReady. Open {args.workspace.expanduser().resolve()} in your editor or coding agent.")
    print("Next, verify your environment: "
          "https://github.com/WIPOperatingSystemName/distro/blob/main/docs/setup.md#4-verify-the-environment")
    print("Then build your first VM: "
          "https://github.com/WIPOperatingSystemName/distro/blob/main/docs/build.md#first-build")
    print("For contributions: https://github.com/WIPOperatingSystemName/.github/blob/main/AGENTS.md")


if __name__ == "__main__":
    try:
        main()
    except SetupError as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nSetup interrupted. Rerun to continue.", file=sys.stderr)
        sys.exit(1)
