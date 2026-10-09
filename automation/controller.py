"""Create, qualify and merge exact bundles under the configured merge policy."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CONTEXT, CONTROL, DISTRO, MODULES, ORG, WORKFLOW, Failure,
                    GitHub, app_client, redact, required, trusted_dispatch)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise Failure("Expected an immutable full Git commit ID")
    return value


def number(value):
    if not re.fullmatch(r"[1-9][0-9]{0,18}", str(value)) or int(value) > 2**63 - 1:
        raise Failure("Expected a positive PR/run identifier")
    return int(value)


def parse_refs(value):
    refs = []
    for item in value.split(","):
        match = re.fullmatch(r"\s*([a-z][a-z-]*)#([1-9][0-9]{0,9})\s*", item)
        if not match or match[1] not in {*MODULES, "distro"}:
            raise Failure("Use comma-separated distro repository PRs, e.g. telorgon#42,settings#9")
        refs.append((match[1], int(match[2])))
    if not 1 <= len(refs) <= 7 or len({r for r, _ in refs}) != len(refs):
        raise Failure("A bundle accepts one PR per repository, up to seven repositories")
    return refs


def branch_head(github, repo):
    return sha(github.repo(repo, "/git/ref/heads/main")["object"]["sha"])


def commit(github, repo, revision):
    return github.repo(repo, f"/git/commits/{sha(revision)}")


def snapshot(github, short, pr_number):
    repo = f"{ORG}/{short}"
    pr = github.repo(repo, f"/pulls/{number(pr_number)}")
    if (pr["state"] != "open" or pr["draft"] or pr["base"]["ref"] != "main"
            or pr["base"]["repo"]["full_name"] != repo):
        raise Failure("Bundle PRs must be open, ready and target the allowed main branch")
    head, base = sha(pr["head"]["sha"]), branch_head(github, repo)
    comparison = github.repo(repo, f"/compare/{base}...{head}")
    if comparison["status"] not in {"ahead", "identical"} or comparison["behind_by"]:
        raise Failure(f"Update {short}#{pr_number} from main before preparing a bundle")
    return {"repository": short, "number": number(pr_number), "base": base,
            "head": head, "tree": sha(commit(github, repo, head)["tree"]["sha"])}


def validate_bundle(bundle):
    keys = {"schema", "distro_base", "pins", "prs", "run_id", "controller_sha", "digest"}
    if not isinstance(bundle, dict) or set(bundle) != keys or bundle["schema"] != 1:
        raise Failure("Unsupported integration manifest")
    body = {key: value for key, value in bundle.items() if key != "digest"}
    if bundle["digest"] != digest(body):
        raise Failure("Integration manifest digest differs")
    sha(bundle["distro_base"])
    sha(bundle["controller_sha"])
    number(bundle["run_id"])
    if not isinstance(bundle["pins"], dict) or set(bundle["pins"]) != set(MODULES):
        raise Failure("Integration requires all six source pins")
    for pin in bundle["pins"].values():
        sha(pin)
    if not isinstance(bundle["prs"], list) or not 1 <= len(bundle["prs"]) <= 7:
        raise Failure("Invalid integration PR list")
    seen = set()
    for pr in bundle["prs"]:
        if not isinstance(pr, dict) or set(pr) != {"repository", "number", "base", "head", "tree"}:
            raise Failure("Invalid component PR record")
        short = pr["repository"]
        if short not in {*MODULES, "distro"} or short in seen:
            raise Failure("Unknown or duplicate component repository")
        seen.add(short)
        number(pr["number"])
        for key in ("base", "head", "tree"):
            sha(pr[key])
        if short == "distro":
            if pr["base"] != bundle["distro_base"]:
                raise Failure("Distro source PR base differs from the bundle base")
        elif pr["head"] != bundle["pins"][short]:
            raise Failure("Component commit and distro pin differ")
    return bundle


def read_bundle(github, hub, *, audit=True):
    if (hub["draft"] or hub["base"]["ref"] != "main"
            or hub["base"]["repo"]["full_name"] != DISTRO
            or hub["head"]["repo"]["full_name"] != DISTRO
            or not re.fullmatch(r"integration/[1-9][0-9]{0,18}", hub["head"]["ref"])):
        raise Failure("Expected a controller-created distro integration PR")
    head = sha(hub["head"]["sha"])
    run = hub["head"]["ref"].split("/")[1]
    path = f".integration/bundles/{run}.json"
    document = github.repo(DISTRO, f"/contents/{path}?ref={head}")
    if document.get("encoding") != "base64" or document.get("type") != "file":
        raise Failure("Expected an ordinary integration manifest blob")
    try:
        bundle = validate_bundle(json.loads(base64.b64decode(document["content"])))
    except (ValueError, TypeError):
        raise Failure("Invalid integration manifest encoding") from None
    if bundle["run_id"] != number(run):
        raise Failure("Manifest run and integration branch differ")
    if audit:
        audit_hub(github, head, bundle)
    return bundle


def audit_hub(github, head, bundle):
    """The generated commit may change only reviewed pins and its exact receipt."""
    source = next((pr for pr in bundle["prs"] if pr["repository"] == "distro"), None)
    parent = source["head"] if source else bundle["distro_base"]
    if [item["sha"] for item in commit(github, DISTRO, head)["parents"]] != [parent]:
        raise Failure("Integration commit has an unexpected parent")
    if _initial_pins(github, head) != bundle["pins"]:
        raise Failure("Integration source pins differ from the reviewed bundle")
    comparison = github.repo(DISTRO, f"/compare/{parent}...{head}")
    files = comparison.get("files")
    if (comparison.get("status") != "ahead" or comparison.get("behind_by") != 0
            or comparison.get("total_commits") != 1 or not isinstance(files, list)
            or not 1 <= len(files) <= 7):
        raise Failure("Integration commit comparison is incomplete")
    path = f".integration/bundles/{bundle['run_id']}.json"
    content = (json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode()
    blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
    expected = {MODULES[r]: pin for r, pin in bundle["pins"].items()}
    expected[path] = blob
    found = set()
    for file in files:
        filename = file.get("filename")
        if (filename not in expected or filename in found
                or file.get("sha") != expected[filename]
                or file.get("status") != ("added" if filename == path else "modified")):
            raise Failure("Integration commit contains unreviewed changes")
        found.add(filename)
    if path not in found:
        raise Failure("Integration commit has no immutable manifest addition")


def load_bundle(github, hub_number, expected_head=None):
    hub = github.repo(DISTRO, f"/pulls/{number(hub_number)}")
    if hub["state"] != "open":
        raise Failure("Expected an open controller-created distro integration PR")
    if expected_head is not None and sha(hub["head"]["sha"]) != sha(expected_head):
        raise Failure("Integration PR changed; prepare and qualify it again")
    return hub, read_bundle(github, hub)


def discover(github, controller_sha):
    """Select ready changes once per source/base/controller state, oldest first."""
    controller_sha = sha(controller_sha)
    distro_base = branch_head(github, DISTRO)
    attempted = set()
    # Both open and closed App-owned receipts count. A failed or denied revision
    # is retried by a deliberate manual prepare, or after its inputs change.
    for page in range(1, 11):
        receipts = github.repo(DISTRO, f"/pulls?state=all&base=main&sort=created&direction=desc&per_page=100&page={page}")
        for hub in receipts:
            if (hub.get("user", {}).get("login") != github.bot_login
                    or hub["head"]["repo"] is None
                    or hub["head"]["repo"]["full_name"] != DISTRO
                    or not re.fullmatch(r"integration/[1-9][0-9]{0,18}", hub["head"]["ref"])):
                continue
            bundle = read_bundle(github, hub, audit=False)
            if bundle["controller_sha"] == controller_sha and bundle["distro_base"] == distro_base:
                audit_hub(github, sha(hub["head"]["sha"]), bundle)
                attempted.update((pr["repository"], pr["number"], pr["base"], pr["head"])
                                 for pr in bundle["prs"])
        if len(receipts) < 100:
            break
    else:
        raise Failure("Automatic receipt audit exceeds 1,000 PRs; use manual prepare")
    refs = []
    for short in [*MODULES, "distro"]:
        repo = f"{ORG}/{short}"
        pulls = github.repo(repo, "/pulls?state=open&base=main&sort=created&direction=asc&per_page=100")
        if len(pulls) >= 100:
            raise Failure("Automatic discovery exceeds 100 open PRs per repository; use manual prepare")
        for pr in pulls:
            if (pr["draft"] or (short == "distro" and pr["head"]["repo"] is not None
                    and pr["head"]["repo"]["full_name"] == DISTRO
                    and pr["head"]["ref"].startswith("integration/"))):
                continue
            try:
                candidate = snapshot(github, short, pr["number"])
            except Failure:
                # Contributors must update behind branches before qualification.
                continue
            identity = (short, candidate["number"], candidate["base"], candidate["head"])
            if identity not in attempted:
                refs.append(f"{short}#{candidate['number']}")
                break
    return ",".join(refs)


def candidate_state(github, pr, *, allow_merged=False):
    repo = f"{ORG}/{pr['repository']}"
    live = github.repo(repo, f"/pulls/{pr['number']}")
    if (sha(live["head"]["sha"]) != pr["head"] or live["base"]["ref"] != "main"
            or live["base"]["repo"]["full_name"] != repo):
        raise Failure("Component PR changed; a fresh bundle and approval are required")
    current = branch_head(github, repo)
    if live.get("merged"):
        if not allow_merged:
            raise Failure("Component merged before qualification; prepare a fresh bundle")
        merged = sha(live["merge_commit_sha"])
        result = commit(github, repo, merged)
        parents = [p["sha"] for p in result["parents"]]
        if (current != merged or result["tree"]["sha"] != pr["tree"]
                or parents != [pr["base"], pr["head"]]):
            raise Failure("A previously merged component no longer matches the tested bundle")
        return "merged"
    if live["state"] != "open" or live["draft"] or current != pr["base"]:
        raise Failure("Component/base changed; prepare and qualify a fresh bundle")
    return "open"


def fresh(github, hub, bundle, *, allow_merged=False):
    if branch_head(github, DISTRO) != bundle["distro_base"]:
        raise Failure("Distro main moved; prepare and qualify a fresh bundle")
    if hub["base"]["repo"]["full_name"] != DISTRO:
        raise Failure("Unexpected integration target")
    states = {pr["repository"]: candidate_state(github, pr, allow_merged=allow_merged)
              for pr in bundle["prs"]}
    for short, pin in bundle["pins"].items():
        if short in states:
            continue
        repo = f"{ORG}/{short}"
        main = branch_head(github, repo)
        compared = github.repo(repo, f"/compare/{pin}...{main}")
        if compared["status"] not in {"ahead", "identical"} or compared["behind_by"]:
            raise Failure("Unselected source pins must already be ancestors of component main")
    return states


def _initial_pins(github, parent):
    tree_sha = sha(commit(github, DISTRO, parent)["tree"]["sha"])
    tree = github.repo(DISTRO, f"/git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated"):
        raise Failure("Distro tree is too large for a complete source-pin audit")
    paths = {item["path"]: item for item in tree["tree"]}
    pins = {}
    for short, path in MODULES.items():
        item = paths.get(path, {})
        if item.get("type") != "commit" or item.get("mode") != "160000":
            raise Failure("Publish the distro baseline with all six submodules first")
        pins[short] = sha(item["sha"])
    return pins


def prepare(github, references, run_id, controller_sha):
    base = branch_head(github, DISTRO)
    prs = [snapshot(github, repo, n) for repo, n in parse_refs(references)]
    source = next((p for p in prs if p["repository"] == "distro"), None)
    parent = source["head"] if source else base
    if source and source["base"] != base:
        raise Failure("Distro base changed during preparation")
    pins = _initial_pins(github, parent)
    for pr in prs:
        if pr["repository"] in MODULES:
            pins[pr["repository"]] = pr["head"]
    body = {"schema": 1, "distro_base": base, "pins": pins, "prs": prs,
            "run_id": number(run_id), "controller_sha": sha(controller_sha)}
    bundle = {**body, "digest": digest(body)}
    validate_bundle(bundle)
    for pr in prs:
        candidate_state(github, pr)
    if branch_head(github, DISTRO) != base:
        raise Failure("Distro base changed during preparation")
    blob = github.repo(DISTRO, "/git/blobs", payload={
        "content": json.dumps(bundle, indent=2, sort_keys=True) + "\n", "encoding": "utf-8"})
    entries = [{"path": MODULES[r], "mode": "160000", "type": "commit", "sha": pin}
               for r, pin in pins.items()]
    entries.append({"path": f".integration/bundles/{run_id}.json", "mode": "100644",
                    "type": "blob", "sha": blob["sha"]})
    tree = github.repo(DISTRO, "/git/trees", payload={
        "base_tree": commit(github, DISTRO, parent)["tree"]["sha"], "tree": entries})
    created = github.repo(DISTRO, "/git/commits", payload={
        "message": f"Integrate reviewed source bundle {run_id}",
        "tree": tree["sha"], "parents": [parent]})
    branch = f"integration/{run_id}"
    github.repo(DISTRO, "/git/refs", payload={"ref": f"refs/heads/{branch}", "sha": created["sha"]})
    lines = [f"Coordinate these component changes as one tested distro version:"]
    lines += [f"- {ORG}/{p['repository']}#{p['number']} at `{p['head']}`" for p in prs]
    lines += ["", f"Manifest digest: `{bundle['digest']}`.", "",
              f"Qualification: https://github.com/{CONTROL}/actions/runs/{run_id}", "",
              "Qualification and an accepted security review are required for these exact commits. "
              "Automatic mode merges after the trusted checks pass; manual mode also requires "
              "maintainer approval and a merge dispatch."]
    hub = github.repo(DISTRO, "/pulls", payload={"title": f"Integration bundle {run_id}",
                     "head": branch, "base": "main", "body": "\n".join(lines)})
    qualification_status(github, DISTRO, created["sha"], bundle, "pending")
    for pr in prs:
        if pr["repository"] != "distro":
            qualification_status(github, f"{ORG}/{pr['repository']}", pr["head"], bundle, "pending")
    return number(hub["number"]), sha(created["sha"])


def qualification_status(github, repo, head, bundle, state):
    github.repo(repo, f"/statuses/{sha(head)}", payload={
        "state": state, "context": CONTEXT,
        "description": f"Bundle {bundle['digest'][:16]}; run {bundle['run_id']}",
        "target_url": f"https://github.com/{CONTROL}/actions/runs/{bundle['run_id']}",
    })


def _jobs(github, bundle, *, completed):
    run = github.repo(CONTROL, f"/actions/runs/{bundle['run_id']}")
    if (run["head_sha"] != bundle["controller_sha"] or run["path"] != WORKFLOW
            or run["head_branch"] != "main"
            or run["event"] not in {"workflow_dispatch", "schedule"}
            or run["actor"]["login"].casefold() != required("MAINTAINER_LOGIN").casefold()
            or (completed and (run["status"] != "completed" or run["conclusion"] != "success"))):
        raise Failure("Qualification must come from the trusted maintainer workflow and succeed")
    jobs = github.repo(CONTROL, f"/actions/runs/{bundle['run_id']}/jobs?per_page=100")
    if jobs["total_count"] > 100:
        raise Failure("Qualification job audit exceeds its size limit")
    return {job["name"]: job["conclusion"] for job in jobs["jobs"]}


def _run(github, bundle, *, completed, recorded=False):
    found = _jobs(github, bundle, completed=completed)
    required_jobs = {"Qualify candidate", "OpenAI review", "OpenAI security gate"}
    if recorded:
        required_jobs.add("Record review and checks")
    if any(found.get(name) != "success" for name in required_jobs):
        raise Failure("Qualification, security acceptance and the required review jobs must succeed")


def deny(github, readonly, hub_number, expected_head):
    hub, bundle = load_bundle(github, hub_number, expected_head)
    if (bundle["controller_sha"] != sha(required("GITHUB_SHA"))
            or str(bundle["run_id"]) != required("GITHUB_RUN_ID")
            or os.environ.get("GITHUB_JOB") != "deny"):
        raise Failure("Denial must come from this candidate's trusted failure-recording job")
    if _jobs(readonly, bundle, completed=False).get("OpenAI security gate") != "failure":
        raise Failure("No failed security job exists for this candidate")
    fresh(github, hub, bundle)
    qualification_status(github, DISTRO, expected_head, bundle, "failure")
    for pr in bundle["prs"]:
        if pr["repository"] != "distro":
            qualification_status(github, f"{ORG}/{pr['repository']}", pr["head"], bundle, "failure")


def record(github, readonly, hub_number, expected_head, report, security_report):
    from review import validate_review
    from security_review import validate_report
    hub, bundle = load_bundle(github, hub_number, expected_head)
    if bundle["controller_sha"] != sha(required("GITHUB_SHA")):
        raise Failure("Controller changed; prepare a fresh bundle")
    fresh(github, hub, bundle)
    _run(readonly, bundle, completed=False)
    if report["bundle_digest"] != bundle["digest"] or report["integration_head"] != expected_head:
        raise Failure("AI report belongs to another candidate")
    validate_review(report["review"], [p["repository"] for p in bundle["prs"]])
    validate_report(security_report, bundle, expected_head)
    text = redact(json.dumps({"advisory": report, "security": security_report}, indent=2, ensure_ascii=True))
    # A longer fence keeps model-generated backticks inside the data block.
    fence = "`" * max(3, 1 + max((len(m[0]) for m in re.finditer(r"`+", text)), default=0))
    github.repo(DISTRO, f"/issues/{hub['number']}/comments", payload={
        "body": "Deterministic qualification passed and the security gate accepted these exact commits. "
                "The general code review is advisory; the configured merge policy controls submission. "
                f"\n\n{fence}json\n{text}\n{fence}"})
    qualification_status(github, DISTRO, expected_head, bundle, "success")
    for pr in bundle["prs"]:
        if pr["repository"] != "distro":
            qualification_status(github, f"{ORG}/{pr['repository']}", pr["head"], bundle, "success")


def approved(github, hub):
    reviews = github.repo(DISTRO, f"/pulls/{hub['number']}/reviews?per_page=100")
    if len(reviews) >= 100:
        raise Failure("Too many reviews to audit completely")
    owner = required("MAINTAINER_LOGIN").casefold()
    reviews = [r for r in reviews if r["user"]["login"].casefold() == owner
               and r["state"] != "COMMENTED"]
    latest = max(reviews, key=lambda r: r["id"], default=None)
    if not latest or latest["state"] != "APPROVED" or latest["commit_id"] != hub["head"]["sha"]:
        raise Failure("The configured maintainer must approve the current integration commit")


def protection(github, repo, *, hub=False, automatic=False):
    settings = github.repo(repo)
    policy = github.repo(repo, "/branches/main/protection")
    checks = policy.get("required_status_checks") or {}
    reviews = policy.get("required_pull_request_reviews")
    restrictions = policy.get("restrictions") or {}
    app_ids = {app["id"] for app in restrictions.get("apps", [])}
    trusted_check = {"context": CONTEXT, "app_id": github.app_id} in checks.get("checks", [])
    bypass = (reviews or {}).get("bypass_pull_request_allowances") or {}
    if (settings["default_branch"] != "main" or not settings.get("allow_merge_commit")
            or not policy.get("enforce_admins", {}).get("enabled")
            or policy.get("allow_force_pushes", {}).get("enabled")
            or policy.get("allow_deletions", {}).get("enabled")
            or reviews is None or not trusted_check or app_ids != {github.app_id}
            or restrictions.get("users") or restrictions.get("teams")
            or any(bypass.get(kind) for kind in ("users", "teams", "apps"))):
        raise Failure("Configure the documented main branch protections before merging")
    if automatic and (reviews.get("required_approving_review_count", 0) != 0
            or reviews.get("require_code_owner_reviews") or reviews.get("require_last_push_approval")):
        raise Failure("Automatic mode requires zero human approvals; trusted checks still apply")
    if hub and not automatic and (reviews.get("required_approving_review_count", 0) < 1
                or not reviews.get("dismiss_stale_reviews")):
        raise Failure("Distro main requires approval with stale approvals dismissed")


def checked(github, repo, head, bundle):
    statuses = github.repo(repo, f"/commits/{sha(head)}/statuses?per_page=100")
    if len(statuses) >= 100:
        raise Failure("Too many statuses to audit completely")
    latest = next((s for s in statuses if s["context"] == CONTEXT), None)
    expected_url = f"https://github.com/{CONTROL}/actions/runs/{bundle['run_id']}"
    if (not latest or latest["state"] != "success" or latest["target_url"] != expected_url
            or latest["creator"]["login"] != github.bot_login
            or latest["description"] != f"Bundle {bundle['digest'][:16]}; run {bundle['run_id']}"):
        raise Failure("A successful trusted qualification status is required for this exact bundle")


def merge(github, readonly, hub_number, *, automatic=False):
    hub, bundle = load_bundle(github, hub_number)
    head = sha(hub["head"]["sha"])
    if bundle["controller_sha"] != sha(required("GITHUB_SHA")):
        raise Failure("Controller changed; prepare a fresh bundle")
    if automatic and (os.environ.get("AUTO_MERGE_ENABLED") != "true"
                      or os.environ.get("GITHUB_RUN_ID") != str(bundle["run_id"])
                      or os.environ.get("GITHUB_JOB") != "auto-merge"):
        raise Failure("Automatic merging only runs after checks in its enabled trusted prepare run")
    _run(readonly, bundle, completed=not automatic, recorded=True)
    if not automatic:
        approved(github, hub)
    protection(github, DISTRO, hub=True, automatic=automatic)
    checked(github, DISTRO, head, bundle)
    states = fresh(github, hub, bundle, allow_merged=True)
    for pr in bundle["prs"]:
        if pr["repository"] != "distro":
            protection(github, f"{ORG}/{pr['repository']}", automatic=automatic)
            checked(github, f"{ORG}/{pr['repository']}", pr["head"], bundle)
    # Only this controller may update protected main branches. The workflow serializes merge jobs.
    order = {repo: index for index, repo in enumerate(MODULES)}
    for pr in sorted(bundle["prs"], key=lambda p: order.get(p["repository"], 99)):
        short = pr["repository"]
        if short == "distro" or states[short] == "merged":
            continue
        current_hub, _ = load_bundle(github, hub_number, head)
        if not automatic:
            approved(github, current_hub)
        fresh(github, current_hub, bundle, allow_merged=True)
        protection(github, f"{ORG}/{short}", automatic=automatic)
        checked(github, f"{ORG}/{short}", pr["head"], bundle)
        result = github.repo(f"{ORG}/{short}", f"/pulls/{pr['number']}/merge", method="PUT",
                             payload={"sha": pr["head"], "merge_method": "merge"})
        if not result.get("merged"):
            raise Failure("Component merge refused; distro pins were not promoted")
        candidate_state(github, pr, allow_merged=True)
    current_hub, _ = load_bundle(github, hub_number, head)
    if not automatic:
        approved(github, current_hub)
    fresh(github, current_hub, bundle, allow_merged=True)
    protection(github, DISTRO, hub=True, automatic=automatic)
    checked(github, DISTRO, head, bundle)
    result = github.repo(DISTRO, f"/pulls/{hub_number}/merge", method="PUT",
                         payload={"sha": head, "merge_method": "merge"})
    if not result.get("merged"):
        raise Failure("Distro merge refused; component merges may already exist. Retry after inspection")
    merged = sha(result["sha"])
    if commit(github, DISTRO, merged)["tree"]["sha"] != commit(github, DISTRO, head)["tree"]["sha"]:
        raise Failure("Merged distro tree differs from the tested candidate; inspect before releasing")
    return merged


def output(name, value):
    with Path(required("GITHUB_OUTPUT")).open("a") as stream:
        stream.write(f"{name}={value}\n")


def main():
    trusted_dispatch()
    operation = sys.argv[1] if len(sys.argv) == 2 else ""
    if operation == "manifest":
        client = GitHub(os.environ.get("GITHUB_TOKEN") or None)
        hub, bundle = load_bundle(client, required("HUB_PR"), required("HUB_HEAD"))
        fresh(client, hub, bundle)
        Path("bundle.json").write_text(json.dumps(bundle, indent=2) + "\n")
        return
    client = app_client()
    readonly = GitHub(os.environ.get("GITHUB_TOKEN") or None)
    if operation in {"prepare", "prepare-auto"}:
        if operation == "prepare-auto":
            if os.environ.get("AUTO_MERGE_ENABLED") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "schedule":
                raise Failure("Automatic discovery requires an enabled scheduled run")
            references = discover(client, required("GITHUB_SHA"))
            if not references:
                print("No new ready source revisions; no API review or build scheduled")
                return
        else:
            references = required("PR_REFERENCES")
        pr, head = prepare(client, references, required("GITHUB_RUN_ID"), required("GITHUB_SHA"))
        output("hub_pr", pr)
        output("hub_head", head)
        print(f"Prepared https://github.com/{DISTRO}/pull/{pr}")
    elif operation == "deny":
        deny(client, readonly, number(required("HUB_PR")), required("HUB_HEAD"))
        print("Recorded failed security gate; candidate code was not qualified or merged")
    elif operation == "record":
        report = json.loads(Path("ai-review.json").read_text())
        security_report = json.loads(Path("security-review.json").read_text())
        record(client, readonly, number(required("HUB_PR")), required("HUB_HEAD"), report, security_report)
        print("Recorded qualification, security acceptance and advisory AI review")
    elif operation in {"merge", "merge-auto"}:
        result = merge(client, readonly, number(required("HUB_PR")), automatic=operation == "merge-auto")
        print(f"Promoted distro commit {result}")
    else:
        raise Failure("Expected prepare, prepare-auto, manifest, deny, record, merge or merge-auto")


if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        print(redact(str(error)), file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError, TypeError):
        print("Integration data/authentication was invalid; details withheld", file=sys.stderr)
        sys.exit(1)
