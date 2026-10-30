import asyncio
import inspect

import pytest
from bson import ObjectId
from fastapi import HTTPException, status

from conftest import mongo_test_session
from src.api.deps import require_admin, require_read
from src.api.routes import users
from src.models.user import ensure_indexes, insert_user
from src.schemas.user import UserRoleUpdate

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


# --- Spec 009: cambiar el rol y retirar el acceso (RF-7, RF-8) ---

def test_change_role_and_deactivate_routes_require_admin() -> None:
    assert _actor_dependency(users.change_role_route) is require_admin
    assert _actor_dependency(users.deactivate_user_route) is require_admin


def test_router_registers_the_account_management_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/users/{user_id}"].keys()) >= {"patch"}
    assert set(schema["paths"]["/users/{user_id}/deactivate"].keys()) >= {"patch"}


def test_change_role_route_returns_the_updated_account(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))

            updated = await users.change_role_route(
                str(user_id), UserRoleUpdate(role="gestion_humana"), ACTOR
            )

            assert updated.role == "gestion_humana"
            assert updated.email == "ana@hispacontact.com"

    asyncio.run(scenario())


def test_deactivate_route_returns_the_account_without_access(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("ana@hispacontact.com"))

            updated = await users.deactivate_user_route(str(user_id), ACTOR)

            assert updated.is_active is False

    asyncio.run(scenario())


def test_account_routes_map_unknown_and_malformed_ids_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()

            for user_id in (str(ObjectId()), "no-es-un-object-id"):
                with pytest.raises(HTTPException) as exc_info:
                    await users.change_role_route(user_id, UserRoleUpdate(role="lider"), ACTOR)
                assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

                with pytest.raises(HTTPException) as exc_info:
                    await users.deactivate_user_route(user_id, ACTOR)
                assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    asyncio.run(scenario())


def test_account_routes_map_the_actors_own_account_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            user_id = await insert_user(_make_user("gestion@hispacontact.com"))
            self_actor = {**ACTOR, "_id": user_id}

            with pytest.raises(HTTPException) as exc_info:
                await users.change_role_route(
                    str(user_id), UserRoleUpdate(role="lider"), self_actor
                )
            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

            with pytest.raises(HTTPException) as exc_info:
                await users.deactivate_user_route(str(user_id), self_actor)
            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(scenario())


def test_change_role_route_normalizes_the_legacy_admin_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await ensure_indexes()
            legacy = {**_make_user("legacy@hispacontact.com"), "role": "admin"}
            user_id = await insert_user(legacy)

            # Sin cambio de rol real: el valor guardado sigue siendo "admin" y la
            # respuesta lo canonicaliza igual que GET /users (RF-9).
            unchanged = await users.deactivate_user_route(str(user_id), ACTOR)

            assert unchanged.role == "gestion_humana"

    asyncio.run(scenario())
