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
  Resolve conflicts and commit changes before submitting. Proposed upstream in
  [PR #88: Make submit work with `git rebase -i`](https://github.com/modular/stack-pr/pull/88).
- **Land the entire stack:** `land-all` merges from bottom to top, rebasing each
  remaining PR just before its turn. It watches required CI, confirms each merge,
  and resumes after interruptions by skipping already merged PRs.
  Upstream's `land.style=disable` setting disables both `land` and `land-all` here.
- **Visible PR URLs:** each PR's full URL appears on its own line, including when
  terminal hyperlinks are disabled. Multi-PR descriptions label the stack
  “oldest at bottom.”
- **Restricted-fetch bugfix:** stack branches are fetched explicitly, including
  when `git remote set-branches origin main` restricts normal fetches. This fixes
  branch-number reuse that could overwrite existing stack branches; proposed
  upstream in [PR #86](https://github.com/modular/stack-pr/pull/86).
- **Upgrade from GitHub:** `stack-pr upgrade` installs the latest `main` from
  this fork into the current installation's Python environment.
- **Failure recovery:** submissions restore the exact stash they created and
  restore PRs temporarily made draft, including after errors or Ctrl-C.

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

Check the installed version and source commit with:

```bash
stack-pr --version
```

The version comes from the installed package's metadata, independent of the
repository you run it in. GitHub installations also report the exact source
commit recorded by pip.

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

Once reviewed, land one PR or the entire stack:

```bash
stack-pr land
# Or:
stack-pr land-all
```

`land` merges the bottom PR and rebases the remaining stack. `land-all` lands
bottom to top, rebasing each later PR just before merging it. It waits for
required CI and confirms that GitHub has merged each PR before advancing.
GitHub's merge requirements still apply; missing approvals, failed required
checks, and merge conflicts stop the command.

You can also merge the bottom PR through GitHub, then fetch and rebase your
local branch before resubmitting the remaining stack.

## Commands

| Command | Behavior |
| --- | --- |
| `submit` / `export` | Create or update one PR per commit; the default with no arguments. |
| `view` | Inspect commits and linked PRs without pushing or rewriting commits. |
| `land` | Merge the bottom PR and rebase the rest. |
| `land-all` | Watch required CI and merge the stack; rerun to resume. |
| `abandon` | Remove stack metadata and delete the associated stack branches. |
| `config section.key=value` | Write a configuration setting. |
| `upgrade` | Install the latest version of this fork from GitHub. |
| `--version` | Print the installed version and source commit. |

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
- `-s`, `--stash`: temporarily stash tracked uncommitted changes during submission.
  Restores those changes and their staged status without consuming unrelated
  stashes. If restoration conflicts, the stash is retained for recovery.

### Landing the entire stack

```bash
stack-pr land-all --wait 30 --retries 10
```

`--wait` is the interval in seconds between checks of CI and merge status.
`--retries` is the number of rechecks after the initial check, so `10` permits
up to 11 polling rounds per PR. Both values must be nonnegative, including in
the config file. Increase `--retries` for longer CI or merge queues.

The command waits for pending required checks and GitHub's mergeability
calculation. It requests a merge once ready and waits for confirmation, including
when GitHub queues the PR. Known temporary transport errors can be retried;
merge conflicts, failed or cancelled required checks, drafts, missing approvals,
and permission errors stop the command.

If interrupted or stopped, rerun the same `land-all` command. It skips the
already merged PRs at the bottom of the stack and continues with the remaining
PRs. Closed but unmerged PRs and PRs merged out of stack order require fixing
the stack before proceeding.

For local rebase conflicts, `stack-pr` aborts the rebase it started, returns to
the original branch, and reports the PR URL and conflicting files. Resolve the
conflicts locally, resubmit the remaining changes, then rerun `land-all`.
Unlike repeatedly calling `land`, each later PR is rebased only when its turn
arrives, rather than after every earlier merge.

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
