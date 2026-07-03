"""Nox sessions for celeri_builder."""

from __future__ import annotations

import nox

nox.needs_version = ">=2024.3.2"
nox.options.default_venv_backend = "uv|virtualenv"
nox.options.sessions = ["lint", "tests"]


@nox.session
def lint(session: nox.Session) -> None:
    """Run the linter suite (pre-commit)."""
    session.install("pre-commit")
    session.run(
        "pre-commit", "run", "--all-files", "--show-diff-on-failure", *session.posargs
    )


@nox.session
def tests(session: nox.Session) -> None:
    """Run the fast unit/engine test suite."""
    session.install("-e", ".[test]")
    session.run("pytest", *session.posargs)


@nox.session
def build(session: nox.Session) -> None:
    """Build sdist and wheel."""
    session.install("build")
    session.run("python", "-m", "build")
