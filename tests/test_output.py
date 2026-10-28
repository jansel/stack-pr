import re

import pytest

from stack_pr.cli import CommitHeader, StackEntry, print_stack


def visible_text(text: str) -> str:
    # Remove OSC 8 hyperlinks as well as ANSI colors, just like a terminal.
    text = re.sub(r"\x1b\]8;;.*?\x1b\\", "", text)
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def make_entry(number: int | None) -> StackEntry:
    entry = StackEntry(CommitHeader("abcdef123456\n    Improve the workflow"))
    if number is not None:
        entry.pr = f"https://github.com/jansel/stack-pr/pull/{number}"
        entry.head = f"jansel/stack/{number}"
        entry.base = "main"
    return entry


@pytest.mark.parametrize("links", [False, True])
def test_pr_url_is_visible_on_its_own_line(*, links: bool) -> None:
    entry = make_entry(123)
    text = entry.pprint(links=links)
    lines = visible_text(text).splitlines()
    assert len(lines) == 2
    assert "abcdef12" in lines[0]
    assert "#123" in lines[0]
    assert "Improve the workflow" in lines[0]
    assert "'jansel/stack/123' -> 'main'" in lines[0]
    assert lines[1].strip() == entry.pr
    assert ("\x1b]8;;" in text) == links
    assert entry.pr in visible_text(repr(entry))


def test_unsubmitted_entry() -> None:
    text = visible_text(make_entry(None).pprint(links=True))
    assert "no PR" in text
    assert "Improve the workflow" in text
    assert "https://" not in text
    assert "\n" not in text


@pytest.mark.parametrize("links", [False, True])
def test_stack_urls_are_indented_and_in_stack_order(
    capsys: pytest.CaptureFixture[str], *, links: bool
) -> None:
    oldest, newest = make_entry(123), make_entry(124)
    print_stack([oldest, newest], links=links)
    lines = visible_text(capsys.readouterr().out).splitlines()
    assert lines[0] == "Stack:"
    assert "#124" in lines[1]
    assert lines[2] == f"         {newest.pr}"
    assert "#123" in lines[3]
    assert lines[4] == f"         {oldest.pr}"
