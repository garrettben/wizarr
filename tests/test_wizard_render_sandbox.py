"""Tests that the anonymous wizard neither leaks secrets nor executes code.

The wizard is served to anonymous invitees (``wizard_bp.before_request``) and
its step content comes from the database / the admin import route.  Two
guarantees are covered here:

* ``_settings()`` exposes an allowlist of public keys, so a step cannot read
  ``{{ settings.admin_password }}``.
* ``_render()`` renders through a Jinja sandbox, so a step cannot walk the
  class hierarchy out of the template.
"""

import frontmatter
import pytest

from app.blueprints.wizard.routes import (
    WIZARD_SETTINGS_ALLOWLIST,
    _get_server_context,
    _render,
    _settings,
)
from app.extensions import db
from app.models import MediaServer, Settings

ADMIN_PASSWORD_HASH = "scrypt:32768:8:1$notarealhash$deadbeef"
OMBI_API_KEY = "ombi-secret-key"
SERVER_NAME = "Catbird Media"

SECRET_KEYS = ("admin_password", "ombi_api_key")


def _post(markdown: str):
    return frontmatter.loads(markdown)


@pytest.fixture
def wizard_ctx(app):
    """Seed a secret-bearing Settings table plus one MediaServer."""
    with app.app_context():
        for key, value in (
            ("admin_password", ADMIN_PASSWORD_HASH),
            ("ombi_api_key", OMBI_API_KEY),
            ("overseerr_url", "https://requests.example.com"),
        ):
            row = Settings.query.filter_by(key=key).first() or Settings()
            row.key = key
            row.value = value
            db.session.add(row)

        server = MediaServer()
        server.name = SERVER_NAME
        server.server_type = "jellyfin"
        server.url = "https://jf.internal.example.com"
        server.external_url = "https://jf.example.com"
        db.session.add(server)
        db.session.commit()
        server_id = server.id

        yield

        # Remove only what this fixture created – the test database is shared.
        MediaServer.query.filter_by(id=server_id).delete(synchronize_session=False)
        Settings.query.filter(
            Settings.key.in_(["admin_password", "ombi_api_key", "overseerr_url"])
        ).delete(synchronize_session=False)
        db.session.commit()


def test_allowlist_excludes_secret_keys():
    for key in SECRET_KEYS:
        assert key not in WIZARD_SETTINGS_ALLOWLIST
    assert not any(
        key.endswith(("_api_key", "_token", "_secret", "_password"))
        for key in WIZARD_SETTINGS_ALLOWLIST
    )


def test_settings_context_omits_secrets(app, wizard_ctx):
    with app.app_context():
        cfg = _settings()
        for key in SECRET_KEYS:
            assert key not in cfg


def test_step_cannot_read_admin_password(app, wizard_ctx):
    with app.app_context():
        cfg = _settings()
        html = _render(_post("pw=[{{ settings.admin_password }}]"), cfg)
        assert ADMIN_PASSWORD_HASH not in html
        assert "pw=[]" in html


def test_step_cannot_read_ombi_api_key(app, wizard_ctx):
    with app.app_context():
        cfg = _settings()
        html = _render(_post("key=[{{ settings.ombi_api_key }}]"), cfg)
        assert OMBI_API_KEY not in html


def test_step_can_still_read_allowlisted_server_name(app, wizard_ctx):
    with app.app_context():
        cfg = _settings()
        html = _render(_post("Welcome to {{ settings.server_name }}!"), cfg)
        assert SERVER_NAME in html


def test_step_cannot_escape_the_sandbox(app, wizard_ctx):
    with app.app_context():
        cfg = _settings()
        html = _render(_post("{{ ''.__class__.__mro__[1].__subclasses__() }}"), cfg)
        assert "<class" not in html
        assert "subprocess" not in html


def test_step_cannot_reach_flask_config(app, wizard_ctx):
    with app.app_context():
        cfg = _settings()
        html = _render(_post("secret=[{{ config.SECRET_KEY }}]"), cfg)
        assert app.config["SECRET_KEY"] not in html


def test_shipped_wizard_step_still_renders(app, wizard_ctx):
    """A real shipped markdown step must survive the sandbox unchanged."""
    from app.blueprints.wizard.routes import BASE_DIR

    post = frontmatter.load(str(BASE_DIR / "jellyfin" / "02_download.md"))
    with app.app_context():
        cfg = _settings()
        html = _render(
            post,
            cfg | {"_": (lambda s: s)} | _get_server_context("jellyfin"),
            server_type="jellyfin",
        )
        assert "alert-error" not in html
        assert "Jellyfin" in html
