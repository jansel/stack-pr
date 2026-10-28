"""Identify the installed distribution without inspecting the working repository."""

import json
import re
from importlib.metadata import PackageNotFoundError, distribution


def version_string() -> str:
    try:
        package = distribution("stack-pr")
    except PackageNotFoundError:
        return "stack-pr (version unknown; package is not installed)"

    commit = None
    direct_url = package.read_text("direct_url.json")
    if direct_url:
        commit = json.loads(direct_url).get("vcs_info", {}).get("commit_id")
    if not commit:
        match = re.search(r"\+g([0-9a-f]+)", package.version)
        if match:
            commit = match.group(1)
    return f"stack-pr {package.version} (commit {commit or 'unknown'})"
