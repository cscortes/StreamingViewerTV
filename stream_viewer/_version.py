"""Single source of truth for the app version.

Bump this alongside buglist.md entries: patch digit for BUG-XXX fixes,
minor digit for FEAT-XXX features, per semver. pyproject.toml reads its
version from here (see [tool.hatch.version]) so there's only one place
to edit.
"""

__version__ = "0.3.6"
