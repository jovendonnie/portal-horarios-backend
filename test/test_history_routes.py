import asyncio
import inspect
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from conftest import mongo_test_session
from src.api.deps import require_read
from src.api.routes import history
from src.services import history_service

ACTOR = {"_id": ObjectId(), "role": "admin", "full_name": "Admin Actor"}
ACTOR_LIDER = {"_id": ObjectId(), "role": "lider", "full_name": "Líder Actor"}


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def test_history_route_requires_read() -> None:
    assert _actor_dependency(history.list_history_route) is require_read


def test_list_history_route_allows_lider_role(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            entries = await history.list_history_route(
                None, None, None, None, None, ACTOR_LIDER
            )

            assert isinstance(entries, list)

    asyncio.run(scenario())


def test_router_registers_history_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/history"].keys()) >= {"get"}


def test_list_history_route_returns_full_list_without_filters(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            ahora = _ahora()
            await history_service.record_change(
                None, "area", ObjectId(), "create", [], ACTOR, ahora
            )
            await history_service.record_change(
                None, "employee", ObjectId(), "create", [], ACTOR, ahora
            )

            entries = await history.list_history_route(None, None, None, None, None, ACTOR)

            assert len(entries) == 2
            assert {entry.entity_type for entry in entries} == {"area", "employee"}

    asyncio.run(scenario())


def test_list_history_route_with_nonexistent_entity_id_raises_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await history.list_history_route(
                    "employee", str(ObjectId()), None, None, None, ACTOR
                )

            assert exc_info.value.status_code == 404

    asyncio.run(scenario())


def test_list_history_route_with_entity_id_without_entity_type_raises_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            with pytest.raises(HTTPException) as exc_info:
                await history.list_history_route(None, str(ObjectId()), None, None, None, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())
