import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from stack_pr import cli, version
from stack_pr.shell_commands import get_command_output, run_shell_command


@pytest.fixture(autouse=True)
def installed_package(monkeypatch: pytest.MonkeyPatch) -> Mock:
    package = Mock(version="0.1.0")
    package.read_text.return_value = None
    monkeypatch.setattr(version, "distribution", Mock(return_value=package))
    return package


@pytest.mark.parametrize("returncode", [0, 1, 23])
@pytest.mark.parametrize("editable", [False, True])
def test_upgrade_uses_current_python_without_repo_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    returncode: int,
    installed_package: Mock,
    *,
    editable: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    # Even a broken local config must not prevent repairing an installation.
    config = tmp_path / ".stack-pr.cfg"
    config.write_text("invalid configuration")
    monkeypatch.setenv("STACKPR_CONFIG", str(config))
    monkeypatch.setattr(sys, "argv", ["stack-pr", "upgrade"])
    run = Mock(return_value=subprocess.CompletedProcess([], returncode))
    monkeypatch.setattr(cli, "run_shell_command", run)
    checkout = tmp_path / "source checkout"
    if editable:
        installed_package.read_text.return_value = json.dumps(
            {"url": checkout.as_uri(), "dir_info": {"editable": True}}
        )

    def unexpected_repo_access() -> None:
        pytest.fail("Upgrade must not inspect the working directory or GitHub CLI")

    monkeypatch.setattr(cli, "get_repo_root", unexpected_repo_access)
    monkeypatch.setattr(cli, "check_gh_installed", unexpected_repo_access)
    if returncode:
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == returncode
    else:
        cli.main()
    if editable:
        expected = [
            "git",
            "-C",
            str(checkout),
            "pull",
            "--ff-only",
            "--no-rebase",
            "--no-autostash",
        ]
    else:
        expected = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "git+https://github.com/jansel/stack-pr.git@main",
        ]
    run.assert_called_once_with(expected, quiet=False, check=False)
    output = capsys.readouterr().out
    assert ("stack-pr is up to date." in output) == (returncode == 0)
    assert ("Resolve the Git error" in output) == (editable and returncode != 0)


