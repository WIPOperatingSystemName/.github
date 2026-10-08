"""Fetch public immutable inputs and run qualification on a disposable Linux worker."""
from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DISTRO, MODULES, ORG, Failure, GitHub, required, trusted_dispatch
from controller import fresh, load_bundle, sha


def git(root, *args):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.check_output([
        "git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
        "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
        "-C", str(root), *args], env=env, text=True).strip()


def checkout(root, short, ref, revision):
    root.mkdir(parents=True)
    git(root, "init", "--quiet", "--initial-branch=main", "--template=")
    git(root, "remote", "add", "origin", f"https://github.com/{ORG}/{short}.git")
    git(root, "fetch", "--depth=1", "origin", ref)
    if git(root, "rev-parse", "FETCH_HEAD") != sha(revision):
        raise Failure("Fetched source changed; prepare a fresh integration bundle")
    git(root, "checkout", "--detach", revision)


def audit_modules(root, bundle):
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.read(root / ".gitmodules")
    expected = {f'submodule "{short}"' for short in MODULES}
    if set(config.sections()) != expected:
        raise Failure("Only the six declared distro submodules are allowed")
    for short, path in MODULES.items():
        section = config[f'submodule "{short}"']
        if (set(section) != {"path", "url"} or section["path"] != path
                or section["url"] != f"https://github.com/{ORG}/{short}.git"):
            raise Failure("Candidate changes the trusted source repository mapping")
        entry = git(root, "ls-tree", "HEAD", "--", path).split()
        if entry[:3] != ["160000", "commit", bundle["pins"][short]]:
            raise Failure("Candidate source pins differ from the integration manifest")


def fetch_candidate(root, bundle, hub_head):
    checkout(root, "distro", f"refs/heads/integration/{bundle['run_id']}", hub_head)
    audit_modules(root, bundle)
    selected = {p["repository"]: p for p in bundle["prs"]}
    for short, path in MODULES.items():
        # Ref names come exclusively from the validated manifest. Never follow candidate URLs.
        ref = f"refs/pull/{selected[short]['number']}/head" if short in selected else bundle["pins"][short]
        target = root / path
        if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
            raise Failure("Submodule mount must be an empty ordinary directory")
        checkout(target, short, ref, bundle["pins"][short])


def resources():
    disk = os.statvfs(".")
    ram = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                   if line.startswith("MemTotal:"))) * 1024
    if disk.f_bavail * disk.f_frsize < 128 * 1024**3 or ram < 16 * 1024**3:
        raise Failure("Provide a disposable worker with 128 GiB free disk and 16 GiB RAM")


def run(root, *args, capture=False):
    result = subprocess.run(["python3", *args], cwd=root, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return json.loads(result.stdout) if capture else None


def qualify(root):
    (root / "out/ci").mkdir(parents=True)
    exported = run(root, "build.py", "source-bundle", "export", capture=True)
    run(root, "build.py", "source-bundle", "import", exported["archive"], "--sha256", exported["sha256"])
    for args in [("validate",), ("fetch", "--bootstrap"), ("bootstrap", "--jobs", "4"),
                 ("native-toolkit", "--fetch", "--jobs", "4"), ("build", "--jobs", "4")]:
        run(root, "build.py", *args)
    run(root, "tools/compose-desktop-sdk.py")
    workspace = json.loads((root / "out/bundles/current.json").read_text())["root"]
    sysroot = json.loads((root / "out/sdk/current.json").read_text())["sysroot"]
    run(root, "build.py", "apps", "prepare", "--source-root", workspace)
    preflight = run(root, "build.py", "apps", "check", "--sysroot", sysroot, capture=True)
    (root / "out/ci/apps-preflight.json").write_text(json.dumps(preflight, indent=2))
    if not preflight.get("ready_to_build"):
        raise Failure("Target desktop inputs are incomplete")
    run(root, "build.py", "apps", "build", "--sysroot", sysroot, "--online", "--jobs", "4")
    run(root, "build.py", "loader", "--source-root", workspace, "--online")
    for tool, args in [("build-desktop-session-probe", []), ("audit-installed-resources", []),
                       ("qualify-desktop", ["--gbm"]), ("qualify-desktop-services", []),
                       ("qualify-network-crypto", [])]:
        run(root, f"tools/{tool}.py", *args)
    run(root, "-m", "unittest", "discover", "-s", "tests", "-v")
    run(root, "build.py", "image")
    run(root, "build.py", "vm", "--output", "out/verification/console", "--timeout", "240")
    for option, image, marker, name, timeout in [
        ("--test-upgrade", "custom-distro-update-test", "CUSTOM_PACKAGE_UPGRADE_OK", "upgrade", "240"),
        ("--test-signed-upgrade", "custom-distro-signed-update-test", "CUSTOM_SIGNED_PACKAGE_UPGRADE_OK", "signed-upgrade", "240"),
    ]:
        run(root, "build.py", "image", option)
        run(root, "build.py", "vm", "--image", f"out/images/{image}.img", "--expect", marker,
            "--output", f"out/verification/{name}", "--timeout", timeout)
    run(root, "build.py", "image", "--profile", "systemd")
    run(root, "build.py", "vm", "--image", "out/images/custom-distro-systemd.img", "--expect",
        "CUSTOM_SYSTEMD_RUNTIME_OK", "--output", "out/verification/systemd", "--timeout", "100")
    run(root, "tools/build-pam-auth-probe.py", "--make-fixture")
    run(root, "build.py", "image", "--profile", "systemd", "--test-pam-auth")
    run(root, "build.py", "vm", "--image", "out/images/custom-distro-pam-auth-test.img", "--expect",
        "CUSTOM_PAM_AUTHENTICATION_OK", "--output", "out/verification/pam-auth", "--timeout", "150")
    run(root, "build.py", "image", "--profile", "desktop")
    run(root, "build.py", "vm", "--image", "out/images/custom-distro-desktop.img", "--expect",
        "CUSTOM_DESKTOP_SESSION_OK", "--desktop-input", "--output", "out/verification/desktop-final",
        "--timeout", "150")
    run(root, "tools/check-wayland-window.py", "--vm-report", "out/verification/desktop-final/result.json",
        "--output", "out/verification/desktop-final/windows.json")


def main():
    trusted_dispatch()
    if any(os.environ.get(name) for name in ("OPENAI_API_KEY", "INTEGRATION_APP_PRIVATE_KEY",
                                           "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "GITHUB_TOKEN")):
        raise Failure("Candidate worker must have no API or merge credentials")
    resources()
    github = GitHub()  # Public inputs need no credentials, including for fork PRs.
    hub, bundle = load_bundle(github, required("HUB_PR"), required("HUB_HEAD"))
    fresh(github, hub, bundle)
    # A fresh worker starts with a fresh directory. Never reuse previous build outputs.
    root = Path("candidate").resolve()
    if root.exists():
        raise Failure("Candidate directory already exists; replace the worker")
    fetch_candidate(root, bundle, required("HUB_HEAD"))
    qualify(root)
    (root / "out/ci/bundle.json").write_text(json.dumps(bundle, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (Failure, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
