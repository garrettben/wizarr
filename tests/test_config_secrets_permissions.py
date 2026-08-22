"""secrets.json must not be world/group readable: it holds SECRET_KEY."""

import stat
from unittest.mock import patch

from app.config import save_secrets


def test_save_secrets_writes_file_with_owner_only_permissions(tmp_path):
    secrets_file = tmp_path / "secrets.json"

    with (
        patch("app.config.SECRETS_FILE", secrets_file),
        patch("app.config.DATABASE_DIR", tmp_path),
    ):
        save_secrets({"SECRET_KEY": "does-not-matter"})

    mode = stat.S_IMODE(secrets_file.stat().st_mode)
    assert mode == 0o600


def test_save_secrets_tightens_permissions_on_preexisting_file(tmp_path):
    """A file that pre-existed with looser permissions (e.g. created before
    this fix shipped) must be tightened on the next write, not just left
    alone because it already exists."""
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text("{}")
    secrets_file.chmod(0o644)

    with (
        patch("app.config.SECRETS_FILE", secrets_file),
        patch("app.config.DATABASE_DIR", tmp_path),
    ):
        save_secrets({"SECRET_KEY": "does-not-matter"})

    mode = stat.S_IMODE(secrets_file.stat().st_mode)
    assert mode == 0o600
