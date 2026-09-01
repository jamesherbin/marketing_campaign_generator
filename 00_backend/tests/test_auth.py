from unittest.mock import patch

from fastapi import HTTPException

from campaign.auth import require_user


def test_require_user_rejects_missing_session() -> None:
    try:
        require_user(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing authentication was accepted")


@patch("campaign.auth.initialize_firebase", return_value=object())
@patch("campaign.auth.auth.verify_session_cookie")
def test_require_user_uses_verified_firebase_claims(verify_session_cookie, _initialize) -> None:
    verify_session_cookie.return_value = {
        "uid": "firebase-user-123",
        "email": "reviewer@example.com",
        "name": "Reviewer",
        "roles": ["approver", 42],
    }

    user = require_user("FirebaseSession signed-cookie")

    assert user.uid == "firebase-user-123"
    assert user.audit_actor == "reviewer@example.com"
    assert user.roles == ("approver",)
    verify_session_cookie.assert_called_once()
