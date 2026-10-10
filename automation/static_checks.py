"""Parse immutable source as data; never import, build or execute candidate code."""
from __future__ import annotations

import ast
import configparser
import json
import os
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DISTRO, MODULES, ORG, Failure, GitHub, redact, required, trusted_dispatch
from controller import digest, fresh, load_bundle
from review import encode_input
from security_review import MAX_FILES, MAX_INPUT_BYTES, candidate_data, source

POLICY = "static-checks-v1"
CHECKS = ["immutable_sources", "module_mapping", "python_json_toml_syntax", "recipe_metadata"]


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
                or section["url"] != f"https://github.com/{ORG}/{short}.git"):
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


def parse_changes(data):
    count = 0
    for change in data["changes"]:
        for file in change["files"]:
            count += 1
            content, path = file["after"], file["path"]
            if content is None:
                continue
            try:
                if path.endswith(".py"):
                    ast.parse(content, filename=path)
                elif path.endswith(".json"):
                    json.loads(content)
                elif path.endswith(".toml"):
                    document = tomllib.loads(content)
                    if change["repository"] == "distro" and re.fullmatch(r"packages/[^/]+/package\.toml", path):
                        recipe(document)
            except (SyntaxError, ValueError, RecursionError):
                # Parser exceptions can contain candidate source; don't echo it.
                raise Failure(f"Invalid source syntax in {change['repository']}/{path}") from None
    return count


def validate_report(report, bundle, head):
    keys = {"policy", "bundle_digest", "integration_head", "source_digest", "checks", "files_checked", "build_and_boot"}
    if (not isinstance(report, dict) or set(report) != keys or report["policy"] != POLICY
            or report["bundle_digest"] != bundle["digest"] or report["integration_head"] != head
            or not isinstance(report["source_digest"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", report["source_digest"])
            or report["checks"] != CHECKS or type(report["files_checked"]) is not int
            or not 1 <= report["files_checked"] <= MAX_FILES or report["build_and_boot"] != "not_run"):
        raise Failure("Missing, stale or unsupported static-check receipt")
    return report


def load_checked_data(bundle, head):
    report_path, data_path = Path("static-checks.json"), Path("checked-source.json")
    if (not report_path.is_file() or not data_path.is_file()
            or report_path.stat().st_size > 4096 or data_path.stat().st_size > MAX_INPUT_BYTES):
        raise Failure("Missing or oversized checked-source artifact")
    report = validate_report(json.loads(report_path.read_text()), bundle, head)
    data = json.loads(data_path.read_text())
    if (not isinstance(data, dict) or data.get("bundle_digest") != bundle["digest"]
            or digest(data) != report["source_digest"]):
        raise Failure("Source artifact differs from the checked immutable input")
    return data, report


def main():
    trusted_dispatch()
    github = GitHub(os.environ.get("GITHUB_TOKEN") or None)
    head = required("HUB_HEAD")
    hub, bundle = load_bundle(github, required("HUB_PR"), head)
    fresh(github, hub, bundle)
    data = candidate_data(github, bundle)
    module_mapping(source(github, DISTRO, ".gitmodules", head))
    count = parse_changes(data)
    current, _ = load_bundle(github, required("HUB_PR"), head)
    fresh(github, current, bundle)
    report = {"policy": POLICY, "bundle_digest": bundle["digest"], "integration_head": head,
              "source_digest": digest(data), "checks": CHECKS, "files_checked": count,
              "build_and_boot": "not_run"}
    validate_report(report, bundle, head)
    Path("checked-source.json").write_text(encode_input(data))
    Path("static-checks.json").write_text(json.dumps(report, indent=2) + "\n")
    with Path(required("GITHUB_STEP_SUMMARY")).open("a") as stream:
        stream.write(f"Parsed and checked {count} changed files without executing candidate code. "
                     "Build and boot verification were not run; they remain required before release.\n")
    print("Lightweight source checks passed; no candidate code was executed")


if __name__ == "__main__":
    try:
        main()
    except (Failure, KeyError, ValueError, TypeError) as error:
        message = str(error) if isinstance(error, Failure) else "Invalid immutable source-check data"
        print(redact(message), file=sys.stderr)
        sys.exit(1)
