"""Exercise real authorization logic against a stateful fake GitHub API."""
import base64
import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import controller as c


def revision(n):
    return f"{n:040x}"


def fixture():
    body = {"schema": 1, "distro_base": revision(1), "pins": {r: revision(10 + i) for i, r in enumerate(common.MODULES)},
            "prs": [{"repository": r, "number": i + 1, "base": revision(20 + i),
                     "head": revision(30 + i), "tree": revision(40 + i)}
                    for i, r in enumerate(["telorgon", "settings"])],
            "run_id": 100, "controller_sha": revision(2)}
    for pr in body["prs"]:
        body["pins"][pr["repository"]] = pr["head"]
    return {**body, "digest": c.digest(body)}


class FakeGitHub:
    app_id = 123
    bot_login = "integration-test[bot]"

    def __init__(self):
        self.bundle = fixture()
        self.head = revision(3)
        self.hub = {"number": 99, "state": "open", "draft": False,
                    "base": {"ref": "main", "repo": {"full_name": common.DISTRO}},
                    "head": {"sha": self.head, "ref": "integration/100", "repo": {"full_name": common.DISTRO}}}
        self.main = {common.DISTRO: revision(1), **{f"{common.ORG}/{r}": p for r, p in self.bundle["pins"].items()}}
        self.prs, self.commits = {}, {(common.DISTRO, self.head): {"tree": {"sha": revision(4)}, "parents": []}}
        for pr in self.bundle["prs"]:
            repo = f"{common.ORG}/{pr['repository']}"
            self.main[repo] = pr["base"]
            self.prs[repo] = {"state": "open", "draft": False, "merged": False,
                              "head": {"sha": pr["head"]}, "base": {"ref": "main", "repo": {"full_name": repo}}}
            self.commits[repo, pr["head"]] = {"tree": {"sha": pr["tree"]}, "parents": []}
        self.reviews = [{"id": 1, "user": {"login": "owner"}, "state": "APPROVED", "commit_id": self.head}]
        self.policy = {"required_status_checks": {"checks": [{"context": common.CONTEXT, "app_id": self.app_id}]},
                       "required_pull_request_reviews": {"required_approving_review_count": 1, "dismiss_stale_reviews": True},
                       "enforce_admins": {"enabled": True}, "allow_force_pushes": {"enabled": False},
                       "allow_deletions": {"enabled": False},
                       "restrictions": {"apps": [{"id": self.app_id}], "users": [], "teams": []}}
        self.status = {"context": common.CONTEXT, "state": "success", "creator": {"login": self.bot_login},
                       "target_url": f"https://github.com/{common.CONTROL}/actions/runs/100",
                       "description": f"Bundle {self.bundle['digest'][:16]}; run 100"}
        self.run = {"head_sha": revision(2), "head_branch": "main", "path": common.WORKFLOW,
                    "event": "workflow_dispatch", "actor": {"login": "owner"}, "status": "completed", "conclusion": "success"}
        self.jobs = {"total_count": 2, "jobs": [{"name": "Qualify candidate", "conclusion": "success"},
                                              {"name": "OpenAI review", "conclusion": "success"}]}
        self.merges, self.fail_repo, self.bad_tree = [], None, False

    def repo(self, repo, suffix="", **kwargs):
        if suffix == "/pulls/99":
            return copy.deepcopy(self.hub)
        if suffix.startswith("/contents/"):
            return {"type": "file", "encoding": "base64", "content": base64.b64encode(json.dumps(self.bundle).encode()).decode()}
        if suffix == "/git/ref/heads/main":
            return {"object": {"sha": self.main[repo]}}
        if suffix.startswith("/compare/"):
            return {"status": "ahead", "behind_by": 0}
        if suffix.startswith("/git/commits/"):
            return self.commits[repo, suffix.rsplit("/", 1)[1]]
        if suffix == "/pulls/99/reviews?per_page=100":
            return self.reviews
        if suffix.endswith("/merge"):
            if repo == self.fail_repo:
                raise common.Failure("Simulated merge failure")
            payload = kwargs["payload"]
            self.merges.append((repo, payload))
            merged = revision(200 + len(self.merges))
            tree = revision(999) if self.bad_tree else self.commits[repo, payload["sha"]]["tree"]["sha"]
            self.commits[repo, merged] = {"tree": {"sha": tree},
                                         "parents": [{"sha": self.main[repo]}, {"sha": payload["sha"]}]}
            self.main[repo] = merged
            if repo != common.DISTRO:
                self.prs[repo].update(merged=True, merge_commit_sha=merged, state="closed")
            return {"merged": True, "sha": merged}
        if suffix.startswith("/pulls/"):
            return self.prs[repo]
        if suffix == "/branches/main/protection":
            return copy.deepcopy(self.policy)
        if suffix.startswith("/commits/") and "/statuses" in suffix:
            return [self.status]
        if suffix == "/actions/runs/100":
            return self.run
        if suffix == "/actions/runs/100/jobs?per_page=100":
            return self.jobs
        if suffix == "":
            return {"default_branch": "main", "allow_merge_commit": True}
        raise AssertionError((repo, suffix, kwargs))


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MAINTAINER_LOGIN": "owner", "GITHUB_SHA": revision(2)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = FakeGitHub()

    def merge(self):
        return c.merge(self.api, self.api, 99)

    def refused(self):
        with self.assertRaises(common.Failure):
            self.merge()
        self.assertEqual(self.api.merges, [])

    def test_merges_components_before_distro_with_exact_sha(self):
        self.assertEqual(self.merge(), revision(203))
        self.assertEqual([repo for repo, _ in self.api.merges],
                         [f"{common.ORG}/telorgon", f"{common.ORG}/settings", common.DISTRO])
        self.assertEqual([p for _, p in self.api.merges],
                         [{"sha": revision(n), "merge_method": "merge"} for n in [30, 31, 3]])

    def test_missing_approval(self):
        self.api.reviews = []
        self.refused()

    def test_other_contributor_cannot_approve(self):
        self.api.reviews[0]["user"]["login"] = "contributor"
        self.refused()

    def test_approval_of_old_head_is_rejected(self):
        self.api.reviews[0]["commit_id"] = revision(999)
        self.refused()

    def test_latest_changes_requested_overrides_approval(self):
        self.api.reviews.append({**self.api.reviews[0], "id": 2, "state": "CHANGES_REQUESTED"})
        self.refused()

    def test_comment_does_not_cancel_approval(self):
        self.api.reviews.append({**self.api.reviews[0], "id": 2, "state": "COMMENTED"})
        self.merge()

    def test_changed_source_head(self):
        self.api.prs[f"{common.ORG}/settings"]["head"]["sha"] = revision(999)
        self.refused()

    def test_changed_source_base(self):
        self.api.main[f"{common.ORG}/settings"] = revision(999)
        self.refused()

    def test_changed_distro_base(self):
        self.api.main[common.DISTRO] = revision(999)
        self.refused()

    def test_changed_controller(self):
        os.environ["GITHUB_SHA"] = revision(999)
        self.refused()

    def test_failed_or_untrusted_run(self):
        for field, value in [("conclusion", "failure"), ("event", "pull_request"), ("head_branch", "feature"),
                             ("head_sha", revision(999)), ("path", "other.yml"), ("actor", {"login": "contributor"})]:
            with self.subTest(field=field):
                original = self.api.run[field]
                self.api.run[field] = value
                self.refused()
                self.api.run[field] = original

    def test_build_and_review_jobs_must_both_succeed(self):
        self.api.jobs["jobs"][0]["conclusion"] = "failure"
        self.refused()

    def test_spoofed_or_stale_status(self):
        for field, value in [("creator", {"login": "someone[bot]"}), ("state", "pending"),
                             ("target_url", "https://example.org"), ("description", "Another bundle")]:
            with self.subTest(field=field):
                original = self.api.status[field]
                self.api.status[field] = value
                self.refused()
                self.api.status[field] = original

    def test_enforced_protections(self):
        for field, value in [("enforce_admins", {"enabled": False}),
                             ("required_pull_request_reviews", {"required_approving_review_count": 1,
                              "dismiss_stale_reviews": True, "bypass_pull_request_allowances": {"users": [{"login": "owner"}]}}),
                             ("required_status_checks", {"checks": [{"context": common.CONTEXT, "app_id": 999}]}),
                             ("restrictions", {"apps": [{"id": 123}], "users": [{"login": "contributor"}]}),
                             ("required_pull_request_reviews", {"required_approving_review_count": 0})]:
            with self.subTest(field=field):
                original = self.api.policy[field]
                self.api.policy[field] = value
                self.refused()
                self.api.policy[field] = original

    def test_partial_merge_can_resume_without_merging_twice(self):
        self.api.fail_repo = f"{common.ORG}/settings"
        with self.assertRaises(common.Failure):
            self.merge()
        self.assertEqual(self.api.main[common.DISTRO], revision(1))
        self.api.fail_repo = None
        self.merge()
        self.assertEqual(len(self.api.merges), 3)

    def test_changed_component_after_partial_merge_blocks_retry(self):
        self.api.fail_repo = f"{common.ORG}/settings"
        with self.assertRaises(common.Failure):
            self.merge()
        self.api.main[f"{common.ORG}/telorgon"] = revision(999)
        self.api.fail_repo = None
        with self.assertRaises(common.Failure):
            self.merge()
        self.assertEqual(self.api.main[common.DISTRO], revision(1))

    def test_unexpected_merge_tree_blocks_promotion(self):
        self.api.bad_tree = True
        with self.assertRaises(common.Failure):
            self.merge()
        self.assertEqual(self.api.main[common.DISTRO], revision(1))

    def test_manifest_digest_and_pin_mismatch(self):
        bundle = fixture()
        bundle["pins"]["settings"] = revision(999)
        with self.assertRaises(common.Failure):
            c.validate_bundle(bundle)
        bundle["digest"] = c.digest({k: v for k, v in bundle.items() if k != "digest"})
        with self.assertRaises(common.Failure):
            c.validate_bundle(bundle)

    def test_pr_reference_injection_and_duplicates(self):
        for text in ["unknown#1", "settings#1,settings#2", "settings#1;whoami", "settings#0", "", "../x#2"]:
            with self.assertRaises(common.Failure):
                c.parse_refs(text)
        self.assertEqual(c.parse_refs("telorgon#42, settings#9"), [("telorgon", 42), ("settings", 9)])

    def test_current_actions_run_ids_exceed_ten_digits(self):
        run_id = 30_000_000_000
        self.assertEqual(c.number(str(run_id)), run_id)
        self.api.bundle["run_id"] = run_id
        self.api.bundle["digest"] = c.digest({k: v for k, v in self.api.bundle.items() if k != "digest"})
        self.api.hub["head"]["ref"] = f"integration/{run_id}"
        self.assertEqual(c.load_bundle(self.api, 99)[1]["run_id"], run_id)
        with self.assertRaises(common.Failure):
            c.number(2**63)

    def test_prepare_writes_all_pins_and_manifest_with_reviewed_parent(self):
        original = self.api.repo
        captured = {}
        self.api.commits[common.DISTRO, revision(1)] = {"tree": {"sha": revision(50)}, "parents": []}
        def endpoint(repo, suffix="", **kwargs):
            if suffix.startswith("/git/trees/"):
                return {"truncated": False, "tree": [{"path": path, "type": "commit", "mode": "160000",
                                                      "sha": fixture()["pins"][short]} for short, path in common.MODULES.items()]}
            if suffix in {"/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/pulls"} and "payload" in kwargs:
                captured[suffix] = kwargs["payload"]
                if suffix == "/pulls":
                    return {"number": 99}
                return {"sha": revision(300)}
            return original(repo, suffix, **kwargs)
        with patch.object(self.api, "repo", side_effect=endpoint):
            self.assertEqual(c.prepare(self.api, "telorgon#1,settings#2", 100, revision(2)), (99, revision(300)))
        manifest = json.loads(captured["/git/blobs"]["content"])
        self.assertEqual(c.validate_bundle(manifest), fixture())
        self.assertEqual(captured["/git/commits"]["parents"], [revision(1)])
        links = [entry for entry in captured["/git/trees"]["tree"] if entry["mode"] == "160000"]
        self.assertEqual(len(links), 6)
        self.assertEqual(captured["/git/refs"]["ref"], "refs/heads/integration/100")

    def test_moved_hub_head_and_forged_report_cannot_record_success(self):
        report = {"bundle_digest": self.api.bundle["digest"], "integration_head": self.api.head,
                  "review": {"summary": "No findings", "findings": [], "limitations": []}}
        with self.assertRaises(common.Failure):
            c.record(self.api, self.api, 99, revision(999), report)
        report["bundle_digest"] = "another-bundle"
        with self.assertRaises(common.Failure):
            c.record(self.api, self.api, 99, self.api.head, report)

    def test_unselected_pins_cannot_adopt_unmerged_component_code(self):
        original = self.api.repo
        def endpoint(repo, suffix="", **kwargs):
            if repo.endswith("/bootloader") and suffix.startswith("/compare/"):
                return {"status": "diverged", "behind_by": 1}
            return original(repo, suffix, **kwargs)
        with patch.object(self.api, "repo", side_effect=endpoint):
            self.refused()


if __name__ == "__main__":
    unittest.main()
