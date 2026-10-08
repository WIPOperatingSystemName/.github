#!/usr/bin/env python3
"""Prepare one contributor workspace with canonical checkouts and personal forks."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
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
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SetupError("Install Python 3.11 or newer.")
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
    print(f"\nReady. Open {args.workspace.expanduser().resolve()} in your editor or coding agent.")
    print("Create a feature branch in the repo you change, then push with: git push -u fork HEAD")
    print("Open its PR against the corresponding organization's repository, base branch main.")


if __name__ == "__main__":
    try:
        main()
    except SetupError as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nSetup interrupted. Rerun to continue.", file=sys.stderr)
        sys.exit(1)
