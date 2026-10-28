# Development

This is Jason Ansel's private fork of [modular/stack-pr](https://github.com/modular/stack-pr).
File fork-specific issues and pull requests in [jansel/stack-pr](https://github.com/jansel/stack-pr).

Use Python 3.10 or newer and an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade -e '.[dev]'
```

Run the checks used by CI:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest
python -m build
```

The test suite uses temporary Git repositories and mocked GitHub commands;
it does not submit or merge real PRs. The build uses `pdm-backend` to derive
the version from Git history; the PDM CLI is not required.

This fork is installed from GitHub. CI builds packages for validation and
does not publish releases to PyPI.
