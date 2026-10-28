import configparser
import json
from dataclasses import replace
from subprocess import CalledProcessError, CompletedProcess
from unittest.mock import Mock

import pytest

from stack_pr import cli, landing

PR = "https://github.com/jansel/example/pull/1"


@pytest.fixture
def ready() -> landing.PullRequestStatus:
    return landing.PullRequestStatus(
        state="OPEN",
        head="a" * 40,
        base="main",
        mergeable="MERGEABLE",
        merge_state="CLEAN",
        review="APPROVED",
        draft=False,
        auto_merge=False,
    )


@pytest.fixture
def sleep(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock()
    monkeypatch.setattr(landing.time, "sleep", mock)
    return mock


def test_waits_for_required_checks(
    ready: landing.PullRequestStatus, sleep: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = [
        replace(ready, merge_state="BLOCKED"),
        ready,
        replace(ready, state="MERGED"),
    ]
    monkeypatch.setattr(landing, "get_pr_status", Mock(side_effect=states))
    checks = Mock(side_effect=[["build"], []])
    monkeypatch.setattr(landing, "pending_required_checks", checks)
    merge = Mock()
    landing.land_when_ready(PR, "main", merge, wait=7, retries=1)
    sleep.assert_called_once_with(7)
    merge.assert_called_once_with(ready.head)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("mergeable", "CONFLICTING", "Merge conflicts"),
        ("merge_state", "DIRTY", "Merge conflicts"),
        ("review", "REVIEW_REQUIRED", "required review"),
        ("review", "CHANGES_REQUESTED", "required review"),
        ("state", "CLOSED", "CLOSED"),
        ("draft", True, "draft PR"),
        ("base", "other", "expected base"),
        ("merge_state", "BEHIND", "behind main"),
    ],
)
def test_blockers_stop_without_retrying(
    ready: landing.PullRequestStatus,
    sleep: Mock,
    monkeypatch: pytest.MonkeyPatch,
    *,
    field: str,
    value: str | bool,
    message: str,
) -> None:
    status = ready
    setattr(status, field, value)
    monkeypatch.setattr(landing, "get_pr_status", Mock(return_value=status))
    checks, merge = Mock(), Mock()
    monkeypatch.setattr(landing, "pending_required_checks", checks)
    with pytest.raises(landing.LandingError, match=message):
        landing.land_when_ready(PR, "main", merge, wait=30, retries=10)
    sleep.assert_not_called()
    merge.assert_not_called()
    checks.assert_not_called()


@pytest.mark.parametrize("bucket", ["fail", "cancel"])
def test_failed_required_checks_stop_immediately(
    ready: landing.PullRequestStatus,
    sleep: Mock,
    monkeypatch: pytest.MonkeyPatch,
    bucket: str,
) -> None:
    monkeypatch.setattr(landing, "get_pr_status", Mock(return_value=ready))
    output = json.dumps(
        [{"name": "build", "bucket": bucket, "link": "https://example.com/check"}]
    ).encode()
    monkeypatch.setattr(
        landing,
        "run_shell_command",
        Mock(return_value=CompletedProcess([], 1, output, b"")),
    )
    merge = Mock()
    with pytest.raises(landing.LandingError, match=r"Required checks failed.*build"):
        landing.land_when_ready(PR, "main", merge, wait=30, retries=10)
    merge.assert_not_called()
    sleep.assert_not_called()


@pytest.mark.parametrize(
    ("bucket", "code", "expected"),
    [("pass", 0, []), ("skipping", 0, []), ("pending", 8, ["build"])],
)
def test_required_check_results(
    monkeypatch: pytest.MonkeyPatch, bucket: str, code: int, expected: list[str]
) -> None:
    output = json.dumps([{"name": "build", "bucket": bucket, "link": ""}]).encode()
    run = Mock(return_value=CompletedProcess([], code, output, b""))
    monkeypatch.setattr(landing, "run_shell_command", run)
    assert landing.pending_required_checks(PR) == expected
    assert "--required" in run.call_args.args[0]


