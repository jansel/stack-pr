import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from stack_pr import cli
from stack_pr.shell_commands import get_command_output, run_shell_command


@pytest.fixture
def submitted_stack(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[cli.StackEntry], dict[str, dict[str, str]]]:
    monkeypatch.chdir(git_repo)

    def commit(message: str) -> str:
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
                "--allow-empty",
                "-m",
                message,
            ],
            quiet=True,
        )
        return get_command_output(["git", "rev-parse", "HEAD"])

    entries = []
    remote = {}
    base = "main"
    for number in (1, 2):
        head = f"stack/{number}"
        run_shell_command(["git", "checkout", "-b", head], quiet=True)
        if number == 1:
            commit("Earlier lower revision")
        sha = commit(f"Original {number}")
        e = cli.StackEntry(
            cli.CommitHeader(f"{sha}\n    Change {number}"),
            _pr=f"https://github.com/jansel/example/pull/{number}",
            _head=head,
            _base=base,
        )
        entries.append(e)
        remote[e.pr] = {
            "state": "OPEN",
            "headRefName": head,
            "headRefOid": sha,
            "baseRefName": base,
        }
        base = head
    # Rebase both local commits while keeping the submitted PR topology.
    for e in entries:
        run_shell_command(
            ["git", "checkout", "-B", e.head, e.base or "main"], quiet=True
        )
        e.commit = cli.CommitHeader(f"{commit(e.head)}\n    Updated {e.head}")

    def query(command: list[str]) -> str:
        assert command[:3] == ["gh", "pr", "view"]
        return json.dumps(remote[command[3]])

    monkeypatch.setattr(cli, "get_command_output", query)
    return entries, remote


def test_rebased_stack_preserves_existing_bases(
    submitted_stack: tuple[list[cli.StackEntry], dict[str, dict[str, str]]],
) -> None:
    entries, _ = submitted_stack
    assert cli.can_preserve_remote_bases(entries, verbose=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [("baseRefName", "main"), ("headRefName", "renamed"), ("state", "CLOSED")],
)
def test_changed_topology_keeps_detachment_path(
    submitted_stack: tuple[list[cli.StackEntry], dict[str, dict[str, str]]],
    field: str,
    value: str,
) -> None:
    entries, remote = submitted_stack
    remote[entries[1].pr][field] = value
    assert not cli.can_preserve_remote_bases(entries, verbose=False)


def test_patch_moved_into_base_requires_detachment(
    submitted_stack: tuple[list[cli.StackEntry], dict[str, dict[str, str]]],
) -> None:
    entries, remote = submitted_stack
    run_shell_command(
        ["git", "branch", "-f", entries[0].head, remote[entries[1].pr]["headRefOid"]],
        quiet=True,
    )
    assert not cli.can_preserve_remote_bases(entries, verbose=False)


def test_unknown_remote_commit_cannot_prove_safe_update(
    submitted_stack: tuple[list[cli.StackEntry], dict[str, dict[str, str]]],
) -> None:
    entries, remote = submitted_stack
    remote[entries[1].pr]["headRefOid"] = "f" * 40
    assert not cli.can_preserve_remote_bases(entries, verbose=False)


def test_new_head_contained_in_old_base_requires_detachment(
    submitted_stack: tuple[list[cli.StackEntry], dict[str, dict[str, str]]],
) -> None:
    entries, remote = submitted_stack
    old_lower = remote[entries[0].pr]["headRefOid"]
    run_shell_command(
        ["git", "checkout", "-B", entries[0].head, f"{old_lower}^"], quiet=True
    )
    run_shell_command(["git", "checkout", "-B", entries[1].head, old_lower], quiet=True)
    # If GitHub processes the upper update first, its head and old base
    # coincide. The old-upper/new-base check alone would miss this closure.
    assert not cli.can_preserve_remote_bases(entries, verbose=False)


def test_new_stack_keeps_existing_submission_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = Mock(side_effect=AssertionError("new PRs have no remote state"))
    monkeypatch.setattr(cli, "get_command_output", query)
    assert not cli.can_preserve_remote_bases(
        [cli.StackEntry(cli.CommitHeader("a"))], verbose=False
    )
    query.assert_not_called()


@pytest.mark.parametrize("preserve", [False, True])
def test_submit_preserves_bases_only_after_safety_check(
    monkeypatch: pytest.MonkeyPatch, *, preserve: bool
) -> None:
    e = cli.StackEntry(
        cli.CommitHeader("abcdef\n    Change"),
        _pr="https://github.com/jansel/example/pull/1",
        _head="stack/1",
        _base="main",
    )
    for name in (
        "check_no_duplicate_prs",
        "init_local_branches",
        "create_pr",
        "verify",
        "print_stack",
        "add_cross_links",
        "delete_local_branches",
        "print_tips_after_export",
    ):
        monkeypatch.setattr(cli, name, Mock())
    monkeypatch.setattr(cli, "is_rebase_in_progress", lambda: False)
    monkeypatch.setattr(cli, "get_current_branch_name", lambda: "dev")
    monkeypatch.setattr(cli, "should_update_local_base", Mock(return_value=False))
    monkeypatch.setattr(cli, "get_stack", Mock(return_value=[e]))
    monkeypatch.setattr(cli, "is_ancestor", Mock(return_value=False))
    monkeypatch.setattr(cli, "add_or_update_metadata", Mock(return_value=False))
    monkeypatch.setattr(
        cli, "run_shell_command", Mock(return_value=CompletedProcess([], 0))
    )
    events = []

    def check(*args: object, **kwargs: object) -> bool:
        events.append("check")
        return preserve

    def reset(*args: object, **kwargs: object) -> None:
        events.append("detach")

    def push(*args: object, **kwargs: object) -> None:
        events.append("push")

    monkeypatch.setattr(cli, "can_preserve_remote_bases", check)
    monkeypatch.setattr(cli, "reset_remote_base_branches", reset)
    monkeypatch.setattr(cli, "push_branches", push)
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
    cli.command_submit(args, draft=False, reviewer="", keep_body=True)
    assert events == (["check"] if preserve else ["check", "detach"]) + ["push", "push"]
