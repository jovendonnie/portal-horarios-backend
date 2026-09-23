"""Lógica de negocio de gestión de empleados (RF-1, RF-2, RF-3).

CARGOS_VALIDOS y create_employee() son el contrato compartido que debe
reutilizar la carga masiva por Excel (RF-4, otro colaborador) contra la
misma colección `Usuarios` (plan.md sección 5, decisión 7).
"""

from datetime import datetime, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from src.models.employee import (
    find_employee_by_id,
    find_employee_by_identity,
    insert_employee,
    list_employees as list_employee_documents,
    update_employee_fields,
)
from src.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate

CARGOS_VALIDOS = {"recursos_humanos", "lider"}


class InvalidPositionError(Exception):
    """El Cargo indicado no es uno de los Cargos válidos (RF-1, RF-3)."""

    def __init__(self, position: str) -> None:
        self.position = position
        super().__init__(f"Cargo inválido: {position}")


class DuplicateEmployeeError(Exception):
    """Ya existe un empleado con el mismo Nombre, Cargo y Área (RF-1, RF-3)."""

    def __init__(self) -> None:
        super().__init__("Ya existe un empleado con ese Nombre, Cargo y Área")


class EmployeeNotFoundError(Exception):
    """No existe un empleado con el id indicado (RF-2, RF-3)."""

    def __init__(self) -> None:
        super().__init__("No existe un empleado con ese id")


def _utcnow() -> datetime:
    """Hora actual en UTC, naive: coincide con el formato en que Motor devuelve los campos de Mongo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_employee_out(document: dict[str, Any]) -> EmployeeOut:
    return EmployeeOut(**document)


def _to_mongo_document(data: EmployeeCreate | EmployeeUpdate) -> dict[str, Any]:
    field_translation = {"full_name": "nombre_completo", "position": "cargo", "area": "area"}
    provided = data.model_dump(exclude_unset=True) if isinstance(data, EmployeeUpdate) else data.model_dump()
    return {field_translation[key]: value for key, value in provided.items()}


async def create_employee(actor: dict[str, Any], data: EmployeeCreate) -> EmployeeOut:
    if data.position not in CARGOS_VALIDOS:
        raise InvalidPositionError(data.position)

    fields = _to_mongo_document(data)
    full_name = fields["nombre_completo"].strip()
    area = fields["area"].strip()
    position = fields["cargo"]

    if await find_employee_by_identity(full_name, position, area) is not None:
        raise DuplicateEmployeeError()

    document = {
        "nombre_completo": full_name,
        "cargo": position,
        "area": area,
        "creado_en": _utcnow(),
        "creado_por": actor.get("_id"),
    }

    try:
        inserted_id = await insert_employee(document)
    except DuplicateKeyError as exc:
        raise DuplicateEmployeeError() from exc

    created = await find_employee_by_id(inserted_id)
    assert created is not None
    return _to_employee_out(created)


async def get_employee(employee_id: Any) -> EmployeeOut:
    document = await find_employee_by_id(employee_id)
    if document is None:
        raise EmployeeNotFoundError()
    return _to_employee_out(document)


async def list_employees() -> list[EmployeeOut]:
    documents = await list_employee_documents()
    return [_to_employee_out(document) for document in documents]


async def update_employee(
    actor: dict[str, Any], employee_id: Any, changes: EmployeeUpdate
) -> EmployeeOut:
    current = await find_employee_by_id(employee_id)
    if current is None:
        raise EmployeeNotFoundError()

    provided = _to_mongo_document(changes)
    new_full_name = provided.get("nombre_completo", current["nombre_completo"]).strip()
    new_position = provided.get("cargo", current["cargo"])
    new_area = provided.get("area", current["area"]).strip()

    if new_position not in CARGOS_VALIDOS:
        raise InvalidPositionError(new_position)

    identity_changed = (
        new_full_name != current["nombre_completo"]
        or new_position != current["cargo"]
        or new_area != current["area"]
    )
    if identity_changed and await find_employee_by_identity(new_full_name, new_position, new_area) is not None:
        raise DuplicateEmployeeError()

    updates = {
        "nombre_completo": new_full_name,
        "cargo": new_position,
        "area": new_area,
        "actualizado_en": _utcnow(),
        "actualizado_por": actor.get("_id"),
    }

    try:
        await update_employee_fields(employee_id, updates)
    except DuplicateKeyError as exc:
        raise DuplicateEmployeeError() from exc

    updated = await find_employee_by_id(employee_id)
    assert updated is not None
    return _to_employee_out(updated)
