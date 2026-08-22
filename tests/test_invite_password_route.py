"""Regression tests: /j/<code>/password must validate the invite first.

The route only checked that *an* Invitation row with that code existed. An
expired or already-used invite therefore still handed out real accounts on
every media server attached to it, with a caller-supplied username.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db
from app.models import Invitation, MediaServer, User

PASSWORD = "s3cret-password"


@pytest.fixture
def server_id(app, session):
    with app.app_context():
        server = MediaServer(
            name="Jellyfin",
            server_type="jellyfin",
            url="http://localhost:8096",
            api_key="test-key",
        )
        db.session.add(server)
        db.session.commit()
        return server.id


def _make_invitation(app, server_id, code, **kwargs):
    with app.app_context():
        invitation = Invitation(code=code, used=False, unlimited=False, **kwargs)
        invitation.servers.append(db.session.get(MediaServer, server_id))
        db.session.add(invitation)
        db.session.commit()


def _mock_client():
    client = MagicMock()
    client.create_user.return_value = "remote-uid"
    client.get.return_value.json.return_value = {"Policy": {}}
    return client


def _post_password(client, code):
    with patch(
        "app.services.media.service.get_client_for_media_server",
        return_value=_mock_client(),
    ):
        return client.post(
            f"/j/{code}/password",
            data={
                "username": "attacker",
                "password": PASSWORD,
                "confirm": PASSWORD,
            },
        )


def _user_count(app, code):
    with app.app_context():
        return User.query.filter_by(code=code).count()


def test_expired_invitation_is_rejected(app, client, server_id):
    _make_invitation(
        app,
        server_id,
        "EXPIRED1",
        expires=datetime.now(UTC) - timedelta(hours=1),
    )

    response = client.get("/j/EXPIRED1/password")
    assert response.status_code == 200
    assert b"Invalid Invitation" in response.data

    response = _post_password(client, "EXPIRED1")
    assert response.status_code == 200
    assert b"Invalid Invitation" in response.data
    assert _user_count(app, "EXPIRED1") == 0


def test_used_invitation_is_rejected(app, client, server_id):
    _make_invitation(app, server_id, "USEDCODE")
    with app.app_context():
        invitation = Invitation.query.filter_by(code="USEDCODE").one()
        invitation.used = True
        db.session.commit()

    response = client.get("/j/USEDCODE/password")
    assert response.status_code == 200
    assert b"Invalid Invitation" in response.data

    response = _post_password(client, "USEDCODE")
    assert response.status_code == 200
    assert b"Invalid Invitation" in response.data
    assert _user_count(app, "USEDCODE") == 0


def test_valid_invitation_still_renders_the_form(app, client, server_id):
    _make_invitation(
        app,
        server_id,
        "GOODCODE",
        expires=datetime.now(UTC) + timedelta(days=1),
    )

    response = client.get("/j/GOODCODE/password")

    assert response.status_code == 200
    assert b"Choose a password" in response.data
