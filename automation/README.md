# Maintainer setup

One endpoint: **[.github → Actions → Distro integration](https://github.com/WIPOperatingSystemName/.github/actions/workflows/integration.yml)**.

With `INTEGRATION_ENABLED=true` and `AUTO_MERGE_ENABLED=true`:

1. Contributors open ready PRs in the six component repositories or `distro`,
   updating their source branches from the canonical `main`.
2. PR notifications request an immediate scan by the trusted `.github/main`
   workflow. The 30-minute poll remains a fallback. Both select the oldest
   unattempted ready PR in each repository and create an exact distro integration
   bundle; contributor PRs can use their existing fork `main`.
3. Standard GitHub-hosted runners fetch immutable source data, audit the six
   canonical module mappings and pins, parse changed Python/JSON/TOML files, and
   check changed package recipe metadata. Candidate code is never executed.
4. One OpenAI request reviews security and correctness together. It receives the
   complete immutable patches and full new text files; deleted files include
   their old text. Shared contribution documents are included at the controller
   revision only for changes involving delegated contribution policy.
5. A finding, material missing source context, malformed/refused/incomplete
   response, or API failure blocks merging. Only the trusted controller records
   passing statuses and merges the unchanged reviewed commits.

**PR integration does not compile, execute or boot candidate code.** No self-hosted
runner, DigitalOcean account or managed VM is required. Build and boot verification
remain mandatory manual checks before a release. An accepted source review is not
build evidence and does not guarantee that the OS works or is vulnerability-free.

No per-merge GitHub approval or merge dispatch is needed in automatic mode.
The `.github` controller repository itself remains under manual maintainer
control; it is not among the seven repositories the integration App can merge.
The schedule runs only from the default branch and can be delayed by GitHub.
The configured maintainer must activate or update the cron schedule so its
GitHub actor matches `MAINTAINER_LOGIN`; their account must remain active.
See [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

An App-owned integration receipt remembers attempted source/base/controller
revisions, including closed or denied bundles. Unchanged failed revisions are
not repeatedly sent to OpenAI by notifications or polling, even when an unrelated distro merge
moves the distro baseline. A new dependency combination can be retried manually. Fix or update the source, or have the
maintainer deliberately dispatch **prepare** with e.g.
`telorgon#42,file-explorer#18,settings#9` to retry. A manual prepare also merges
automatically when automatic mode is enabled. There is one selected PR per
repository per bundle. Discovery fails closed beyond 100 open PRs per repository
or 1,000 distro PR receipts; manual prepare remains available.

**Status:** the source-only policy is covered by local tests; live source-only
reviews and automatic merges have not yet been verified. The model receives no
GitHub credentials. Signing and public release promotion remain separate
maintainer operations.

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
Configure project usage alerts and monitor the token counters in review receipts.
The workflow keeps requests bounded:

- One combined security/correctness request per attempted bundle, containing up
  to seven PRs. There is no separate advisory request, repair loop, model
  escalation, prewarming request or automatic API retry.
- Polling makes no OpenAI request when source/base/controller revisions have
  already been attempted. Explicit manual retries can incur another charge;
  changing the controller or source/base commits can require a fresh review.
- Static failures stop before OpenAI authentication or inference. Automatic mode
  also audits merge protection setup before preparing a candidate, avoiding
  paid reviews that cannot merge because setup is incomplete.
- Input is compact UTF-8 JSON, limited to 24 changed files, 32 KB per full text
  file, 60 KB per repository patch and **96 KB serialized total**. Full old text
  is omitted for modified files because changed old lines are already in the
  complete patch. Unrelated shared setup documents are omitted.
- Output has a **4,000-token ceiling**, including a concise summary and at most
  12 concrete findings. Input, output and cached-input token counts are recorded
  when supplied by the API, including for incomplete responses. Missing usage
  counters remain null; they are not reported as zero-cost requests.

The configured model is retained; select another compatible model with
`OPENAI_MODEL` after checking review quality and its price. Stable instructions
and schemas permit supported prompt caching without padding the prompt or making
extra requests. Token/byte bounds are per attempt, not a monthly dollar cap.
See [OpenAI cost optimization](https://developers.openai.com/api/docs/guides/cost-optimization)
and [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

Oversized, binary, submodule, invalid UTF-8 or unsupported changes block acceptance
before a paid review. Split the change or improve and separately review the
trusted tooling. Source data is never silently truncated to obtain acceptance.

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
is disabled. The combined source review is binding: acceptance requires complete
declared coverage, no security or correctness findings at any severity, and no
material missing source context. Missing build/boot evidence is explicitly
reserved for manual release verification. Structured output constrains the
response format, not its correctness; the gate can miss defects or reject safe
changes. Only public source inputs belong in this pipeline. Never submit
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
| Workflows | Read and write (prepare and merge workflow-file changes) |
| Administration | Read only (audit branch protection) |
| Metadata | Read only |

In `integration-control`, save the generated PEM as secret
`INTEGRATION_APP_PRIVATE_KEY`; add variables `INTEGRATION_APP_ID` and
`INTEGRATION_INSTALLATION_ID`. The controller generates a temporary installation
token limited to those seven repositories. Its key file is private and temporary.
The App does not need access to `.github`: that repository's read-only Actions
token audits trusted source-check runs. See [GitHub App authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation).

For an existing App, add **Workflows: read and write** under its **Permissions &
events**, save, and approve the updated permissions on its organization
installation. The controller also requests `workflows: write` in its temporary
token. Both grants are needed to prepare branches and merge PRs that change
`.github/workflows/`; Contents write alone is insufficient. A GitHub 403 during
prepare can indicate this missing grant. This App permission is separate from
the notification token's Actions permission.

Before any merge, configure **classic branch protection** on `main` in all seven
repositories. This version audits classic protections; rulesets alone won't pass.
Enable merge commits, enforce protection for administrators, disable force pushes
and deletion, require a PR, and restrict branch updates to **only this App** with
no user/team writers or PR bypass allowances. Require status `distro/integration`
with this App selected as its expected source. Keep relevant lightweight checks;
review your required-check list so an old full-build requirement does not keep
PRs waiting for the retired automatic build worker.
For automatic mode, set the required human approval count to **zero in all seven
repositories**, disable required code-owner/last-push approval, and retain the
required PR and App-sourced checks. The security gate is enforced through
`distro/integration`: that status now represents static source checks, combined
AI acceptance and immutable receipt validation. It does not represent a build
or a boot test. Other required CI checks still apply through
GitHub's merge API; the controller cannot bypass them. Do not use GitHub's native
auto-merge on individual component PRs because the controller coordinates their
exact source pins with the distro bundle.

If GitHub hasn't yet listed the status/App, run one prepare with automatic mode
disabled to publish the initial pending status, then finish the expected-source
setting before merging. A merge with missing protection fails before changing
any repository.

## 4. Enable source-only integration

Publish the distro baseline with all six submodules. Every automatic integration
job uses a standard GitHub-hosted Ubuntu runner. Only the trusted controller
checkout is executed; submitted files are fetched through GitHub's API and treated
as data. The source-check job has no OpenAI or App credential. The OpenAI job has
no App credential; merge credentials stay in separate trusted controller jobs.

In **.github → Settings → Secrets and variables → Actions → Variables**, add
`MAINTAINER_LOGIN` using your exact GitHub login. After completing setup, add
`INTEGRATION_ENABLED=true`, leaving `AUTO_MERGE_ENABLED` unset or `false` for
an initial review trial. Until integration is enabled privileged jobs skip;
until automatic mode is enabled polling and automatic merging skip.

Dispatch prepare against small real PRs and inspect the `checked-source` and
`security-review` artifacts. The static receipt must say `build_and_boot: not_run`;
the AI receipt must accept the same bundle, commit and checked-source digest.
Configure the required App checks and zero-approval automatic protections, then
set `AUTO_MERGE_ENABLED=true` and dispatch a fresh prepare. Verify the resulting
component/distro trees and denial behavior before treating remote integration as
verified. No VM provisioner or build-runner registration is part of this setup.

### PR notifications

Merge the controller and reusable `request-integration.yml` workflow into
`.github/main` first, then add the caller workflow in each of the seven source
repositories. New, reopened, updated and newly ready PRs targeting `main` request
a scan; draft PRs and generated distro integration PRs are ignored. Base changes
also request a scan. The caller uses `pull_request_target` so fork PRs can notify
the controller, but neither caller nor reusable workflow checks out or executes
PR code or interpolates PR content into a command.

Create a **fine-grained personal access token** owned by `MAINTAINER_LOGIN`, with
resource owner `WIPOperatingSystemName`, selected repository **`.github` only**,
and **Actions: read and write** (plus the implicit Metadata permission). Save it
as organization Actions secret `INTEGRATION_DISPATCH_TOKEN`, accessible only to
`distro`, `telorgon`, `bootloader`, `shell`, `file-explorer`, `settings` and
`portal-picker`. A repository secret with the same name in each caller also
works. This separate token dispatches workflows; it has no Contents, merge, App
private key or OpenAI access. Do not reuse the integration App key or a broadly
scoped login token. See [workflow dispatch permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

The notification dispatches `operation=scan` on `.github/main` without PR-supplied
arguments. GitHub attributes the dispatch to the token's maintainer, preserving
the existing actor and rerun checks. Scan uses the same receipt deduplication,
automatic-mode flags, source review and protected merge flow as polling. It does
not force a paid retry; explicit `prepare` retains that manual behavior. Missing
or expired dispatch credentials fail the notification visibly, while polling
continues. GitHub runner availability and the serialized controller still govern
when a requested scan starts.

## Manual verification before release

The maintainer must build and boot the exact proposed release revision and its
pinned components. Use the distro Python CLI and preserve real build, console,
upgrade, systemd, PAM and desktop results. The existing manual
[distro candidate workflow](https://github.com/WIPOperatingSystemName/distro/actions/workflows/candidate.yml)
and distro contribution documentation describe the qualification commands;
the full desktop workflow requires an adequate disposable worker when invoked.
Trusted local development builds may use the declared host seed environment;
untrusted recipes still require isolation. Source-review acceptance does not
waive these release checks or the distro's signing/package revision rules.

The currently pinned Telorgon revision lacks the settings service API used by
the desktop consumers. Resolve compatible source pins before releasing a
verified desktop image; source-only integration does not establish runtime
compatibility or repair that existing build issue.

## Manual mode

Leave `AUTO_MERGE_ENABLED=false`, require at least one human approval on
`distro/main` with stale approvals dismissed, then dispatch **prepare**.
Inspect the accepted source review and static receipt, approve the exact
integration commit using `MAINTAINER_LOGIN`, and dispatch **merge** with its
distro PR number. Manual mode retains the security gate; it is not a security
bypass. Changed source heads, bases or controller commits require a fresh prepare
and source review. A partial automatic merge can be inspected and recovered
using this manual mode after configuring its approval protections.

## Merge behavior and recovery

GitHub cannot merge several repositories atomically. Component merges happen
first, and distro changes only after they all succeed. A failed component merge
leaves distro's pins untouched; inspect and retry the same merge operation. A
retry accepts an already merged component only if its base, parents, tree and
current `main` exactly match this bundle. Further changes require a new bundle.
No controller operation force-pushes or rolls back a public component branch.

Merge commits preserve the reviewed PR head as an ancestor of component `main`.
Distro keeps that original reviewed head as its pin; it does not rewrite pins to
a different squash/rebase result. Changes to package payloads still need a package
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
and manual authority, stale commits/bases, trusted source jobs/receipts,
generated-commit integrity, branch protection, polling/retry behavior, merge
ordering and partial retries, data-only syntax/recipe parsing, bounded source
review, one-request usage accounting, deduplication and OIDC authentication.
They do not spend API credits or merge real PRs.
