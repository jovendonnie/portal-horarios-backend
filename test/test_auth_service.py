import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest

from conftest import mongo_test_session
from src.core.config import settings
from src.core.database import get_database
from src.core.security import hash_password, verify_password
from src.models.user import ensure_indexes, find_user_by_email, insert_user
from src.schemas.user import UserCreate
from src.services import auth_service


def _make_user(email: str, password: str) -> dict[str, Any]:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": hash_password(password),
        "role": "lider",
        "is_active": True,
    }


def test_authenticate_returns_user_on_correct_credentials(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("ana@hispacontact.com", "Secreta123"))

            user = await auth_service.authenticate("ana@hispacontact.com", "Secreta123")

            assert user["email"] == "ana@hispacontact.com"
            assert user["failed_login_attempts"] == 0
            assert user["locked_until"] is None

    asyncio.run(scenario())


def test_authenticate_rejects_wrong_and_missing_email_with_same_generic_message(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("ana@hispacontact.com", "Secreta123"))

            wrong_password_message = None
            missing_email_message = None

            try:
                await auth_service.authenticate("ana@hispacontact.com", "contraseña-mala")
            except auth_service.InvalidCredentialsError as exc:
                wrong_password_message = str(exc)

            try:
                await auth_service.authenticate("no-existe@hispacontact.com", "lo-que-sea")
            except auth_service.InvalidCredentialsError as exc:
                missing_email_message = str(exc)

            assert wrong_password_message is not None
            assert missing_email_message is not None
            assert wrong_password_message == missing_email_message

    asyncio.run(scenario())


def test_authenticate_locks_account_after_n_failed_attempts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("ana@hispacontact.com", "Secreta123"))

            for _ in range(settings.max_failed_attempts - 1):
                with pytest.raises(auth_service.InvalidCredentialsError):
                    await auth_service.authenticate("ana@hispacontact.com", "mala")

            not_yet_locked = await find_user_by_email("ana@hispacontact.com")
            assert not_yet_locked["locked_until"] is None
            assert not_yet_locked["failed_login_attempts"] == settings.max_failed_attempts - 1

            with pytest.raises(auth_service.InvalidCredentialsError):
                await auth_service.authenticate("ana@hispacontact.com", "mala")

            locked = await find_user_by_email("ana@hispacontact.com")
            assert locked["locked_until"] is not None
            assert locked["failed_login_attempts"] == 0

            with pytest.raises(auth_service.AccountLockedError):
                await auth_service.authenticate("ana@hispacontact.com", "Secreta123")

    asyncio.run(scenario())


def test_authenticate_unlocks_after_lockout_minutes_pass(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("ana@hispacontact.com", "Secreta123"))

            frozen_now = datetime(2026, 1, 1, 12, 0, 0)
            with mock.patch.object(auth_service, "_utcnow", return_value=frozen_now):
                for _ in range(settings.max_failed_attempts):
                    with pytest.raises(auth_service.InvalidCredentialsError):
                        await auth_service.authenticate("ana@hispacontact.com", "mala")

            locked = await find_user_by_email("ana@hispacontact.com")
            assert locked["locked_until"] == frozen_now + timedelta(minutes=settings.lockout_minutes)

            still_locked_time = frozen_now + timedelta(minutes=settings.lockout_minutes - 1)
            with mock.patch.object(auth_service, "_utcnow", return_value=still_locked_time):
                with pytest.raises(auth_service.AccountLockedError):
                    await auth_service.authenticate("ana@hispacontact.com", "Secreta123")

            unlocked_time = frozen_now + timedelta(minutes=settings.lockout_minutes + 1)
            with mock.patch.object(auth_service, "_utcnow", return_value=unlocked_time):
                user = await auth_service.authenticate("ana@hispacontact.com", "Secreta123")

            assert user["failed_login_attempts"] == 0
            assert user["locked_until"] is None

    asyncio.run(scenario())


def test_register_user_creates_account_with_temporary_password(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            actor = {"_id": "admin-id", "email": "admin@hispacontact.com", "role": "admin"}
            data = UserCreate(full_name="Ana Pérez", email="ana@hispacontact.com", role="lider")

            result = await auth_service.register_user(actor, data)

            assert result.user["email"] == "ana@hispacontact.com"
            assert result.user["is_active"] is True
            assert result.user["created_by"] == "admin-id"
            assert verify_password(result.temporary_password, result.user["password_hash"])

    asyncio.run(scenario())


def test_register_user_rejects_duplicate_email(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            actor = {"_id": "admin-id"}
            data = UserCreate(full_name="Ana Pérez", email="dup@hispacontact.com", role="lider")

            await auth_service.register_user(actor, data)

            with pytest.raises(auth_service.EmailAlreadyExistsError):
                await auth_service.register_user(actor, data)

            db = get_database()
            count = await db["users"].count_documents({"email": "dup@hispacontact.com"})
            assert count == 1

    asyncio.run(scenario())
