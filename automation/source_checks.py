"""Parse committed source as data, without credentials or candidate execution."""
from __future__ import annotations

import argparse
import ast
import configparser
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

MODULES = {
    "telorgon": "sources/telorgon",
    "bootloader": "sources/telorgon-bootloader",
    "shell": "sources/test-shell",
    "file-explorer": "sources/telorgon-file-explorer",
    "settings": "sources/telorgon-settings-app",
    "portal-picker": "sources/telorgon-portal-picker",
}


class Failure(Exception):
    """A diagnostic that does not contain candidate source or parser excerpts."""


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise Failure("Cannot read the committed source or comparison base")
    return result.stdout


def module_mapping(text):
    config = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        config.read_string(text)
    except configparser.Error:
        raise Failure("Invalid .gitmodules syntax") from None
    if config.defaults() or set(config.sections()) != {f'submodule "{short}"' for short in MODULES}:
        raise Failure("Only the six declared distro submodules are allowed")
    for short, path in MODULES.items():
        section = config[f'submodule "{short}"']
        if (set(section) != {"path", "url"} or section["path"] != path
                or section["url"] != f"https://github.com/WIPOperatingSystemName/{short}.git"):
            raise Failure("Candidate changes the trusted source repository mapping")


def recipe(document):
    package, dependencies = document.get("package"), document.get("dependencies")
    if (document.get("schema") != 1 or not isinstance(package, dict)
            or not isinstance(package.get("version"), str) or not package["version"]
            or type(package.get("revision")) is not int or package["revision"] < 1
            or not isinstance(dependencies, dict) or not isinstance(dependencies.get("runtime"), list)
            or any(not isinstance(value, str) or not value for value in dependencies["runtime"])):
        raise Failure("Changed recipe requires a version, positive revision and runtime dependencies")
    sources = document.get("sources", [])
    if not isinstance(sources, list):
        raise Failure("Changed recipe has invalid source pins")
    for item in sources:
        if (not isinstance(item, dict) or not isinstance(item.get("url"), str)
                or not item["url"].startswith("https://")
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))):
            raise Failure("Changed recipe sources require HTTPS URLs and immutable SHA256 pins")


def parse_source(repository, path, content):
    try:
        text = content.decode("utf-8")
        if path.endswith(".py"):
            ast.parse(text, filename=path)
        elif path.endswith(".json"):
            json.loads(text)
        elif path.endswith(".toml"):
            document = tomllib.loads(text)
            if repository == "distro" and re.fullmatch(r"packages/[^/]+/package\.toml", path):
                recipe(document)
    except (SyntaxError, ValueError, RecursionError):
        raise Failure(f"Invalid source syntax in {json.dumps(path, ensure_ascii=True)}") from None


def check(root, repository, base=""):
    if repository not in {".github", "distro", *MODULES}:
        raise Failure("Unknown source repository")
    if base and not re.fullmatch(r"[0-9a-f]{40}", base):
        raise Failure("Comparison base must be a complete commit ID")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    changed = None
    if base and base != "0" * 40:
        changed = set(git(root, "diff", "--name-only", "-z", "--no-renames",
                          "--no-ext-diff", "--no-textconv", "--diff-filter=AMT",
                          base, head, "--").split(b"\0"))
    entries = {}
    for record in git(root, "ls-tree", "-rz", "--full-tree", head).split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            mode, kind, blob = metadata.split()
            entries[path] = (mode, kind, blob)
    if repository == "distro":
        mapping = entries.get(b".gitmodules")
        if not mapping or mapping[0] not in {b"100644", b"100755"}:
            raise Failure("Missing regular .gitmodules file")
        try:
            module_mapping(git(root, "cat-file", "blob", mapping[2].decode()).decode("utf-8"))
        except UnicodeError:
            raise Failure("Invalid .gitmodules encoding") from None
    count = 0
    for raw_path, (mode, kind, blob) in entries.items():
        if changed is not None and raw_path not in changed:
            continue
        if not raw_path.endswith((b".py", b".json", b".toml")):
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise Failure(f"Source must be a regular file: {json.dumps(path, ensure_ascii=True)}")
        parse_source(repository, path, git(root, "cat-file", "blob", blob.decode()))
        count += 1
    return {"revision": head, "files_parsed": count, "build_and_boot": "not_run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base", default="")
    args = parser.parse_args()
    try:
        result = check(args.root, args.repository, args.base)
    except Failure as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
