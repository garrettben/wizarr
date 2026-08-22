"""App-wide CSRF protection tests.

The rest of the suite runs with ``WTF_CSRF_ENABLED = False``; this module spins
up a dedicated application with CSRF turned on so the real protection can be
exercised end to end.
"""

import contextlib
import hashlib
import os
import re
import tempfile

import pytest

from app import create_app
from app.blueprints.api import api_bp, status_bp
from app.extensions import csrf, db
from app.models import AdminAccount, ApiKey
from tests.conftest import TestConfig

_CSRF_DB_PATH = os.path.join(tempfile.gettempdir(), "wizarr_csrf_test.db")

_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')


class CSRFTestConfig(TestConfig):
    """TestConfig, but with CSRF protection actually switched on."""

    WTF_CSRF_ENABLED = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_CSRF_DB_PATH}"


def _remove_db_files():
    for ext in ("", "-wal", "-shm"):
        with contextlib.suppress(OSError):
            os.unlink(_CSRF_DB_PATH + ext)


@pytest.fixture(scope="module")
def csrf_app():
    _remove_db_files()
    application = create_app(CSRFTestConfig)  # type: ignore[arg-type]
    with application.app_context():
        db.create_all()
        admin = AdminAccount(username="csrfadmin")
        admin.set_password("Password1")
        db.session.add(admin)
        db.session.commit()
    yield application
    with application.app_context():
        db.drop_all()
    _remove_db_files()


@pytest.fixture
def anon_client(csrf_app):
    return csrf_app.test_client()


@pytest.fixture
def admin_client(csrf_app):
    """A logged-in admin client.

    The login POST is itself CSRF protected, so the token is scraped from the
    rendered login page first.
    """
    client = csrf_app.test_client()
    page = client.get("/login").get_data(as_text=True)
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page)
    assert match, "login page must render a csrf_token input"
    resp = client.post(
        "/login",
        data={
            "username": "csrfadmin",
            "password": "Password1",
            "csrf_token": match.group(1),
        },
    )
    assert resp.status_code in {302, 303}
    return client


def _admin_page(client):
    resp = client.get("/settings/")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_state_changing_post_without_token_is_rejected(admin_client):
    """A POST with a valid session but no CSRF token must be refused."""
    resp = admin_client.post("/settings/scan-libraries")
    assert resp.status_code == 400


def test_state_changing_post_with_header_token_is_accepted(admin_client):
    """The same POST carrying X-CSRFToken must reach the view."""
    token = _META_RE.search(_admin_page(admin_client))
    assert token, "admin base layout must expose the csrf-token meta tag"

    resp = admin_client.post(
        "/settings/scan-libraries",
        headers={"X-CSRFToken": token.group(1)},
    )
    assert resp.status_code != 400


def test_api_blueprints_are_csrf_exempt(csrf_app, anon_client):
    """Token-authenticated API blueprints must not require a CSRF token."""
    assert api_bp in csrf._exempt_blueprints
    assert status_bp in csrf._exempt_blueprints

    raw_key = "csrf_test_api_key"
    with csrf_app.app_context():
        admin = AdminAccount.query.filter_by(username="csrfadmin").first()
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        if not ApiKey.query.filter_by(key_hash=key_hash).first():
            db.session.add(
                ApiKey(
                    name="csrf test key",
                    key_hash=key_hash,
                    created_by_id=admin.id,
                    is_active=True,
                )
            )
            db.session.commit()

    # No CSRF token at all — the request must be handled by the view (404 for a
    # missing user), not blocked with a 400 by CSRFProtect.
    resp = anon_client.delete("/api/users/999999", headers={"X-API-Key": raw_key})
    assert resp.status_code == 404


def test_base_layout_exposes_token_to_htmx(admin_client):
    """base.html must publish the token as meta tag and as HTMX headers."""
    html = _admin_page(admin_client)
    assert _META_RE.search(html)
    assert "X-CSRFToken" in html
    assert "hx-headers" in html


def test_session_authenticated_api_endpoint_still_requires_token(admin_client):
    """The one /api endpoint that accepts a session cookie keeps CSRF on.

    ``/api/users/<id>/reset-password`` is decorated with
    ``require_api_key_or_session``. The blueprint exemption would otherwise let a
    cross-site request ride the admin's cookie, so the check is re-applied for
    the cookie path.
    """
    resp = admin_client.post("/api/users/999999/reset-password")
    assert resp.status_code == 400

    token = _META_RE.search(_admin_page(admin_client))
    assert token
    resp = admin_client.post(
        "/api/users/999999/reset-password",
        headers={"X-CSRFToken": token.group(1)},
    )
    assert resp.status_code == 404
