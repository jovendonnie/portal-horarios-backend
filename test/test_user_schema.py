import pytest
from pydantic import ValidationError

from src.schemas.user import UserCreate, UserOut


def test_user_out_never_exposes_password_hash() -> None:
    mongo_document = {
        "_id": "66f1000000000000000000aa",
        "full_name": "Ana Pérez",
        "email": "ana.perez@hispacontact.com",
        "password_hash": "pbkdf2_sha256$260000$deadbeef$deadbeef",
        "role": "lider",
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": "2026-09-21T10:00:00Z",
        "created_by": "66f0000000000000000000bb",
    }

    user_out = UserOut(**mongo_document)

    assert "password_hash" not in user_out.model_dump()
    assert user_out.id == "66f1000000000000000000aa"
    assert user_out.email == "ana.perez@hispacontact.com"


def test_user_create_builds_with_valid_role() -> None:
    user_create = UserCreate(full_name="Ana Pérez", email="ana.perez@hispacontact.com", role="lider")

    assert user_create.role == "lider"


def test_user_create_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        UserCreate(full_name="Ana Pérez", email="ana.perez@hispacontact.com", role="superadmin")
