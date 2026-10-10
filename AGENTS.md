# Organization contribution instructions

These instructions apply to coding agents working in repositories owned by
WIPOperatingSystemName, including this `.github` repository. Other repositories
reference this file from their root `AGENTS.md`. Read it alongside the owning
repository's guidance; preserve its build, testing and project rules. Explicit
user instructions and existing authorization take precedence.

## Keep forks synchronized with the organization

- At the start of each task and when resuming ongoing work, inspect the working
  tree and verify the canonical WIPOperatingSystemName remote, personal fork
  remote and actual upstream default branch. In the standard contributor setup,
  `origin` is the organization and `fork` is the personal fork.
- Fetch both remotes before choosing a baseline. Fetch the organization again
  immediately before submission; never treat a cached reference or the fork's
  default branch as proof that the checkout is current.
- For ordinary sequential contributions, prefer the existing local and fork
  default branch, normally `main`. From a clean checkout on `main`, use
  `git pull --ff-only origin main` when the remotes match the standard setup.
  Do not create a new branch for every PR. Preserve the source branch of an
  already open PR; separate branches are for user-requested isolation or
  independent concurrent work.
- If branches have diverged, inspect the commits on both sides and integrate
  the freshly fetched organization branch with a normal merge. Preserve pending
  contribution commits and resolve conflicts deliberately. Do not reset,
  force-push, discard local changes or silently stash the user's work to make a
  pull succeed. Use a clean separate checkout when uncommitted work prevents
  safe integration.
- Before pushing, verify that the freshly fetched upstream commit is an
  ancestor of the submitted HEAD. In the standard setup, run
  `git merge-base --is-ancestor origin/main HEAD` and require success. If it
  fails, integrate upstream and rerun checks affected by that integration.
  Record the verified upstream commit in the PR or handoff.
- After a PR merges, fetch and integrate the organization default branch before
  the next task. Synchronize the personal fork through a normal push when
  authorized; if it has diverged, preserve its commits and reconcile them
  before pushing. Never overwrite fork history just to match upstream.
- If fetching or integration is blocked, report the concrete blocker and do
  not describe the fork or PR as synchronized.
- These rules do not authorize pulling or advancing distro's pinned source
  submodules as incidental build setup. Work on a component in its owning
  repository; keep distro pin updates separate and reviewed.

## Prepare the handoff

- PRs are reviewed and merged manually by the maintainer. Keep ordinary source,
  catalog and tooling checks; do not add AI review, automatic merges or generated
  cross-repository integration PRs unless the user explicitly requests them.
- Component merges do not advance distro source pins. Propose pin changes as a
  separate distro contribution with the relevant build and VM evidence.

- Complete the requested changes and appropriate verification before offering
  submission. Preserve unrelated work and inspect the final diff.
- Identify each owning Git repository, its organization upstream and its actual
  default branch. The current organization repositories use `main`; do not
  assume that a personal fork or the current working branch is the PR target.
- Summarize the changes, verification and any material limitations. Include a
  short suggested commit message.
- If there are changes to submit and the user has not already authorized or
  declined submission for this work, ask once:
  "Would you like me to commit these changes and open a pull request to
  WIPOperatingSystemName/<repository>'s default branch?"
- For changes spanning repositories, name the repositories in one combined
  question and propose a separate commit and PR for each owning repository.
- Explain that the offer follows the repository's contribution instructions.
  Editing files is not itself permission to commit, push or open a PR. Wait for
  an affirmative answer before those actions. If the user declines, leave the
  changes local. A missing answer is not approval.
- If the user already explicitly requested commits, pushes or PRs, perform the
  authorized steps without asking again. Do not offer another PR for work
  already submitted or for a task that produced no changes.

## After submission is authorized

- Stage only the intended changes on the selected contribution branch, normally
  the fork's existing default branch for sequential work. Inspect staged content
  before committing; exclude unrelated files and generated artifacts. Preserve
  the user's branch history and work.
- Prefer the contributor's configured `fork` remote for pushing, following the
  [contributor setup](profile/README.md). Verify that it belongs to the intended
  contributor. If it is missing, use an existing personal fork or create one
  within the authorized submission workflow. Never push directly to the
  organization's default branch.
- Open the PR against the owning WIPOperatingSystemName repository's actual
  default branch, or update the existing PR for the same work. When submitting
  from the fork's default branch, keep one active contribution per repository:
  later pushes to that branch update the same open PR. Describe the resulting
  behavior and relevant validation; disclose checks that failed or were not run.
- A change inside a distro source submodule belongs to that component's
  repository. A distro pin update is separate work and requires an intended,
  reviewed component commit. Do not advance pins merely to submit a component
  change.
- Commit/PR approval does not authorize merging, releases, deployment or
  changing branch protection. Leave those to the maintainer unless separately
  authorized.
- If authentication, permissions or connectivity prevent submission, retain
  the prepared changes and report the concrete blocker. Do not claim a commit,
  push or PR succeeded without verifying it.
- Return the created commit identifiers and PR links.
