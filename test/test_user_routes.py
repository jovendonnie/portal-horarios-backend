import asyncio
import inspect

from bson import ObjectId

from conftest import mongo_test_session
from src.api.deps import require_admin, require_read
from src.api.routes import users
from src.models.user import ensure_indexes, insert_user

ACTOR = {"_id": ObjectId(), "role": "gestion_humana", "full_name": "Gestión Humana Actor"}
ACTOR_LIDER = {"_id": ObjectId(), "role": "lider", "full_name": "Líder Actor"}


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def _make_user(email: str) -> dict:
    return {
        "full_name": "Ana Pérez",
        "email": email,
        "password_hash": "pbkdf2_sha256$260000$deadbeef$deadbeef",
        "role": "lider",
        "is_active": True,
    }


def test_create_user_route_requires_admin() -> None:
    assert _actor_dependency(users.create_user) is require_admin


def test_list_users_route_requires_read() -> None:
    assert _actor_dependency(users.list_users_route) is require_read


def test_router_registers_user_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/users"].keys()) >= {"get", "post"}


def test_list_users_route_allows_lider_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            result = await users.list_users_route(ACTOR_LIDER)

            assert isinstance(result, list)

    asyncio.run(scenario())


def test_list_users_route_returns_all_accounts(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("ruta-a@hispacontact.com"))
            await insert_user(_make_user("ruta-b@hispacontact.com"))

            result = await users.list_users_route(ACTOR)

            assert {user.email for user in result} == {
                "ruta-a@hispacontact.com",
                "ruta-b@hispacontact.com",
            }

    asyncio.run(scenario())


def test_list_users_route_excludes_password_hash(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            await insert_user(_make_user("ana@hispacontact.com"))

            result = await users.list_users_route(ACTOR)

            assert len(result) == 1
            assert "password_hash" not in result[0].model_dump()

    asyncio.run(scenario())
