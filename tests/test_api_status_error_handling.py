"""GET /api/status must not leak internal exception text to API-key holders.

Note: the live /api/status route is actually served by the Flask-RESTX
StatusResource in app/blueprints/api/api_routes.py (api_bp is registered
before status_bp in app/blueprints/__init__.py, and Werkzeug routes to the
first-registered matching rule), so the app.blueprints.api.status.status
view below is unreachable over HTTP. It's still fixed and tested directly
here as defense in depth against that routing shadowing ever changing.
"""

import hashlib
import json
from unittest.mock import patch

from app.blueprints.api.status import status as status_view
from app.extensions import db
from app.models import AdminAccount, ApiKey


def _make_api_key(app, raw_key="status-error-test-key"):
    with app.app_context():
        admin = AdminAccount.query.first()
        if admin is None:
            admin = AdminAccount(username="status-error-admin")
            admin.set_password("Password1")
            db.session.add(admin)
            db.session.commit()

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        existing = ApiKey.query.filter_by(key_hash=key_hash).first()
        if existing is None:
            db.session.add(
                ApiKey(
                    name="status error test key",
                    key_hash=key_hash,
                    created_by_id=admin.id,
                    is_active=True,
                )
            )
            db.session.commit()

    return raw_key


def test_status_view_hides_internal_error_detail(app):
    raw_key = _make_api_key(app)

    with (
        patch("app.blueprints.api.status.User") as mock_user,
        app.test_request_context("/api/status", headers={"X-API-Key": raw_key}),
    ):
        mock_user.query.count.side_effect = RuntimeError("secret detail")
        response, status_code = status_view()

    assert status_code == 500
    text = response.get_data(as_text=True)
    assert "secret detail" not in text
    assert json.loads(text)["error"] == "Internal server error"
