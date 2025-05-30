import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

import pytest

from stack_pr.cli import (
    generate_available_branch_name,
    generate_branch_name,
    get_branch_id,
    get_gh_username,
    get_taken_branch_ids,
)
from stack_pr.git import git_config


@pytest.fixture(scope="module")
def username() -> str:
    git_config.set_username_override("TestBot")
    return get_gh_username()


@pytest.mark.parametrize(
    ("template", "branch_name", "expected"),
    [
        ("feature-$ID-desc", "feature-123-desc", "123"),
        ("$USERNAME/stack/$ID", "{username}/stack/99", "99"),
        ("$USERNAME/stack/$ID", "refs/remote/origin/{username}/stack/99", "99"),
    ],
)
def test_get_branch_id(
    username: str, template: str, branch_name: str, expected: str
) -> None:
    branch_name = branch_name.format(username=username)
    assert get_branch_id(template, branch_name) == expected


@pytest.mark.parametrize(
    ("template", "branch_name"),
    [
        ("feature/$ID/desc", "feature/abc/desc"),
        ("feature/$ID/desc", "wrong/format"),
        ("$USERNAME/stack/$ID", "{username}/main/99"),
    ],
)
def test_get_branch_id_no_match(username: str, template: str, branch_name: str) -> None:
    branch_name = branch_name.format(username=username)
    assert get_branch_id(template, branch_name) is None


def test_generate_branch_name() -> None:
    template = "feature/$ID/description"
    assert generate_branch_name(template, 123) == "feature/123/description"


def test_get_taken_branch_ids() -> None:
    template = "$USERNAME/stack/$ID"
    refs = [
        "refs/remotes/origin/TestBot/stack/104",
        "refs/remotes/origin/TestBot/stack/105",
        "refs/remotes/origin/TestBot/stack/134",
    ]
    assert get_taken_branch_ids(refs, template) == [104, 105, 134]
    refs = ["TestBot/stack/104", "TestBot/stack/105", "TestBot/stack/134"]
    assert get_taken_branch_ids(refs, template) == [104, 105, 134]
    refs = [
        "TestBot/stack/104",
        "AAAA/stack/105",
        "TestBot/stack/134",
        "TestBot/stack/bbb",
    ]
    assert get_taken_branch_ids(refs, template) == [104, 134]


def test_generate_available_branch_name() -> None:
    template = "$USERNAME/stack/$ID"
    refs = [
        "refs/remotes/origin/TestBot/stack/104",
        "refs/remotes/origin/TestBot/stack/105",
        "refs/remotes/origin/TestBot/stack/134",
    ]
    assert generate_available_branch_name(refs, template) == "TestBot/stack/135"
    refs = []
    assert generate_available_branch_name(refs, template) == "TestBot/stack/1"
    template = "$USERNAME-stack-$ID"
    refs = [
        "refs/remotes/origin/TestBot-stack-104",
        "refs/remotes/origin/TestBot-stack-105",
        "refs/remotes/origin/TestBot-stack-134",
    ]
    assert generate_available_branch_name(refs, template) == "TestBot-stack-135"
