import json
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import Mock

import pytest

from stack_pr import cli, version


@pytest.mark.parametrize(
    ("installed_version", "direct_url", "expected"),
    [
        ("0.1.dev120+gabcdef0", None, "commit abcdef0"),
        ("0.1.0", {"vcs_info": {"commit_id": "a" * 40}}, "commit " + "a" * 40),
        ("0.1.0", {"dir_info": {"editable": True}}, "commit unknown"),
    ],
)
def test_installed_version(
    installed_version: str,
    direct_url: dict | None,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = Mock(version=installed_version)
    package.read_text.return_value = json.dumps(direct_url) if direct_url else None
    monkeypatch.setattr(version, "distribution", Mock(return_value=package))
    assert installed_version in version.version_string()
    assert expected in version.version_string()


def test_version_without_installed_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(version, "distribution", Mock(side_effect=PackageNotFoundError))
    assert "not installed" in version.version_string()


def test_version_ignores_repository_and_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".stack-pr.cfg").write_text("invalid config")
    monkeypatch.setattr(sys, "argv", ["stack-pr", "--version"])
    monkeypatch.setattr(
        cli, "version_string", lambda: "stack-pr 1.2.3 (commit abcdef0)"
    )
    git = Mock(side_effect=AssertionError("Must not access Git"))
    monkeypatch.setattr(cli, "get_repo_root", git)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "stack-pr 1.2.3 (commit abcdef0)"
    git.assert_not_called()
