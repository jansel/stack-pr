# stack-pr — Jason Ansel's private fork

This is my private fork of [Modular's stack-pr](https://github.com/modular/stack-pr),
maintained at [jansel/stack-pr](https://github.com/jansel/stack-pr).
It creates a GitHub pull request for each commit in a stack, with each PR based
on the previous one so reviewers see only that commit's changes.

## Differences from upstream

This fork includes upstream changes through
[`57e425c`](https://github.com/modular/stack-pr/commit/57e425c26d112b8aa458c8d681e2ea511a426688),
plus these workflow changes:

- **Default submission:** running `stack-pr` with no arguments submits the stack
  and prints the resulting PRs.
- **Preserve PR descriptions:** submission keeps existing PR bodies and refreshes
  their cross-links. Use `--update-body` to replace bodies from commit messages;
  upstream uses `--keep-body` to opt into preserving them. Titles still update.
- **Interactive rebases:** submit and land commands can run while paused during
  `git rebase -i`. The fork temporarily saves and restores the rebase state,
  including in linked worktrees. Upstream rejects submission during a rebase.
  Resolve conflicts and commit changes before submitting.
- **Land the entire stack:** `land-all` merges from bottom to top, rebasing each
  remaining PR once just before its turn, with configurable waits and retries.
  Upstream's `land.style=disable` setting disables both `land` and `land-all` here.
- **Visible PR URLs:** each PR's full URL appears on its own line, including when
  terminal hyperlinks are disabled. Multi-PR descriptions label the stack
  “oldest at bottom.”
- **Restricted fetch configurations:** stack branches are fetched explicitly,
  including when `git remote set-branches origin main` restricts normal fetches.
- **Upgrade from GitHub:** `stack-pr upgrade` installs the latest `main` from
  this fork into the current installation's Python environment.

The upstream merge also brings the `config` command, repository-root config
lookup, optional usage tips, target-branch diagnostics, temporary draft status
while updating existing PRs, and quieter output.

The fork requires Python 3.10+, has no Python runtime dependencies, and uses
updated build and development tools. It is distributed from GitHub; installing
`stack-pr` by name from PyPI installs the upstream distribution.

## Install or upgrade this fork

You need Python 3.10 or newer, Git, and the [GitHub CLI](https://cli.github.com/).
Authenticate an account that can access this private fork and the repositories
where you want to use it:

```bash
gh auth login
gh auth setup-git
```

Use this command for both installation and upgrades, in your chosen Python
environment:

```bash
python -m pip install --upgrade "git+https://github.com/jansel/stack-pr.git@main"
```

For an isolated installation:

```bash
python3 -m venv ~/.venvs/stack-pr
~/.venvs/stack-pr/bin/python -m pip install --upgrade "git+https://github.com/jansel/stack-pr.git@main"
export PATH="$HOME/.venvs/stack-pr/bin:$PATH"
```

Add the `PATH` line to your shell startup file to keep the command available.
Once installed, update with:

```bash
stack-pr upgrade
```

This runs `python -m pip install --upgrade` using the Python interpreter that
runs `stack-pr`, targeting this fork's `main` branch. It works from any directory,
requires Git access to the fork, and reports pip's exit status if installation
fails. It does not need a working checkout or `gh` at runtime if Git credentials
are already configured.

For local development, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Basic workflow

Create a feature branch and make one commit per desired PR:

```bash
git fetch origin
git switch -c my-feature origin/main
# Edit files, then create a commit for each logical change.
git add path/to/file
git commit -m "First change"
# Repeat for the next change.
```

Inspect the stack, then create or update its PRs:

```bash
stack-pr view
stack-pr submit   # `stack-pr` and `stack-pr export` also submit
```

The output shows the newest commit first, with visible URLs:

```text
Stack:
   * cc932b71 (#439, 'jansel/stack/103' -> 'jansel/stack/102'): Improve navigation
         https://github.com/jansel/example/pull/439
   * 3475c898 (#438, 'jansel/stack/102' -> 'main'): Fix the coffee dispenser
         https://github.com/jansel/example/pull/438
```

Amend or reorder commits locally, then run `stack-pr submit` again. Existing PR
bodies are preserved; use `stack-pr submit --update-body` when you want to replace
them with the current commit messages.

To rebase onto the latest target branch:

```bash
git fetch origin
git rebase origin/main
stack-pr submit
```

Once reviewed and the bottom PR is mergeable, land one PR or the entire stack:

```bash
stack-pr land
# Or:
stack-pr land-all
```

`land` merges the bottom PR and rebases the remaining stack. `land-all` lands
bottom to top, rebasing each later PR just before merging it. After a rebase,
it sleeps to allow CI to run; failed merge commands are retried. GitHub's merge
requirements still apply.

You can also merge the bottom PR through GitHub, then fetch and rebase your
local branch before resubmitting the remaining stack.

## Commands

| Command | Behavior |
| --- | --- |
| `submit` / `export` | Create or update one PR per commit; the default with no arguments. |
| `view` | Inspect commits and linked PRs without pushing or rewriting commits. |
| `land` | Merge the bottom PR and rebase the rest. |
| `land-all` | Merge the entire stack with waits and retries. |
| `abandon` | Remove stack metadata and delete the associated stack branches. |
| `config section.key=value` | Write a configuration setting. |
| `upgrade` | Install the latest version of this fork from GitHub. |

### Commit ranges and common options

Stack commands operate on `BASE..HEAD`, targeting `origin/main` by default.
When `--base` is omitted, the base is the merge base of `HEAD` and the remote
target. Generated branches are named `$USERNAME/stack/$ID`; let `stack-pr`
manage these branches and the `stack-info` metadata in commit messages.

These options apply to `submit`, `view`, `land`, `land-all`, and `abandon`:

| Option | Meaning / default |
| --- | --- |
| `-R`, `--remote` | Git remote; `origin`. |
| `-B`, `--base` | Base revision; inferred from the remote target. |
| `-H`, `--head` | Head revision; `HEAD`. |
| `-T`, `--target` | Remote target branch; `main`. |
| `--hyperlinks` / `--no-hyperlinks` | Toggle terminal hyperlinks; full URLs always remain visible. |
| `--show-tips` / `--no-show-tips` | Toggle usage tips after commands. |
| `-V`, `--verbose` | Show additional progress and subprocess output. |
| `--branch-name-template` | Branch template; `$USERNAME/stack`. Supports `$USERNAME`, `$BRANCH`, and `$ID`; `/$ID` is appended if absent. |

Examples:

```bash
stack-pr view -B HEAD~5
stack-pr submit -B HEAD~5
stack-pr submit -H HEAD~2
stack-pr view --no-hyperlinks --no-show-tips
```

### Submission options

- `--update-body`: replace PR bodies from commit messages. By default, keep the
  current bodies and only refresh cross-links and titles.
- `-d`, `--draft`: create new PRs as drafts.
- `--draft-bitmask`: choose draft status for new PRs from oldest to newest, such
  as `0010` for a four-PR stack. The mask length must match the stack; `--draft`
  takes precedence.
- `--reviewer`: comma-separated reviewer handles; defaults to
  `$STACK_PR_DEFAULT_REVIEWER` or the config file.
- `-s`, `--stash`: temporarily stash uncommitted changes during submission.

### Landing the entire stack

```bash
stack-pr land-all --wait 30 --retries 10
```

`--wait` is the number of seconds to sleep after rebasing a later PR and between
failed merge attempts. `--retries` allows that many retries after the first
attempt, so `10` permits up to 11 attempts per PR. The initial stack must pass
verification before landing starts. Unlike repeatedly calling `land`, which
rebases the remaining stack after every merge, `land-all` rebases each later PR
once.

### Configuration

Defaults are read from `.stack-pr.cfg` at the Git repository root, including
when invoked from a subdirectory. `STACKPR_CONFIG` overrides the path.

```bash
stack-pr config common.hyperlinks=False
stack-pr config common.show_tips=False
stack-pr config repo.target=main
stack-pr config 'repo.branch_name_template=$USERNAME/$BRANCH'
stack-pr config land-all.wait=60
```

Example configuration:

```ini
[common]
verbose=False
hyperlinks=True
show_tips=True
draft=False
stash=False
[repo]
remote=origin
target=main
reviewer=GithubHandle1,GithubHandle2
branch_name_template=$USERNAME/$BRANCH
[land]
style=bottom-only
[land-all]
wait=30
retries=10
```

Set `land.style=disable` to disable both landing commands and require merging
through GitHub. Use `stack-pr <command> --help` for command-specific options.
