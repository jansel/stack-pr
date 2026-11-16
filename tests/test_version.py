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
    assert version.editable_checkout() is None


@pytest.mark.parametrize(
    "direct_url",
    [
        None,
        {"url": "https://github.com/jansel/stack-pr", "vcs_info": {"vcs": "git"}},
        {"url": "file:///source/stack-pr", "dir_info": {}},
        {"url": "file:///source/stack-pr", "dir_info": {"editable": False}},
    ],
)
def test_regular_installation_has_no_editable_checkout(
    direct_url: dict | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = Mock()
    package.read_text.return_value = json.dumps(direct_url) if direct_url else None
    monkeypatch.setattr(version, "distribution", Mock(return_value=package))
    assert version.editable_checkout() is None


@pytest.mark.parametrize("authority", ["", "localhost"])
def test_editable_checkout_decodes_file_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, authority: str
) -> None:
    checkout = tmp_path / "editable checkout #1%20"
    url = checkout.as_uri().replace("file://", f"file://{authority}", 1)
    package = Mock()
    package.read_text.return_value = json.dumps(
        {"url": url, "dir_info": {"editable": True}}
    )
    monkeypatch.setattr(version, "distribution", Mock(return_value=package))
    assert version.editable_checkout() == checkout


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://github.com/jansel/stack-pr",
        "file:relative/path",
        "file://other-host/source/stack-pr",
    ],
)
def test_invalid_editable_checkout_is_not_a_regular_installation(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = Mock()
    package.read_text.return_value = json.dumps(
        {"url": url, "dir_info": {"editable": True}}
    )
    monkeypatch.setattr(version, "distribution", Mock(return_value=package))
    with pytest.raises(ValueError, match="local directory"):
        version.editable_checkout()


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
