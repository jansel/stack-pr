from subprocess import CalledProcessError
from unittest.mock import Mock, call

import pytest

from stack_pr import cli


def entry(number: int) -> cli.StackEntry:
    return cli.StackEntry(
        cli.CommitHeader("abcdef\n    A change"),
        _pr=f"https://github.com/jansel/example/pull/{number}",
    )


@pytest.mark.parametrize(
    "failure", [None, RuntimeError("push failed"), KeyboardInterrupt()]
)
def test_original_draft_status_restored(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException | None
) -> None:
    ready, draft = entry(1), entry(2)
    monkeypatch.setattr(cli, "is_draft_pr", lambda e: e is draft)
    run = Mock()
    monkeypatch.setattr(cli, "run_shell_command", run)

    def submit() -> None:
        with cli.temporary_draft_status([ready, draft], verbose=False):
            cli.reset_remote_base_branches([ready, draft], "main", verbose=False)
            if failure is not None:
                raise failure

    if failure is not None:
        with pytest.raises(type(failure)):
            submit()
    else:
        submit()
    assert (
        call(["gh", "pr", "ready", ready.pr, "--undo"], quiet=True)
        in run.call_args_list
    )
    assert call(["gh", "pr", "ready", ready.pr], quiet=True) in run.call_args_list
    assert call(["gh", "pr", "ready", draft.pr], quiet=True) not in run.call_args_list
    assert not ready.is_tmp_draft


def test_failed_draft_request_still_restores_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pr = entry(1)
    monkeypatch.setattr(cli, "is_draft_pr", lambda e: False)
    run = Mock(side_effect=[CalledProcessError(1, "gh"), None])
    monkeypatch.setattr(cli, "run_shell_command", run)
    with (
        pytest.raises(CalledProcessError),
        cli.temporary_draft_status([pr], verbose=False),
    ):
        cli.reset_remote_base_branches([pr], "main", verbose=False)
    assert run.call_args == call(["gh", "pr", "ready", pr.pr], quiet=True)


@pytest.mark.parametrize("submission_failed", [False, True])
def test_cleanup_attempts_all_prs_and_reports_recovery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    submission_failed: bool,
) -> None:
    first, second = entry(1), entry(2)
    first.is_tmp_draft = second.is_tmp_draft = True
    run = Mock(side_effect=[CalledProcessError(1, "gh"), None])
    monkeypatch.setattr(cli, "run_shell_command", run)
    message = (
        "original failure" if submission_failed else "Could not restore ready status"
    )

    def submit() -> None:
        with cli.temporary_draft_status([first, second], verbose=False):
            if submission_failed:
                raise RuntimeError("original failure")

    with pytest.raises(RuntimeError, match=message):
        submit()
    assert run.call_count == 2
    assert first.is_tmp_draft
    assert not second.is_tmp_draft
    assert f"gh pr ready {first.pr}" in capsys.readouterr().out
