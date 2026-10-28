# Top of tree

* Added `stack-pr --version`, including the source commit for GitHub installs.
* Fixed stash restoration with verbose output, preserving unrelated stashes,
  staged changes, and recoverable stashes after conflicts.
* Restore PRs temporarily made draft after submission errors or interrupts,
  and report manual recovery commands if restoring their status fails.
* `land-all` now polls required CI and confirms merges before advancing,
  resumes after partially completed runs, and rejects negative wait/retry values.
* Stop landing immediately on merge conflicts, failed required checks, missing
  approvals, or permanent merge errors. Abort local rebase conflicts and restore
  the original branch, including after interrupts.
* Linked upstream PRs #86 (restricted-fetch bugfix) and #88 (interactive rebases).

* Merged upstream through `57e425c`, retaining the fork's interactive-rebase
  support, default submission, preserved PR bodies, and `land-all` command.
  The upstream `land.style=disable` option now disables both landing commands.
* Added `stack-pr upgrade` to install the latest `jansel/stack-pr` main branch
  with pip in the running command's Python environment.
* Print full PR URLs on separate lines, with or without terminal hyperlinks.
* Documented the private fork, upstream differences, and GitHub installation.
* Updated development/build dependencies and CI, require Python 3.10+, and
  removed the unused runtime backport and stale PDM/Pixi configuration.
* Replaced the upstream PyPI release workflow with build validation and added
  type checks, a Python 3.10–3.15 test matrix, and dependency update checks.
* Fixed rebase-state handling in worktrees and subdirectories, protected saved
  rebase state, and corrected subprocess argument/output handling.

* Added `land-all` command that lands the entire stack in a loop, rebasing each
  PR exactly once and waiting for required CI between lands. Configurable wait
  (`--wait`, default 30s) and retries (`--retries`, default 10).

# Version 0.1.3

* Fix a bug with replacing $USERNAME in the branch name. (#44)

# Version 0.1.2

* Added config files - now defaults for the CL options can be customized with
  local config files (#32).
* Added a feature to customize branch names for stacked PRs (#33).
* Fixed a bug with branches not being deleted when a stack is abandoned (#27).
* Subcommands outputs is suppressed for less spammy look (#26).

# Version 0.1.1
