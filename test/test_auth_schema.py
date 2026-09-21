import pytest
from pydantic import ValidationError

from src.schemas.auth import LoginRequest, LoginResponse


def test_login_request_requires_email() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(password="secret")


def test_login_request_requires_password() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="ana.perez@hispacontact.com")


def test_login_request_builds_with_both_fields() -> None:
    login_request = LoginRequest(email="ana.perez@hispacontact.com", password="secret")

    assert login_request.email == "ana.perez@hispacontact.com"
    assert login_request.password == "secret"


def test_login_response_holds_session_token() -> None:
    login_response = LoginResponse(session_token="tok-abc123")

    assert login_response.session_token == "tok-abc123"
