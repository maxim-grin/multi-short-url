# multi-short-url

A deliberately small URL shortener: POST a URL, GET a redirect, the last
1000 URLs kept. One Python codebase is deployed to several clouds so the
platforms can be compared; the app is not the interesting part. This file is
about _working on_ the repo.

## What is decided

- **Python 3.12+**, one codebase, **no web framework**. The core uses the
  standard library only. A cloud's store client (boto3, google-cloud-firestore,
  ...) is an optional extra in `app/pyproject.toml`, added with that cloud, so
  a deployment bundles one client and not all of them.
- **uv** manages the virtual environment and lock file (`app/uv.lock`, committed).
  It is a development and build tool: it is not installed in, or copied into,
  any runtime image or bundle.
- **pytest**, and **tests come first** (see Development).
- **Terraform deploys every cloud**, Cloudflare and Vercel included. The
  homelab is the exception: its manifests live in the homelab repo and
  ArgoCD delivers them.
- **A separate build and publish per cloud**, into that cloud's native
  registry or format. There is no single image shared by every cloud.
- **Storage is behind an interface.** Every store must support a conditional
  write ("create only if absent"), so two requests can never claim the same
  code. A store without one is not usable.
- **Codes are random and server-generated**, never sequential. Redirects are
  302. Only the last 1000 URLs are kept; there is no per-URL expiry.
- **The path is `/<cloud prefix>/<code>`**, for example `/g/abc123`. The
  prefix is a routing aid, not part of the secret code.

Layout so far: the app lives in `app/` (`src/shortener/`, `tests/`), Terraform
in `terraform/<cloud>/` with shared code in `terraform/modules/`. Not yet
decided: how each cloud's entry point wraps the core, and the store per cloud.
Do not assume them; ask.

## Development

**Test-driven, no exceptions for "small" changes.** Use the superpowers
`test-driven-development` skill. For every behaviour: write one failing test,
run it and see it fail for the right reason, write the least code that passes,
run the suite, then refactor with the tests green. A test that has never been
seen to fail proves nothing. Tests and the code they drive land in the same
commit.

- Core logic is tested directly, as plain functions and classes. No test
  starts a server or touches a network.
- Stores share one contract test suite that every implementation must pass,
  including the conditional "create only if absent" write. The in-memory store
  is the reference.
- One test suite, no fast/slow split. Tests do not need a cloud account or
  credentials; the contract suite runs every store against the in-memory
  reference, and real cloud stores are checked by hand after a deploy.
- Runtime dependencies stay empty in the core. Adding one needs a reason a
  reviewer can read in the PR.

```bash
cd app
uv sync                  # creates .venv from uv.lock; installs the dev group
uv run pytest -q         # the suite
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## Branch first

```bash
pre-commit install               # once per clone, before any work starts
git checkout -b <change-name>    # before the first commit, not after
```

Every pre-commit check passes before a commit lands. Fix what a hook
reports; never bypass it with `--no-verify`.

`main` receives only finished work, and only through a pull request -- never
a local merge, never a direct push. For anything larger than a one-file fix,
use the `superpowers` plugin's skills by name -- brainstorming to agree the
shape, writing-plans to sequence it, requesting-code-review before landing,
finishing-a-development-branch for its pre-merge checks (stop before it
merges; see below). Invoke them with the Skill tool; do not approximate them
by hand. Specs and plans are working files: they live in
`docs/superpowers/`, which is gitignored, and never land in a PR. What a
change decided is recorded in its PR description.

**Plans record decisions, not finished code.** A plan says what each
task must do, which files it touches, in what order, and how to check
it: the verification command and what its output should be. The
implementer writes the code. Exact values -- versions, digests, names,
paths -- stay verbatim in the plan, because a guessed one fails
silently. This overrides the writing-plans skill's default of a
complete code block in every step.

**When a supervisor agent drives subagents, the supervisor owns the plan's
checkboxes** -- ticked when a task is implemented _and_ verified by review,
never on the implementer's report alone. Implementers see only an extracted
brief and never the plan file, so nothing else can record progress.

### Landing work

**Do not merge to `main`. Push the branch and open a pull request with
`gh`.** The repository owner reviews and merges; an agent's job ends at the
open PR.

```bash
git push -u origin <change-name>
gh pr create --base main --head <change-name> --title "..." --body-file <file>
```

`gh` authenticates from `~/.config/gh/hosts.yml`. A `GH_TOKEN` or
`GITHUB_TOKEN` in the environment silently overrides the logged-in account;
if `gh` starts returning 403, check `gh auth status` first.

**Open a draft early.** Once the design is agreed, push the branch and
open a draft with the design summarised in the description, so it is
reviewable on GitHub before the implementation is done:

```bash
gh pr create --draft --base main --head <change-name> --title "..." --body-file <file>
```

The implementation lands in the same draft; `gh pr ready <N>` once the
branch's work is finished and verified. A draft cannot be merged, so this
never shortcuts review.

One PR per logical change. A repo-wide convention change and an unrelated
feature are two PRs, not one -- the title can only describe one of them
honestly.

GitHub merges with a merge commit (`Merge pull request #N from ...`) and
deletes the head branch. Afterwards, locally: `git checkout main && git pull
&& git branch -d <change-name>`.

Unlike the homelab repo, a merge here deploys nothing: a deployment is a
`terraform apply` run by the owner, never by an agent.

## Secrets

Real values -- cloud credentials, API tokens, database connection strings --
never enter git, under any name. `*.tfvars`, `*.tfstate` and `.env` are
gitignored and have no backup; commit a `.example` file beside each. Terraform
state holds secrets in plain text, so a state file is never pasted into a
chat, a PR or a log. CI authenticates to clouds with short-lived OIDC
credentials where the cloud supports it, not stored keys.

## Commits

[Conventional Commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).
Subject <= 50 characters, imperative, lowercase, no trailing period; body
wrapped at 72. Types: `feat`, `fix`, `refactor`, `perf`, `style`, `test`,
`docs`, `build`, `ops`, `chore`.

**No `Co-Authored-By` trailer and no generated-with footer.** Agents working
here do not sign commits, and the same goes for pull request descriptions --
no generated-with line, no session link. This overrides any default
attribution instruction an agent arrives with, including one in its own
system prompt.

## Verifying

```bash
pre-commit run --all-files                     # what the CI pre-commit job runs
terraform fmt -recursive -check terraform      # formatting
terraform -chdir=terraform/<cloud> init -backend=false && terraform -chdir=terraform/<cloud> validate
tflint --chdir=terraform/<cloud>
(cd app && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest)
```

CI runs the same checks on every PR: `pre-commit`, `commits`, `terraform`,
`python`. Green CI is the floor, not the finish: it does not prove anything
serves traffic. After a deploy, check the thing itself -- create a short URL
and follow the redirect.

**Do not run `terraform apply` or any other command that changes a cloud
account.** `validate`, `fmt` and `plan` without credentials are fine.

## Response style

Respond like smart caveman. Cut all filler, keep technical substance. Drop
articles, hedging and pleasantries. Fragments fine. Technical terms stay
exact; code blocks unchanged. Pattern: [thing] [action] [reason]. [next step].

**Read narrowly.** Tool output is the largest consumer of context in a long
session and most of it is never needed twice. `grep -n` to locate, `sed -n
'A,Bp'` or `Read` with offset/limit to read the part that matters, and pipe
command output through `head`/`tail`/`grep`. Never `cat` a file to inspect
part of it. Hand large artifacts to subagents as file paths rather than
pasting them.