@pytest.mark.parametrize(
    ("stderr", "no_checks"),
    [(b"no checks reported on branch", True), (b"HTTP 403 forbidden", False)],
)
def test_empty_check_response(
    monkeypatch: pytest.MonkeyPatch, stderr: bytes, *, no_checks: bool
) -> None:
    monkeypatch.setattr(
        landing,
        "run_shell_command",
        Mock(return_value=CompletedProcess([], 1, b"", stderr)),
    )
    if no_checks:
        assert landing.pending_required_checks(PR) == []
    else:
        with pytest.raises(CalledProcessError):
            landing.pending_required_checks(PR)


def test_waits_for_confirmation_without_repeating_merge(
    ready: landing.PullRequestStatus, sleep: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = [ready, ready, ready, replace(ready, state="MERGED")]
    monkeypatch.setattr(landing, "get_pr_status", Mock(side_effect=states))
    monkeypatch.setattr(landing, "pending_required_checks", Mock(return_value=[]))
    merge = Mock()
    landing.land_when_ready(PR, "main", merge, wait=1, retries=2)
    merge.assert_called_once()
    assert sleep.call_count == 2


def test_already_merged_does_not_attempt_merge(
    ready: landing.PullRequestStatus, sleep: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        landing, "get_pr_status", Mock(return_value=replace(ready, state="MERGED"))
    )
    merge = Mock()
    landing.land_when_ready(PR, "main", merge, wait=0, retries=0)
    merge.assert_not_called()
    sleep.assert_not_called()


@pytest.mark.parametrize("stderr", [b"cannot be cleanly merged", b"HTTP 403 forbidden"])
def test_merge_errors_are_not_blindly_retried(
    ready: landing.PullRequestStatus,
    sleep: Mock,
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes,
) -> None:
    # Even when GitHub still reports CLEAN, the merge command can find a conflict.
    monkeypatch.setattr(landing, "get_pr_status", Mock(return_value=ready))
    monkeypatch.setattr(landing, "pending_required_checks", Mock(return_value=[]))
    merge = Mock(side_effect=CalledProcessError(1, "gh", stderr=stderr))
    with pytest.raises(CalledProcessError):
        landing.land_when_ready(PR, "main", merge, wait=30, retries=10)
    merge.assert_called_once()
    sleep.assert_not_called()


def test_transient_merge_failure_can_retry(
    ready: landing.PullRequestStatus, sleep: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = Mock(return_value=ready)
    monkeypatch.setattr(landing, "get_pr_status", status)
    monkeypatch.setattr(landing, "pending_required_checks", Mock(return_value=[]))
    calls = []

    def merge(head: str) -> None:
        calls.append(head)
        if len(calls) == 1:
            raise CalledProcessError(1, "gh", stderr=b"HTTP 503 Service Unavailable")
        status.return_value = replace(ready, state="MERGED")

    landing.land_when_ready(PR, "main", merge, wait=1, retries=1)
    assert len(calls) == 2
    sleep.assert_called_once_with(1)


def test_pending_checks_have_a_bounded_wait(
    ready: landing.PullRequestStatus, sleep: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(landing, "get_pr_status", Mock(return_value=ready))
    monkeypatch.setattr(
        landing, "pending_required_checks", Mock(return_value=["build"])
    )
    merge = Mock()
    with pytest.raises(landing.LandingError, match="rerun land-all to resume"):
        landing.land_when_ready(PR, "main", merge, wait=0, retries=0)
    sleep.assert_not_called()
    merge.assert_not_called()


@pytest.mark.parametrize("option", ["wait", "retries"])
@pytest.mark.parametrize("in_config", [False, True])
def test_negative_landing_options_rejected(option: str, *, in_config: bool) -> None:
    config = configparser.ConfigParser()
    argv = ["land-all"]
    if in_config:
        config.read_dict({"land-all": {option: "-1"}})
    else:
        argv += [f"--{option}", "-1"]
    with pytest.raises(SystemExit) as exc:
        cli.create_argparser(config).parse_args(argv)
    assert exc.value.code == 2


def test_zero_landing_options_allowed() -> None:
    args = cli.create_argparser(configparser.ConfigParser()).parse_args(
        ["land-all", "--wait", "0", "--retries", "0"]
    )
    assert args.wait == args.retries == 0
