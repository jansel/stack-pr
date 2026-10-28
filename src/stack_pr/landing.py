"""Wait for required checks and a confirmed GitHub merge."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from subprocess import CalledProcessError

from stack_pr.shell_commands import get_command_output, run_shell_command


class LandingError(RuntimeError):
    """A landing failure that needs user action before retrying."""


@dataclass
class PullRequestStatus:
    state: str
    head: str
    base: str
    mergeable: str
    merge_state: str
    review: str
    draft: bool
    auto_merge: bool


def get_pr_status(pr: str) -> PullRequestStatus:
    data = json.loads(
        get_command_output(
            [
                "gh",
                "pr",
                "view",
                pr,
                "--json",
                (
                    "state,headRefOid,baseRefName,mergeable,mergeStateStatus,"
                    "reviewDecision,isDraft,autoMergeRequest"
                ),
            ]
        )
    )
    return PullRequestStatus(
        state=data["state"],
        head=data["headRefOid"],
        base=data["baseRefName"],
        mergeable=data["mergeable"],
        merge_state=data["mergeStateStatus"],
        review=data["reviewDecision"] or "",
        draft=data["isDraft"],
        auto_merge=data["autoMergeRequest"] is not None,
    )


def pending_required_checks(pr: str) -> list[str]:
    command = ["gh", "pr", "checks", pr, "--required", "--json", "name,bucket,link"]
    result = run_shell_command(command, quiet=True, check=False)
    # gh uses exit 1 for failed checks and exit 8 for pending checks, while
    # still returning structured JSON. Empty stdout usually means an API error.
    if not result.stdout.strip():
        if result.returncode == 1 and b"no checks reported" in result.stderr.lower():
            return []
        raise CalledProcessError(
            result.returncode or 1, command, result.stdout, result.stderr
        )
    if result.returncode not in {0, 1, 8}:
        raise CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    checks = json.loads(result.stdout)
    if any(
        check["bucket"] not in {"pass", "skipping", "pending", "fail", "cancel"}
        for check in checks
    ):
        raise LandingError(f"Unrecognized required check status for {pr}.")
    failed = [
        f"{check['name']} ({check['link']})"
        for check in checks
        if check["bucket"] in {"fail", "cancel"}
    ]
    if failed:
        raise LandingError(f"Required checks failed for {pr}: " + ", ".join(failed))
    return [check["name"] for check in checks if check["bucket"] == "pending"]


def check_landing_blockers(pr: str, status: PullRequestStatus, target: str) -> None:
    if status.state != "OPEN":
        raise LandingError(f"Cannot land {pr}: PR is {status.state}.")
    if status.mergeable == "CONFLICTING" or status.merge_state == "DIRTY":
        raise LandingError(
            f"Merge conflicts in {pr}. Resolve them locally and submit again; not retrying."
        )
    if status.base != target:
        raise LandingError(
            f"Cannot land {pr}: expected base {target}, got {status.base}."
        )
    if status.draft:
        raise LandingError(f"Cannot land draft PR {pr}. Mark it ready first.")
    if status.review in {"REVIEW_REQUIRED", "CHANGES_REQUESTED"}:
        raise LandingError(f"Cannot land {pr}: required review is {status.review}.")
    if status.merge_state == "BEHIND":
        raise LandingError(
            f"{pr} is behind {target}. Rebase and submit before retrying."
        )


def transient_merge_error(exc: CalledProcessError) -> bool:
    output = (exc.stderr or b"").decode("utf-8", errors="replace")
    return bool(
        re.search(
            r"HTTP (?:429|5\d\d)\b|timed? out|connection reset|temporary failure|unexpected EOF",
            output,
            re.IGNORECASE,
        )
    )


def request_merge(
    pr: str, target: str, head: str, merge: Callable[[str], None]
) -> bool:
    try:
        merge(head)
    except CalledProcessError as exc:
        latest = get_pr_status(pr)
        if latest.state == "MERGED":
            return True
        check_landing_blockers(pr, latest, target)
        # Only retry known transport failures; conflicts and permission errors
        # require user action, even if GitHub's mergeability data is stale.
        if not transient_merge_error(exc):
            raise
        return False
    else:
        return True


def land_when_ready(
    pr: str, target: str, merge: Callable[[str], None], *, wait: int, retries: int
) -> None:
    """Poll checks, request a merge once ready, and wait until GitHub confirms it."""
    if wait < 0 or retries < 0:
        raise ValueError("wait and retries must be nonnegative")
    requested = False
    for attempt in range(retries + 1):
        status = get_pr_status(pr)
        if status.state == "MERGED":
            return
        check_landing_blockers(pr, status, target)
        pending = pending_required_checks(pr)
        requested = requested or status.auto_merge
        if pending:
            reason = "Waiting for required checks: " + ", ".join(pending)
        elif status.mergeable == "UNKNOWN" or status.merge_state in {
            "UNKNOWN",
            "BLOCKED",
        }:
            reason = "Waiting for GitHub to report merge readiness"
        elif requested:
            reason = "Waiting for GitHub to finish merging"
        else:
            requested = request_merge(pr, target, status.head, merge)
            latest = get_pr_status(pr)
            if latest.state == "MERGED":
                return
            check_landing_blockers(pr, latest, target)
            reason = (
                "Waiting for GitHub to finish merging"
                if requested
                else "Retrying a temporary GitHub error"
            )
        if attempt == retries:
            raise LandingError(
                f"{reason}: {pr}. Stopped after {retries + 1} checks; "
                "rerun land-all to resume, or increase --retries."
            )
        print(f"{reason}: {pr}; checking again in {wait}s.", flush=True)
        time.sleep(wait)
