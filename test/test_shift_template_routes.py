import asyncio
import inspect

import pytest
from bson import ObjectId
from fastapi import HTTPException, status

from conftest import mongo_test_session
from src.api.deps import require_admin, require_read
from src.api.routes import shift_templates
from src.models import shift_template
from src.schemas.shift_template import ShiftTemplateCreate, ShiftTemplateUpdate

ACTOR = {"_id": ObjectId(), "role": "gestion_humana", "full_name": "Admin Actor"}

VALID = {
    "name": "Mañana",
    "blocks": [{"start": "08:00", "end": "17:00"}],
    "weekdays": ["monday", "tuesday"],
}


def _actor_dependency(route_function):
    signature = inspect.signature(route_function)
    param_name = "actor" if "actor" in signature.parameters else "_actor"
    return signature.parameters[param_name].default.dependency


def test_routes_require_the_expected_roles() -> None:
    assert _actor_dependency(shift_templates.create_template_route) is require_admin
    assert _actor_dependency(shift_templates.list_templates_route) is require_read
    assert _actor_dependency(shift_templates.update_template_route) is require_admin


def test_router_registers_shift_template_routes() -> None:
    from src.main import app

    schema = app.openapi()

    assert set(schema["paths"]["/shift-templates"].keys()) >= {"post", "get"}
    assert set(schema["paths"]["/shift-templates/{template_id}"].keys()) >= {"patch"}


def test_create_returns_201_and_the_stored_template(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()

            created = await shift_templates.create_template_route(
                ShiftTemplateCreate(**VALID), ACTOR
            )

            assert created.name == "Mañana"
            assert [block.start for block in created.blocks] == ["08:00"]
            status_code = next(
                route.status_code
                for route in shift_templates.router.routes
                if route.endpoint is shift_templates.create_template_route
            )
            assert status_code == status.HTTP_201_CREATED

    asyncio.run(scenario())


def test_list_and_update_return_the_current_templates(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            created = await shift_templates.create_template_route(
                ShiftTemplateCreate(**VALID), ACTOR
            )

            updated = await shift_templates.update_template_route(
                created.id, ShiftTemplateUpdate(**{**VALID, "name": "Tarde"}), ACTOR
            )
            assert updated.name == "Tarde"

            listed = await shift_templates.list_templates_route(ACTOR)
            assert [entry.name for entry in listed] == ["Tarde"]

    asyncio.run(scenario())


def test_create_maps_duplicate_to_409(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            await shift_templates.create_template_route(ShiftTemplateCreate(**VALID), ACTOR)

            with pytest.raises(HTTPException) as exc_info:
                await shift_templates.create_template_route(ShiftTemplateCreate(**VALID), ACTOR)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    asyncio.run(scenario())


def test_update_maps_unknown_and_malformed_ids_to_404(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()

            for template_id in (str(ObjectId()), "no-es-un-object-id"):
                with pytest.raises(HTTPException) as exc_info:
                    await shift_templates.update_template_route(
                        template_id, ShiftTemplateUpdate(**VALID), ACTOR
                    )
                assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    asyncio.run(scenario())


def test_create_maps_blank_name_to_422(use_test_db) -> None:
    async def scenario() -> None:
        async with mongo_test_session():
            await shift_template.ensure_indexes()
            blank = ShiftTemplateCreate.model_construct(
                name="   ",
                blocks=ShiftTemplateCreate(**VALID).blocks,
                weekdays=["monday"],
            )

            with pytest.raises(HTTPException) as exc_info:
                await shift_templates.create_template_route(blank, ACTOR)

            assert exc_info.value.status_code == 422

    asyncio.run(scenario())
