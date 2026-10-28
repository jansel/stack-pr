import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from stack_pr import cli


@pytest.mark.parametrize("returncode", [0, 1, 23])
def test_upgrade_uses_current_python_without_repo_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    returncode: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    # Even a broken local config must not prevent repairing an installation.
    config = tmp_path / ".stack-pr.cfg"
    config.write_text("invalid configuration")
    monkeypatch.setenv("STACKPR_CONFIG", str(config))
    monkeypatch.setattr(sys, "argv", ["stack-pr", "upgrade"])
    run = Mock(return_value=subprocess.CompletedProcess([], returncode))
    monkeypatch.setattr(cli, "run_shell_command", run)

    def unexpected_repo_access() -> None:
        pytest.fail("Upgrade must not inspect the repository or GitHub CLI")

    monkeypatch.setattr(cli, "get_repo_root", unexpected_repo_access)
    monkeypatch.setattr(cli, "check_gh_installed", unexpected_repo_access)
    if returncode:
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == returncode
    else:
        cli.main()
    run.assert_called_once_with(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "git+https://github.com/jansel/stack-pr.git@main",
        ],
        quiet=False,
        check=False,
    )
    assert ("stack-pr is up to date." in capsys.readouterr().out) == (returncode == 0)


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
