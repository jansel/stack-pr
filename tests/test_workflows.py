import configparser
from pathlib import Path

import pytest

from stack_pr.cli import create_argparser, maybe_stash_interactive_rebase
from stack_pr.git import is_rebase_in_progress
from stack_pr.shell_commands import get_command_output, run_shell_command


@pytest.mark.parametrize("command", ["land", "land-all"])
def test_land_disabled(command: str) -> None:
    config = configparser.ConfigParser()
    assert create_argparser(config).parse_args([command]).command == command
    config.read_dict({"land": {"style": "disable"}})
    with pytest.raises(SystemExit) as exc:
        create_argparser(config).parse_args([command])
    assert exc.value.code == 2


@pytest.mark.parametrize("worktree", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_rebase_state_restored(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, *, worktree: bool, fails: bool
) -> None:
    repo = git_repo
    if worktree:
        repo = git_repo.parent / "worktree"
        run_shell_command(
            ["git", "worktree", "add", "-b", "feature", repo], cwd=git_repo, quiet=True
        )
    git_dir = Path(
        get_command_output(["git", "rev-parse", "--absolute-git-dir"], cwd=repo)
    )
    rebase_dir = git_dir / "rebase-merge"
    rebase_dir.mkdir()
    (rebase_dir / "state").write_text("original rebase state")
    subdir = repo / "subdir"
    subdir.mkdir()
    monkeypatch.chdir(subdir)
    assert is_rebase_in_progress()
    assert is_rebase_in_progress(repo)

    def submit_during_rebase() -> None:
        with maybe_stash_interactive_rebase():
            assert not is_rebase_in_progress()
            if fails:
                raise RuntimeError("Submission failed")

    if fails:
        with pytest.raises(RuntimeError, match="Submission failed"):
            submit_during_rebase()
    else:
        submit_during_rebase()
    assert is_rebase_in_progress()
    assert (rebase_dir / "state").read_text() == "original rebase state"
    assert not (git_dir / "rebase-merge-stashed").exists()


def test_existing_saved_rebase_is_preserved(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo)
    rebase_dir = git_repo / ".git/rebase-merge"
    rebase_dir.mkdir()
    (rebase_dir / "state").write_text("current")
    saved_dir = rebase_dir.with_name("rebase-merge-stashed")
    saved_dir.mkdir()
    (saved_dir / "state").write_text("saved")
    with (
        pytest.raises(RuntimeError, match="Saved rebase state already exists"),
        maybe_stash_interactive_rebase(),
    ):
        pytest.fail("An existing saved rebase must not be overwritten")
    assert (rebase_dir / "state").read_text() == "current"
    assert (saved_dir / "state").read_text() == "saved"
