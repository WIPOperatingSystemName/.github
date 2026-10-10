# Source checks and manual PR merging

Maintainers review and merge PRs directly in their owning GitHub repositories.
There is no AI review, polling, generated integration bundle or automatic merge.
Ordinary source checks and the distro's catalog/tooling tests still run on PRs.
The distro's manual build and VM qualification workflows remain available.

## Checks

Each repository's `source-checks.yml` calls the shared read-only workflow in
`.github`. It parses changed Python, JSON and TOML files without executing them.
For distro changes it also validates the declared six-submodule mapping and
changed recipes' versions, revisions, runtime dependencies and immutable source
pins. Deletions are ignored; renames check the new file. An initial push without
a comparison base checks the full committed tree.

Candidate source is read from Git objects. Submodules are not initialized and
candidate scripts are not imported or run by this checker. The implementation
comes from the organization-controlled `.github/main`. The check has read-only
repository permissions and uses no service credentials or paid API. It does not
compile Rust, validate all workflow YAML or establish build/boot/runtime behavior.

Keep repository-specific tests and run the relevant local build, package install
and VM checks before merging changes that affect runtime behavior. Follow the
[distro testing guide](https://github.com/WIPOperatingSystemName/distro/blob/main/docs/testing.md).

## Manual merge workflow

1. Synchronize with the organization, edit the owning repository and run its
   relevant checks. Push to your fork and open or update a PR to organization
   `main`, following the [contribution instructions](../AGENTS.md).
2. Inspect the diff and check results, resolve problems, then merge the PR in
   GitHub when satisfied. A component merge does not update distro pins.
3. When adopting a component version, open a separate distro PR selecting its
   intended merged commit. Rebuild affected packages, install them through the
   Python pipeline and guest pacman, and test the actual behavior in a private
   development VM. Record exact source/package identities and results.

## GitHub configuration

Merge the `.github` workflow removal/replacement PR first, then the caller
updates in the seven source repositories. Caller PR checks need the new checker
on `.github/main`. Existing generated `integration/*` distro PRs are obsolete;
close them without merging and keep the original component/distro PRs.

The former `distro/integration` status and bot-only push restrictions can block
manual merges even after the workflow is removed. With explicit maintainer
approval, remove that retired required status and allow the maintainer account
to merge. Preserve unrelated required checks, PR requirements, administrator
enforcement and force-push/deletion restrictions. After the replacement checks
have run, select their exact check name in branch protection if they should be
required; keep the distro's catalog/tooling checks as well.

Disable the old `Distro integration` workflow during migration after approving
the temporary loss of its source checks. After removal is merged, retire unused
`INTEGRATION_ENABLED`, `AUTO_MERGE_ENABLED`, `INTEGRATION_DISPATCH_TOKEN` and the
`integration-control`/`openai-review` environment credentials. Revoke the former
integration App installation and OpenAI credential or identity mapping when no
other workflow uses them. Never paste credential values into PRs or logs.

## Local verification

```sh
python3 -I -m unittest discover -s automation/tests -v
python3 -I -m unittest discover -s tests -v
python3 -I automation/source_checks.py --root ../distro --repository distro --base <base-commit>
```

Tests use temporary Git repositories and do not contact external services or
merge PRs. A passing syntax check is not a runtime qualification result.
