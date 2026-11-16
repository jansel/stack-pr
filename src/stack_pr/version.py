"""Identify the installed distribution without inspecting the working repository."""

import json
import re
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname


def editable_checkout() -> Path | None:
    """Return the source directory recorded by an editable installation."""
    try:
        package = distribution("stack-pr")
    except PackageNotFoundError:
        return None

    direct_url = package.read_text("direct_url.json")
    if not direct_url:
        return None
    metadata = json.loads(direct_url)
    if not metadata.get("dir_info", {}).get("editable"):
        return None

    url = urlsplit(metadata.get("url", ""))
    checkout = Path(url2pathname(url.path))
    if (
        url.scheme != "file"
        or url.netloc not in {"", "localhost"}
        or url.query
        or url.fragment
        or not checkout.is_absolute()
    ):
        raise ValueError("Editable stack-pr metadata must point to a local directory.")
    return checkout


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