def test_invalid_editable_metadata_does_not_install(
    installed_package: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed_package.read_text.return_value = json.dumps(
        {"dir_info": {"editable": True}}
    )
    run = Mock()
    monkeypatch.setattr(cli, "run_shell_command", run)
    monkeypatch.setattr(sys, "argv", ["stack-pr", "upgrade"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    run.assert_not_called()


def commit(repo: Path, message: str) -> str:
    run_shell_command(
        [
            "git",
            "-C",
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-am",
            message,
        ],
        quiet=True,
    )
    return get_command_output(["git", "rev-parse", "HEAD"], cwd=repo)


@pytest.fixture
def editable_repo(
    git_repo: Path, installed_package: Mock, monkeypatch: pytest.MonkeyPatch
) -> Path:
    for filename in ("local.txt", "upstream.txt"):
        (git_repo / filename).write_text("original\n")
    run_shell_command(["git", "add", "."], cwd=git_repo, quiet=True)
    commit(git_repo, "Add files")
    run_shell_command(["git", "branch", "-m", "development"], cwd=git_repo, quiet=True)
    checkout = git_repo.parent / "editable checkout #1%20"
    run_shell_command(["git", "clone", git_repo, checkout], quiet=True)
    for key, value in (
        ("pull.rebase", "true"),
        ("pull.ff", "false"),
        ("merge.autoStash", "true"),
        ("rebase.autoStash", "true"),
    ):
        run_shell_command(["git", "config", key, value], cwd=checkout, quiet=True)
    installed_package.read_text.return_value = json.dumps(
        {"url": checkout.as_uri(), "dir_info": {"editable": True}}
    )
    (git_repo / "upstream.txt").write_text("updated upstream\n")
    commit(git_repo, "Upstream update")

    def git_only(
        command: list[str], *, quiet: bool, check: bool
    ) -> subprocess.CompletedProcess:
        assert command[0] == "git", "An editable upgrade must never run pip"
        return run_shell_command(command, quiet=quiet, check=check)

    monkeypatch.setattr(cli, "run_shell_command", git_only)
    # Run from a different repository with a broken config.
    monkeypatch.chdir(git_repo)
    config = git_repo / ".stack-pr.cfg"
    config.write_text("invalid configuration")
    monkeypatch.setenv("STACKPR_CONFIG", str(config))
    monkeypatch.setattr(sys, "argv", ["stack-pr", "upgrade"])
    return checkout


def test_editable_upgrade_fast_forwards_and_preserves_edits(
    git_repo: Path, editable_repo: Path
) -> None:
    (editable_repo / "local.txt").write_text("staged\n")
    run_shell_command(["git", "add", "local.txt"], cwd=editable_repo, quiet=True)
    (editable_repo / "local.txt").write_text("unstaged\n")
    (editable_repo / "untracked.txt").write_text("untracked\n")
    cli.main()
    assert get_command_output(["git", "rev-parse", "HEAD"], cwd=editable_repo) == (
        get_command_output(["git", "rev-parse", "HEAD"], cwd=git_repo)
    )
    assert (editable_repo / "upstream.txt").read_text() == "updated upstream\n"
    assert (editable_repo / "local.txt").read_text() == "unstaged\n"
    assert (editable_repo / "untracked.txt").read_text() == "untracked\n"
    assert (
        get_command_output(["git", "show", ":local.txt"], cwd=editable_repo) == "staged"
    )
    assert get_command_output(
        ["git", "branch", "--show-current"], cwd=editable_repo
    ) == ("development")
    assert not get_command_output(["git", "stash", "list"], cwd=editable_repo)


@pytest.mark.parametrize("failure", ["diverged", "conflicting edits", "no upstream"])
def test_failed_editable_upgrade_preserves_work(
    editable_repo: Path, failure: str, capsys: pytest.CaptureFixture[str]
) -> None:
    if failure == "diverged":
        (editable_repo / "local.txt").write_text("local commit\n")
        commit(editable_repo, "Local change")
    elif failure == "conflicting edits":
        (editable_repo / "upstream.txt").write_text("local edit\n")
    else:
        run_shell_command(
            ["git", "branch", "--unset-upstream"], cwd=editable_repo, quiet=True
        )
    (editable_repo / "local.txt").write_text("staged\n")
    run_shell_command(["git", "add", "local.txt"], cwd=editable_repo, quiet=True)
    (editable_repo / "local.txt").write_text("unstaged\n")
    (editable_repo / "untracked.txt").write_text("untracked\n")
    head = get_command_output(["git", "rev-parse", "HEAD"], cwd=editable_repo)
    diff = get_command_output(["git", "diff", "HEAD"], cwd=editable_repo)

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code != 0
    assert get_command_output(["git", "rev-parse", "HEAD"], cwd=editable_repo) == head
    assert get_command_output(["git", "diff", "HEAD"], cwd=editable_repo) == diff
    assert (
        get_command_output(["git", "show", ":local.txt"], cwd=editable_repo) == "staged"
    )
    assert (editable_repo / "untracked.txt").read_text() == "untracked\n"
    assert not get_command_output(["git", "stash", "list"], cwd=editable_repo)
    assert "Resolve the Git error" in capsys.readouterr().out


@pytest.mark.parametrize("args", [["upgrade", "--help"], ["upgrade", "--invalid"]])
def test_upgrade_help_and_invalid_options_do_not_install(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["stack-pr", *args])
    upgrade = Mock()
    monkeypatch.setattr(cli, "command_upgrade", upgrade)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == (0 if "--help" in args else 2)
    upgrade.assert_not_called()
