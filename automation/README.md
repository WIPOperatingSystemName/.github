# Maintainer setup

One endpoint: **[.github → Actions → Distro integration](https://github.com/WIPOperatingSystemName/.github/actions/workflows/integration.yml)**.

With `INTEGRATION_ENABLED=true` and `AUTO_MERGE_ENABLED=true`:

1. Contributors open ready PRs in the six component repositories or `distro`,
   updating their source branches from the canonical `main`.
2. The trusted `.github/main` workflow polls every 30 minutes and selects the
   oldest unattempted ready PR in each repository. It creates an exact distro
   integration bundle; contributor PRs can use their existing fork `main`.
3. OpenAI analyzes the immutable diff and full before/after changed text files.
   A security finding, material missing context, malformed/refused/incomplete
   response, or API failure denies the candidate and stops the build and merge.
4. Accepted candidates build and boot on a disposable worker. A separate general
   code review runs after qualification. Only the trusted controller can record
   passing statuses and automatically merge the unchanged tested commits.

No per-merge GitHub approval or merge dispatch is needed in automatic mode.
The `.github` controller repository itself remains under manual maintainer
control; it is not among the seven repositories the integration App can merge.
The schedule runs only from the default branch and can be delayed by GitHub.
The configured maintainer must activate or update the cron schedule so its
GitHub actor matches `MAINTAINER_LOGIN`; their account must remain active.
See [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

An App-owned integration receipt remembers attempted source/base/controller
revisions, including closed or denied bundles. Unchanged failed revisions are
not repeatedly sent to OpenAI by polling. Fix or update the source, or have the
maintainer deliberately dispatch **prepare** with e.g.
`telorgon#42,file-explorer#18,settings#9` to retry. A manual prepare also merges
automatically when automatic mode is enabled. There is one selected PR per
repository per bundle. Discovery fails closed beyond 100 open PRs per repository
or 1,000 distro PR receipts; manual prepare remains available.

**Status:** implemented, disabled until configured; live OpenAI review, remote
full builds and real merges have not yet been verified. The workflow never
grants the model GitHub credentials: its verdict is one required gate enforced
by the controller. Signing and public release promotion remain
separate maintainer operations.

## 1. Protect the controller

Keep `.github/main` under your control. Require PR review, dismiss stale approvals,
disallow force pushes and deletion, enforce protection for administrators, and
restrict updates to you. Use a `CODEOWNERS` entry for your actual GitHub login
covering `automation/`, `.github/workflows/` and `CODEOWNERS` itself. Contributors
must not be able to merge changes to privileged workflow code or alter secrets,
environments, branch policies or Actions settings.

Create two environments in **.github → Settings → Environments**, each allowing
deployments only from `main`:

- `integration-control`: GitHub App credential. You may add yourself as its
  required reviewer in manual mode. For automatic mode, omit required environment
  reviewers; otherwise every prepare/record/merge job waits for a human. Keep
  its deployment branch policy restricted to `main`.
- `openai-review`: OpenAI credential or OIDC mapping. No merge credential here.

## 2. Connect OpenAI

Use your OpenAI Platform project, with a restricted project service account and
appropriate model-request permissions. Choose a model available to your project
that supports Responses API structured output; set `OPENAI_MODEL` to its ID.
Configure project usage alerts/limits in OpenAI. Each attempted bundle can make
one security request (up to 6,000 output tokens) before any candidate execution,
plus one advisory request (up to 4,000 tokens) after a successful build. Manual
retries can incur another charge. Security input is limited to 24 changed files,
32 KB per full text file, 60 KB per repository diff and 180 KB serialized total.
The advisory combined diffs are limited to 60 KB. Oversized, binary, submodule,
invalid UTF-8 or unsupported file changes block acceptance; reduce/split the
change or improve and separately review the trusted review tooling. Data is
never silently truncated to obtain a passing verdict.

**Recommended: no saved API key.** Configure an OpenAI workload identity provider
for GitHub Actions, issuer `https://token.actions.githubusercontent.com`, audience
`https://api.openai.com/v1`, with these exact authorized claims:

| Claim | Required value |
| --- | --- |
| `repository` | `WIPOperatingSystemName/.github` |
| `ref` | `refs/heads/main` |
| `workflow_ref` | `WIPOperatingSystemName/.github/.github/workflows/integration.yml@refs/heads/main` |
| `environment` | `openai-review` |
| `iss` | `https://token.actions.githubusercontent.com` |
| `aud` | `https://api.openai.com/v1` |

Map the provider to your project service account. In `openai-review`, add variables
`OPENAI_AUTH_MODE=oidc`, `OPENAI_IDENTITY_PROVIDER_ID`,
`OPENAI_SERVICE_ACCOUNT_ID`, `OPENAI_WIF_AUDIENCE=https://api.openai.com/v1`,
and `OPENAI_MODEL`. The job exchanges GitHub's OIDC JWT for a short-lived bearer
token. Follow [OpenAI's GitHub Actions setup](https://developers.openai.com/api/docs/guides/workload-identity-federation/github-actions)
and [token exchange reference](https://developers.openai.com/api/reference/workload-identity-federation).

**Fallback:** set `OPENAI_AUTH_MODE=api-key` and save a restricted project API key
as the **environment secret** `OPENAI_API_KEY` in `openai-review`. Never place it
in code, an Actions variable, a PR or chat. GitHub masks credentials in logs;
the integration also masks exchanged tokens and excludes them from prompts,
reports and artifacts. See [GitHub secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

Diffs are sent to OpenAI as untrusted data. The model has no tools or credentials.
The request sets `store=false`; this is not a claim that all service retention
is disabled. The security report is binding: acceptance requires complete declared
coverage, no findings at any severity and no material context limitations. The
separate general code review is advisory. Structured output constrains the response
format, not its correctness; the gate can miss vulnerabilities or reject safe
changes. It complements deterministic tests and worker isolation. Only public
source inputs and qualification evidence belong in this pipeline. Never submit
signing credentials. Private-key blocks are rejected before API submission;
this detection does not replace source secret scanning.
See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## 3. Connect the GitHub App

Create an organization GitHub App dedicated to integration. Disable webhooks;
install it only on `distro`, `telorgon`, `bootloader`, `shell`, `file-explorer`,
`settings`, and `portal-picker`. Repository permissions:

| Permission | Access |
| --- | --- |
| Contents | Read and write |
| Pull requests | Read and write |
| Commit statuses | Read and write |
| Administration | Read only (audit branch protection) |
| Metadata | Read only |

In `integration-control`, save the generated PEM as secret
`INTEGRATION_APP_PRIVATE_KEY`; add variables `INTEGRATION_APP_ID` and
`INTEGRATION_INSTALLATION_ID`. The controller generates a temporary installation
token limited to those seven repositories. Its key file is private and temporary.
The App does not need access to `.github`: that repository's read-only Actions
token audits qualification runs. See [GitHub App authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation).

Before any merge, configure **classic branch protection** on `main` in all seven
repositories. This version audits classic protections; rulesets alone won't pass.
Enable merge commits, enforce protection for administrators, disable force pushes
and deletion, require a PR, and restrict branch updates to **only this App** with
no user/team writers or PR bypass allowances. Require status `distro/integration`
with this App selected as its expected source. Keep other relevant checks.
For automatic mode, set the required human approval count to **zero in all seven
repositories**, disable required code-owner/last-push approval, and retain the
required PR and App-sourced checks. The security gate is enforced through
`distro/integration`: that status passes only after security acceptance, runtime
qualification and report validation. Other required CI checks still apply through
GitHub's merge API; the controller cannot bypass them. Do not use GitHub's native
auto-merge on individual component PRs because the controller coordinates their
exact source pins with the distro bundle.

If GitHub hasn't yet listed the status/App, run one prepare with automatic mode
disabled to publish the initial pending status, then finish the expected-source
setting before merging. A merge with missing protection fails before changing
any repository.

## 4. Provide the build worker and enable

Publish the distro baseline with all six submodules. Register a **fresh disposable
Linux x86_64 VM** under label `custom-distro-ephemeral`: at least **128 GiB free
disk and 16 GiB RAM**, a Debian/Ubuntu apt environment, Rustup, Python 3.11+,
Meson **>=1.5 at `/usr/bin/meson`**, and Actions Runner **>=2.327.1** for the
pinned Node 24 actions. The workflow installs declared compiler
and VM seed packages. Give it at most one job, then destroy the VM, its disk and
runner registration. Do not attach host credentials, signing keys, persistent
workspaces or privileged host mounts. Register it for `.github` only; public
contributor PR workflows must not schedule arbitrary jobs on this runner.

The currently pinned Telorgon revision lacks the settings service API used by
the desktop consumers. Fix and publish compatible reviewed source pins before
expecting full qualification to pass. A successful console/systemd boot alone
does not satisfy this workflow's desktop requirement.

Builds execute contributor code only on this worker. Review, authentication and
merge run on separate GitHub-hosted machines from the trusted controller commit.
The worker never receives the OpenAI key, App key or OIDC token. Actions' job-local
artifact/runtime tokens remain scoped to that job; candidate artifacts are data.

In **.github → Settings → Secrets and variables → Actions → Variables**, add
`MAINTAINER_LOGIN` using your exact GitHub login. After completing setup, add
`INTEGRATION_ENABLED=true`, leaving `AUTO_MERGE_ENABLED` unset or `false` for
the first qualification trial. Until integration is enabled privileged jobs
are skipped; until automatic mode is enabled polling and automatic merge skip.

Run prepare against small real PRs, inspect public `candidate-evidence` and
`security-review`/`ai-review` artifacts and confirm the security job accepted
and every qualification check passed. Configure the required App checks and
zero-approval automatic protections, then set `AUTO_MERGE_ENABLED=true` and
dispatch a fresh prepare trial. It should merge without a human review after
the trusted checks succeed. Verify the resulting component/distro trees and
exercise a denied candidate before treating remote integration as verified.

## Manual mode

Leave `AUTO_MERGE_ENABLED=false`, require at least one human approval on
`distro/main` with stale approvals dismissed, then dispatch **prepare**.
Inspect the accepted security report and runtime evidence, approve the exact
integration commit using `MAINTAINER_LOGIN`, and dispatch **merge** with its
distro PR number. Manual mode retains the security gate; it is not a security
bypass. Changed source heads, bases or controller commits require a fresh prepare
and qualification. A partial automatic merge can be inspected and recovered
using this manual mode after configuring its approval protections.

## Merge behavior and recovery

GitHub cannot merge several repositories atomically. Component merges happen
first, and distro changes only after they all succeed. A failed component merge
leaves distro's pins untouched; inspect and retry the same merge operation. A
retry accepts an already merged component only if its base, parents, tree and
current `main` exactly match this bundle. Further changes require a new bundle.
No controller operation force-pushes or rolls back a public component branch.

Merge commits preserve the tested PR head as an ancestor of component `main`.
Distro keeps that original tested head as its pin; it does not rewrite pins to
an untested squash/rebase result. Changes to package payloads still need a package
revision increase, as described in distro's contribution rules.

Integration runs serialize. GitHub concurrency retains only one pending run, so an
additional request can replace a pending request; this is not a durable FIFO
queue. Retry a canceled request. Preparing multiple bundles is possible, but
merging one can invalidate the others' bases or statuses; reprepare those bundles
against the new baseline. Contributors continue working independently in PRs.

## Local validation

```sh
python3 -I -m unittest discover -s automation/tests -v
```

Tests use fake credentials and a stateful fake GitHub API. They exercise automatic
and manual authority, stale commits/bases, trusted security jobs/receipts,
generated-commit integrity, branch protection, polling/retry behavior, merge
ordering and partial retries, complete bounded source review and OIDC authentication.
They do not spend API credits or merge real PRs.
