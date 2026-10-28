import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from stack_pr import cli
from stack_pr.git import GitError, restore_stash, stash_changes
from stack_pr.shell_commands import get_command_output, run_shell_command


@pytest.fixture
def tracked_file(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(git_repo)
    path = git_repo / "file.txt"
    path.write_text("committed\n")
    run_shell_command(["git", "add", path], quiet=True)
    run_shell_command(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Add file",
        ],
        quiet=True,
    )
    return path


@pytest.mark.parametrize("verbose", [False, True])
def test_clean_worktree_preserves_existing_stash(
    tracked_file: Path, *, verbose: bool
) -> None:
    tracked_file.write_text("unrelated work\n")
    existing = stash_changes(verbose=False)
    assert existing is not None
    assert stash_changes(verbose=verbose) is None
    assert get_command_output(["git", "rev-parse", "refs/stash"]) == existing
    assert tracked_file.read_text() == "committed\n"


@pytest.mark.parametrize("verbose", [False, True])
def test_restore_exact_stash_and_index(tracked_file: Path, *, verbose: bool) -> None:
    tracked_file.write_text("staged work\n")
    run_shell_command(["git", "add", tracked_file], quiet=True)
    tracked_file.write_text("unstaged work\n")
    saved = stash_changes(verbose=verbose)
    assert saved is not None
    tracked_file.write_text("newer unrelated work\n")
    unrelated = stash_changes(verbose=False)
    restore_stash(saved, verbose=verbose)
    assert tracked_file.read_text() == "unstaged work\n"
    assert get_command_output(["git", "show", ":file.txt"]) == "staged work"
    assert get_command_output(["git", "rev-parse", "refs/stash"]) == unrelated
    assert saved not in get_command_output(["git", "stash", "list", "--format=%H"])


def test_restore_conflict_preserves_stash(tracked_file: Path) -> None:
    tracked_file.write_text("saved work\n")
    saved = stash_changes(verbose=False)
    assert saved is not None
    tracked_file.write_text("conflicting work\n")
    with pytest.raises(GitError, match="is preserved"):
        restore_stash(saved, verbose=False)
    assert get_command_output(["git", "rev-parse", "refs/stash"]) == saved
    assert tracked_file.read_text() == "conflicting work\n"


@pytest.mark.parametrize(
    "failure", [RuntimeError("submit failed"), KeyboardInterrupt()]
)
@pytest.mark.parametrize("verbose", [False, True])
def test_failed_submission_restores_branch_and_own_stash(
    tracked_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
    *,
    verbose: bool,
) -> None:
    tracked_file.write_text("unrelated stash\n")
    existing = stash_changes(verbose=False)
    tracked_file.write_text("uncommitted work\n")
    monkeypatch.setattr(
        sys, "argv", ["stack-pr", "submit", "--stash", *(["-V"] if verbose else [])]
    )
    monkeypatch.setenv("STACKPR_CONFIG", str(tracked_file.parent / ".stack-pr.cfg"))
    monkeypatch.setattr(cli, "check_gh_installed", Mock())
    monkeypatch.setattr(cli, "get_branch_name_base", Mock(return_value="stack"))
    monkeypatch.setattr(cli, "check_target_branch_exists", Mock())
    monkeypatch.setattr(cli, "deduce_base", lambda args: args)

    def submit(*args: object, **kwargs: object) -> None:
        run_shell_command(["git", "switch", "-c", "temporary"], quiet=True)
        raise failure

    monkeypatch.setattr(cli, "command_submit", submit)
    with pytest.raises(type(failure)):
        cli.main()
    assert get_command_output(["git", "branch", "--show-current"]) == "main"
    assert tracked_file.read_text() == "uncommitted work\n"
    assert get_command_output(["git", "stash", "list", "--format=%H"]) == existing
