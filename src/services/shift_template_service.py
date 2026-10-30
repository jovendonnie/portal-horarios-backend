"""Lógica de negocio del catálogo de Plantillas de turno (spec 009, RF-2).

Las validaciones de forma del payload (al menos un día y un bloque, hora de
fin posterior al inicio, bloques sin solape, días sin repetir) viven en
`src/schemas/shift_template.py` y se traducen en 422. Acá queda lo que
necesita la base: unicidad del nombre y la escritura del dato junto a su
entrada de auditoría en una sola transacción.
"""

from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from src.core.database import start_transaction
from src.models import shift_template
from src.schemas.shift_template import ShiftTemplateCreate, ShiftTemplateUpdate
from src.services import history_service

ENTITY_LABEL = "Plantilla de turno"


class InvalidNameError(Exception):
    def __init__(self) -> None:
        super().__init__("El nombre no puede estar vacío ni superar 100 caracteres")


class DuplicateTemplateError(Exception):
    def __init__(self) -> None:
        super().__init__(f"Ya existe una {ENTITY_LABEL} con ese nombre")


class TemplateNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__(f"No existe una {ENTITY_LABEL} con ese id")


def _validate_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed or len(trimmed) > 100:
        raise InvalidNameError()
    return trimmed


def _to_documents(data: ShiftTemplateCreate | ShiftTemplateUpdate) -> tuple[list[dict[str, str]], list[str]]:
    blocks = [{"start": block.start, "end": block.end} for block in data.blocks]
    return blocks, list(data.weekdays)


async def create_template(data: ShiftTemplateCreate, actor: dict[str, Any]) -> dict[str, Any]:
    trimmed = _validate_name(data.name)

    if await shift_template.find_template_by_name(trimmed) is not None:
        raise DuplicateTemplateError()

    blocks, weekdays = _to_documents(data)
    ahora = datetime.now(timezone.utc)

    async with start_transaction() as session:
        try:
            template_id = await shift_template.insert_template(
                trimmed, blocks, weekdays, actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, "shift_template", template_id, "create", [], actor, ahora
            )
            await session.commit_transaction()
        except DuplicateKeyError as exc:
            await session.abort_transaction()
            raise DuplicateTemplateError() from exc
        except Exception:
            await session.abort_transaction()
            raise

    return await shift_template.find_template_by_id(template_id)


async def list_templates() -> list[dict[str, Any]]:
    return await shift_template.list_templates()


async def update_template(
    template_id: Any, data: ShiftTemplateUpdate, actor: dict[str, Any]
) -> dict[str, Any]:
    actual = await shift_template.find_template_by_id(template_id)
    if actual is None:
        raise TemplateNotFoundError()

    trimmed = _validate_name(data.name)

    duplicate = await shift_template.find_template_by_name(trimmed)
    if duplicate is not None and duplicate["_id"] != template_id:
        raise DuplicateTemplateError()

    blocks, weekdays = _to_documents(data)
    diffs = history_service.compute_diff(
        {"name": actual["name"], "blocks": actual["blocks"], "weekdays": actual["weekdays"]},
        {"name": trimmed, "blocks": blocks, "weekdays": weekdays},
        ["name", "blocks", "weekdays"],
    )
    if not diffs:
        return actual

    ahora = datetime.now(timezone.utc)

    async with start_transaction() as session:
        try:
            await shift_template.update_template(
                template_id, trimmed, blocks, weekdays, actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, "shift_template", template_id, "update", diffs, actor, ahora
            )
            await session.commit_transaction()
        except DuplicateKeyError as exc:
            await session.abort_transaction()
            raise DuplicateTemplateError() from exc
        except Exception:
            await session.abort_transaction()
            raise

    return await shift_template.find_template_by_id(template_id)
