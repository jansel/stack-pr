import configparser
import json
from subprocess import CalledProcessError
from unittest.mock import Mock

import pytest

from stack_pr import cli


def entry(sha: str, title: str, pr: str | None = None) -> cli.StackEntry:
    return cli.StackEntry(cli.CommitHeader(f"{sha}\n    {title}"), _pr=pr)


OPEN_PRS = [
    {
        "number": 41,
        "title": "Add the thing",
        "url": "https://github.com/jansel/example/pull/41",
        "headRefName": "jansel/stack/7",
    },
    {
        "number": 42,
        "title": "Unrelated work",
        "url": "https://github.com/jansel/example/pull/42",
        "headRefName": "jansel/stack/8",
    },
]


def test_finds_open_prs_with_the_title_of_a_commit_without_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = Mock(return_value=json.dumps(OPEN_PRS))
    monkeypatch.setattr(cli, "get_command_output", output)
    lost = entry("a" * 40, "Add the thing")
    new = entry("b" * 40, "Add the thing, take two")  # titles must match exactly
    submitted = entry(
        "c" * 40, "Unrelated work", "https://github.com/jansel/example/pull/42"
    )
    duplicates = cli.find_duplicate_prs([lost, new, submitted])
    assert [(e, pr["number"]) for e, pr in duplicates] == [(lost, 41)]
    assert output.call_args.args[0][:6] == [
        "gh",
        "pr",
        "list",
        "--author",
        "@me",
        "--state",
    ]


def test_no_lookup_when_every_commit_has_a_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    output = Mock()
    monkeypatch.setattr(cli, "get_command_output", output)
    pr = "https://github.com/jansel/example/pull/41"
    assert cli.find_duplicate_prs([entry("a" * 40, "Add the thing", pr)]) == []
    output.assert_not_called()


def test_check_exits_with_the_metadata_to_restore(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "get_command_output", lambda cmd: json.dumps(OPEN_PRS))
    with pytest.raises(SystemExit) as info:
        cli.check_no_duplicate_prs([entry("a" * 40, "Add the thing")])
    assert info.value.code == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "Refusing to submit" in text
    assert (
        "stack-info: PR: https://github.com/jansel/example/pull/41, "
        "branch: jansel/stack/7"
    ) in text
    assert "--allow-duplicates" in text


def test_a_failed_lookup_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(cmd: list[str]) -> str:
        raise CalledProcessError(1, cmd)

    monkeypatch.setattr(cli, "get_command_output", fail)
    with pytest.raises(CalledProcessError):
        cli.find_duplicate_prs([entry("a" * 40, "Add the thing")])
    out = capsys.readouterr()
    assert "--allow-duplicates" in out.out + out.err


@pytest.mark.parametrize("allow", [False, True])
def test_submit_checks_before_pushing(
    monkeypatch: pytest.MonkeyPatch, *, allow: bool
) -> None:
    stack = [entry("a" * 40, "Add the thing")]
    monkeypatch.setattr(cli, "is_rebase_in_progress", lambda: False)
    monkeypatch.setattr(cli, "get_current_branch_name", lambda: "dev")
    monkeypatch.setattr(cli, "should_update_local_base", lambda **kwargs: False)
    monkeypatch.setattr(cli, "get_stack", lambda **kwargs: stack)
    checked = Mock(side_effect=SystemExit(1))
    monkeypatch.setattr(cli, "check_no_duplicate_prs", checked)

    class PushedError(Exception):
        pass

    def init_local_branches(*args: object, **kwargs: object) -> None:
        raise PushedError

    monkeypatch.setattr(cli, "init_local_branches", init_local_branches)
    args = cli.CommonArgs(
        "main", "HEAD", "origin", "main", False, False, "$USERNAME/stack", False, False
    )
    expected = PushedError if allow else SystemExit
    with pytest.raises(expected):
        cli.command_submit(
            args, draft=False, reviewer="", keep_body=True, allow_duplicates=allow
        )
    assert checked.called is not allow


def test_allow_duplicates_flag() -> None:
    parser = cli.create_argparser(configparser.ConfigParser())
    assert parser.parse_args(["submit", "--allow-duplicates"]).allow_duplicates
    assert not parser.parse_args(["submit"]).allow_duplicates
