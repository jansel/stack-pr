# Top of tree

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
