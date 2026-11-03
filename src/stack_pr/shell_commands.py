from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable
from logging import getLogger
from pathlib import Path
from typing import Any

logger = getLogger(__name__)

ShellCommand = Iterable[str | Path]


def run_shell_command(
    cmd: ShellCommand,
    *,
    quiet: bool,
    check: bool = True,
    **kwargs: Any,  # noqa: ANN401
) -> subprocess.CompletedProcess:
    """Runs a shell command using the arguments provided.

    This is essentially a wrapper around subprocess.run, with more reasonable
    default arguments, and some debug logging.

    The commands are system tools (``git``, ``gh``, and whatever ``git``
    spawns for SSH, such as a ``ProxyCommand``), so they run without the
    ``LD_LIBRARY_PATH`` of the Python environment stack-pr was installed in:
    a conda or virtualenv library directory on it can shadow the libraries
    those tools link, and an SSH proxy that fails to load leaves ``git push``
    with "Could not read from remote repository".  An explicit ``env``
    argument is passed through unchanged.

    Args:
        cmd: shell command to run.
        check: see subprocess.run for semantics.
        **kwargs: see subprocess.run for semantics
            (https://docs.python.org/3/library/subprocess.html#subprocess.run).

    Returns:
        A subprocess.CompletedProcess object.
    """
    if "shell" in kwargs:
        raise ValueError("shell support has been removed")
    cmd = list(map(str, cmd))
    if "env" not in kwargs and "LD_LIBRARY_PATH" in os.environ:
        kwargs["env"] = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
    if quiet and not kwargs.get("capture_output"):
        # If quiet, capture stdout and stderr so they are not printed to the console
        # But respects explicit stderr/stdout settings at the call sites
        if "stderr" not in kwargs:
            kwargs["stderr"] = subprocess.PIPE
        if "stdout" not in kwargs:
            kwargs["stdout"] = subprocess.PIPE
    logger.debug("Running: %s", cmd)
    return subprocess.run(cmd, **kwargs, check=check)


def get_command_output(
    cmd: ShellCommand,
    **kwargs: Any,  # noqa: ANN401
) -> str:
    """A wrapper over run_shell_command that captures stdout into a string.

    Args:
        cmd: shell command to run.
        **kwargs: see run_shell_command for semantics. Passing capture_output is
            not allowed.

    Returns:
        Captured stdout of the command as a string.

    Raises:
        ValueError: if the capture_output keyword argument is specified.
    """
    if "capture_output" in kwargs:
        raise ValueError("Cannot pass capture_output when using get_command_output")
    proc = run_shell_command(cmd, capture_output=True, quiet=False, **kwargs)
    return str(proc.stdout.decode("utf-8").rstrip())
