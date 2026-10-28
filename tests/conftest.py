from pathlib import Path

import pytest

from stack_pr.shell_commands import run_shell_command


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_shell_command(["git", "init", "-b", "main", repo], quiet=True)
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
            "Initial",
        ],
        cwd=repo,
        quiet=True,
    )
    return repo
