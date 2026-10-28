import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from stack_pr import cli, landing
from stack_pr.git import get_current_branch_name, is_rebase_in_progress
from stack_pr.shell_commands import get_command_output, run_shell_command


def stack_entry(number: int) -> cli.StackEntry:
    return cli.StackEntry(
        cli.CommitHeader(f"abcdef{number}\n    Change {number}"),
        _pr=f"https://github.com/jansel/example/pull/{number}",
        _head=f"stack/{number}",
        _base="main",
    )


def test_resume_after_partial_landing(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = [stack_entry(1), stack_entry(2)]
    states = dict.fromkeys([e.pr for e in stack], "OPEN")
    failed_ci = True
    merges = []

    def view_command(command: list[str]) -> str:
        assert command[:3] == ["gh", "pr", "view"]
        e = next(e for e in stack if e.pr == command[3])
        return json.dumps(
            {
                "state": states[e.pr],
                "number": int(e.pr.rsplit("/", 1)[-1]),
                "headRefName": e.head,
                "baseRefName": e.base,
            }
        )

    def status(pr: str) -> landing.PullRequestStatus:
        return landing.PullRequestStatus(
            state=states[pr],
            head="a" * 40,
            base="main",
            mergeable="MERGEABLE",
            merge_state="CLEAN",
            review="APPROVED",
            draft=False,
            auto_merge=False,
        )

    def checks(pr: str) -> list[str]:
        if pr == stack[1].pr and failed_ci:
            raise landing.LandingError("Required checks failed")
        return []

    def merge(e: cli.StackEntry, head: str, *, verbose: bool) -> None:
        assert head == "a" * 40
        merges.append(e.pr)
        states[e.pr] = "MERGED"

    monkeypatch.setattr(cli, "get_current_branch_name", lambda: "feature")
    monkeypatch.setattr(cli, "should_update_local_base", Mock(return_value=False))
    monkeypatch.setattr(cli, "get_stack", Mock(return_value=stack))
    monkeypatch.setattr(cli, "get_command_output", view_command)
    monkeypatch.setattr(
        cli, "run_shell_command", Mock(return_value=CompletedProcess([], 0))
    )
    monkeypatch.setattr(cli, "branch_exists", Mock(return_value=False))
    rebase = Mock()
    monkeypatch.setattr(cli, "rebase_pr", rebase)
    monkeypatch.setattr(cli, "merge_pr", merge)
    monkeypatch.setattr(landing, "get_pr_status", status)
    monkeypatch.setattr(landing, "pending_required_checks", checks)
    args = cli.CommonArgs(
        base="base",
        head="HEAD",
        remote="origin",
        target="main",
        hyperlinks=False,
        verbose=False,
        branch_name_template="stack",
        show_tips=False,
        land_disabled=False,
    )
    with pytest.raises(landing.LandingError, match="Required checks failed"):
        cli.command_land_all(args, wait=0, retries=0)
    assert merges == [stack[0].pr]
    failed_ci = False
    cli.command_land_all(args, wait=0, retries=0)
    assert merges == [stack[0].pr, stack[1].pr]
    assert all(call.args[0] is stack[1] for call in rebase.call_args_list)
    # A third run only performs local cleanup; no PR is merged twice.
    cli.command_land_all(args, wait=0, retries=0)
    assert len(merges) == 2


@pytest.mark.parametrize("states", [["OPEN", "MERGED"], ["MERGED", "CLOSED"]])
def test_resume_rejects_invalid_stack_states(
    states: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [
        json.dumps(
            {
                "state": state,
                "number": i + 1,
                "headRefName": f"stack/{i + 1}",
                "baseRefName": "main",
            }
        )
        for i, state in enumerate(states)
    ]
    monkeypatch.setattr(cli, "get_command_output", Mock(side_effect=responses))
    with pytest.raises(RuntimeError):
        cli.verify([stack_entry(1), stack_entry(2)], allow_merged=True)


def test_merge_matches_the_checked_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(return_value=CompletedProcess([], 0, b"", b""))
    monkeypatch.setattr(cli, "run_shell_command", run)
    cli.merge_pr(stack_entry(1), "a" * 40, verbose=True)
    command = run.call_args.args[0]
    assert command[-2:] == ["--match-head-commit", "a" * 40]
    assert run.call_args.kwargs["quiet"] is True


def test_local_rebase_conflict_aborts_and_restores_original_branch(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(git_repo)
    for key, value in [
        ("user.name", "Test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
    ]:
        run_shell_command(["git", "config", key, value], quiet=True)
    path = git_repo / "file.txt"
    path.write_text("base\n")
    run_shell_command(["git", "add", path], quiet=True)
    run_shell_command(["git", "commit", "-m", "Base"], quiet=True)
    remote = git_repo.parent / "remote.git"
    run_shell_command(["git", "clone", "--bare", git_repo, remote], quiet=True)
    run_shell_command(["git", "remote", "add", "origin", remote], quiet=True)
    run_shell_command(["git", "switch", "-c", "stack/1"], quiet=True)
    path.write_text("feature change\n")
    run_shell_command(["git", "commit", "-am", "Feature"], quiet=True)
    feature = get_command_output(["git", "rev-parse", "HEAD"])
    run_shell_command(["git", "push", "origin", "stack/1"], quiet=True)
    run_shell_command(["git", "switch", "main"], quiet=True)
    path.write_text("conflicting upstream change\n")
    run_shell_command(["git", "commit", "-am", "Upstream"], quiet=True)
    run_shell_command(["git", "push", "origin", "main"], quiet=True)

    monkeypatch.setattr(sys, "argv", ["stack-pr", "land-all", "--no-hyperlinks"])
    monkeypatch.setenv("STACKPR_CONFIG", str(git_repo / ".stack-pr.cfg"))
    monkeypatch.setattr(cli, "check_gh_installed", Mock())
    monkeypatch.setattr(cli, "get_branch_name_base", Mock(return_value="stack"))

    def land(args: cli.CommonArgs, *, wait: int, retries: int) -> None:
        cli.rebase_pr(stack_entry(1), "origin", "main", verbose=False)

    monkeypatch.setattr(cli, "command_land_all", land)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert not is_rebase_in_progress()
    assert get_current_branch_name() == "main"
    assert get_command_output(["git", "rev-parse", "stack/1"]) == feature
    assert get_command_output(["git", "rev-parse", "origin/stack/1"]) == feature
    assert path.read_text() == "conflicting upstream change\n"
    output = capsys.readouterr().out
    assert "Merge conflicts while rebasing" in output
    assert "not retrying" in output
    assert stack_entry(1).pr in output
