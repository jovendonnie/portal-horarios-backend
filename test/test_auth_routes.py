import asyncio
from typing import Any

from conftest import mongo_test_session

from src.api.routes.auth import login
from src.core.security import hash_password
from src.models.user import insert_user
from src.schemas.auth import LoginRequest


def _make_user(email: str, password: str, role: str) -> dict[str, Any]:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "is_active": True,
    }


def test_login_route_returns_role_of_authenticated_user(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await insert_user(_make_user("ana@hispacontact.com", "Secreta123", "lider"))

            response = await login(
                LoginRequest(email="ana@hispacontact.com", password="Secreta123")
            )

            assert response.role == "lider"
            assert response.session_token

    asyncio.run(scenario())
