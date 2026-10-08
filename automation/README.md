# Maintainer setup

One endpoint: **[.github → Actions → Distro integration](https://github.com/WIPOperatingSystemName/.github/actions/workflows/integration.yml)**.

1. Contributors open PRs in their component repositories or `distro`.
2. Run **prepare** on `main`, with e.g. `telorgon#42,file-explorer#18,settings#9`.
   The controller creates a distro integration PR, builds and boots the combined
   source, then posts an advisory OpenAI review.
3. Inspect the results and **approve that exact integration PR commit**.
4. Run **merge**, supplying its distro PR number. The controller checks your
   approval, unchanged commits/bases, trusted tests and branch protection, then
   merges components and adopts their pins together in distro.

New commits or a changed base require a fresh prepare run and approval. Update
each source branch from its repository's `main` before preparing. One bundle
accepts one PR per repository, including an optional distro code PR.

**Status:** implemented, disabled until configured; live OpenAI review, remote
full builds and real merges have not yet been verified. The workflow never
grants the model merge authority. Signing and public release promotion remain
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
  required reviewer for another execution gate; allow self-review if you're
  the only maintainer. This gate applies to prepare, record and merge jobs.
- `openai-review`: OpenAI credential or OIDC mapping. No merge credential here.

## 2. Connect OpenAI

Use your OpenAI Platform project, with a restricted project service account and
appropriate model-request permissions. Choose a model available to your project
that supports Responses API structured output; set `OPENAI_MODEL` to its ID.
Configure project usage alerts/limits in OpenAI. Each successful prepare build
makes one review request; rerunning it can make another. Combined diffs are
limited to 60 KB and output to 4,000 tokens. Larger changes must be split.

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
is disabled. Reports are advisory and can miss defects or contain false positives.
Only public source inputs and qualification evidence belong in this pipeline.

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
Component PR review count may be zero because your approval is on the combined
distro PR; distro requires at least one approval and dismissal of stale reviews.
The controller additionally checks that the latest approval is yours and names
the current commit. Other repository checks/review requirements still apply.

If GitHub hasn't yet listed the status/App, run one prepare to publish its first
successful check, then finish the expected-source setting before merging. A merge
with missing protection fails before changing any repository.

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

Builds execute contributor code only on this worker. Review, authentication and
merge run on separate GitHub-hosted machines from the trusted controller commit.
The worker never receives the OpenAI key, App key or OIDC token. Actions' job-local
artifact/runtime tokens remain scoped to that job; candidate artifacts are data.

In **.github → Settings → Secrets and variables → Actions → Variables**, add
`MAINTAINER_LOGIN` using your exact GitHub login. After completing setup, add
`INTEGRATION_ENABLED=true`. Until then privileged jobs are skipped.

Run prepare against small real PRs, inspect public `candidate-evidence` and
`ai-review` artifacts, configure the required App checks, approve the integration
PR and exercise merge. Only then treat the remote integration as verified.

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

Merge jobs serialize. GitHub concurrency retains only one pending run, so an
additional request can replace a pending request; this is not a durable FIFO
queue. Retry a canceled request. Preparing multiple bundles is possible, but
merging one can invalidate the others' bases or statuses; reprepare those bundles
against the new baseline. Contributors continue working independently in PRs.

## Local validation

```sh
python3 -I -m unittest discover -s automation/tests -v
```

Tests use fake credentials and a stateful fake GitHub API. They exercise exact
approval, stale commits/bases, trusted status/run checks, branch protection,
merge ordering and partial retries, bounded reports and OIDC authentication.
They do not spend API credits or merge real PRs.
