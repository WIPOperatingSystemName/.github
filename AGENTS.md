# Organization contribution instructions

These instructions apply to coding agents working in repositories owned by
WIPOperatingSystemName, including this `.github` repository. Other repositories
reference this file from their root `AGENTS.md`. Read it alongside the owning
repository's guidance; preserve its build, testing and project rules. Explicit
user instructions and existing authorization take precedence.

## Prepare the handoff

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

- Use a feature branch and stage only the intended changes. Inspect staged
  content before committing; exclude unrelated files and generated artifacts.
  Preserve the user's branch history and work.
- Prefer the contributor's configured `fork` remote for pushing, following the
  [contributor setup](profile/README.md). Verify that it belongs to the intended
  contributor. If it is missing, use an existing personal fork or create one
  within the authorized submission workflow. Never push directly to the
  organization's default branch.
- Open the PR against the owning WIPOperatingSystemName repository's actual
  default branch. Describe the resulting behavior and relevant validation;
  disclose checks that failed or were not run.
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
