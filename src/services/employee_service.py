"""Lógica de negocio de gestión de empleados (RF-1, RF-2, RF-3, RF-7, RF-8).

CARGOS_VALIDOS y create_employee() son el contrato compartido que debe
reutilizar la carga masiva por Excel (RF-4, otro colaborador) contra la
misma colección `Usuarios` (plan.md sección 5, decisión 7).

A partir de la spec 003, crear/editar un empleado exige además una
referencia válida y habilitada al catálogo de Áreas/Estados (RF-7, RF-8);
el campo legado `area` (texto libre) se sigue escribiendo para no romper
el índice único preexistente y `find_employee_by_identity`, pero su valor
ahora se resuelve siempre desde el catálogo (`area_id`), nunca desde
texto libre de usuario (plan.md sección 4b).
"""

from datetime import datetime, timezone
from typing import Any, get_args

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from src.core.database import start_transaction
from src.models import catalog
from src.models.employee import (
    find_employee_by_id,
    find_employee_by_identity,
    insert_employee,
    list_employees as list_employee_documents,
    update_employee_fields,
    update_employee_status_fields,
)
from src.schemas.employee import EmployeeCreate, EmployeeOut, EmployeePosition, EmployeeUpdate
from src.services import history_service

CARGOS_VALIDOS = set(get_args(EmployeePosition))


class InvalidPositionError(Exception):
    """El Cargo indicado no es uno de los Cargos válidos (RF-1, RF-3)."""

    def __init__(self, position: str) -> None:
        self.position = position
        super().__init__(f"Cargo inválido: {position}")


class InvalidAreaError(Exception):
    """El Área indicada no existe o está deshabilitada (RF-7)."""

    def __init__(self) -> None:
        super().__init__("El Área indicada no existe o está deshabilitada")


class InvalidStatusError(Exception):
    """El Estado indicado no existe o está deshabilitado (RF-8)."""

    def __init__(self) -> None:
        super().__init__("El Estado indicado no existe o está deshabilitado")


class DuplicateEmployeeError(Exception):
    """Ya existe un empleado con el mismo Nombre, Cargo y Área (RF-1, RF-3)."""

    def __init__(self) -> None:
        super().__init__("Ya existe un empleado con ese Nombre, Cargo y Área")


class EmployeeNotFoundError(Exception):
    """No existe un empleado con el id indicado (RF-2, RF-3)."""

    def __init__(self) -> None:
        super().__init__("No existe un empleado con ese id")


_CATALOG_ERRORS: dict[str, type[Exception]] = {
    "areas": InvalidAreaError,
    "estados": InvalidStatusError,
}


def _utcnow() -> datetime:
    """Hora actual en UTC, naive: coincide con el formato en que Motor devuelve los campos de Mongo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_mongo_document(data: EmployeeCreate | EmployeeUpdate) -> dict[str, Any]:
    """Traduce full_name/position a las claves de Mongo.

    area_id (y status_id en EmployeeCreate) se resuelven aparte contra el
    catálogo (_validate_catalog_reference), no se traducen acá tal cual.
    """
    field_translation = {"full_name": "nombre_completo", "position": "cargo"}
    if isinstance(data, EmployeeUpdate):
        provided = data.model_dump(exclude_unset=True, exclude={"area_id"})
    else:
        provided = data.model_dump(exclude={"area_id", "status_id"})
    return {field_translation[key]: value for key, value in provided.items()}


async def _validate_catalog_reference(collection_name: str, entry_id: str | None) -> dict[str, Any]:
    """Valida que entry_id exista y esté habilitado en collection_name.

    No distingue "no existe" de "deshabilitado" ni de "id con formato
    inválido": los tres casos son la misma señal para quien llama (plan.md
    sección 5, decisión 8). Retorna la entrada del catálogo si es válida,
    para que el llamador pueda reutilizar su `name`/`_id` sin otra consulta.
    """
    error_cls = _CATALOG_ERRORS[collection_name]
    if not entry_id:
        raise error_cls()
    try:
        object_id = ObjectId(entry_id)
    except InvalidId as exc:
        raise error_cls() from exc

    entry = await catalog.find_entry_by_id(collection_name, object_id)
    if entry is None or not entry["is_enabled"]:
        raise error_cls()
    return entry


async def _resolve_catalog_names(
    employees: list[dict[str, Any]]
) -> tuple[dict[str, str], dict[str, str]]:
    """Resuelve area_name/status_name con una sola consulta batch por catálogo.

    Los catálogos son pequeños (plan.md sección 5, decisión 5): se trae
    siempre la lista completa de areas/estados (incluidos deshabilitados,
    para no romper la resolución de un empleado ya asignado a una entrada
    deshabilitada — RNF-4), sin importar cuántos `employees` haya ni hacer
    una consulta por empleado.
    """
    area_entries = await catalog.list_entries("areas")
    status_entries = await catalog.list_entries("estados")
    area_names = {str(entry["_id"]): entry["name"] for entry in area_entries}
    status_names = {str(entry["_id"]): entry["name"] for entry in status_entries}
    return area_names, status_names


def _build_employee_out(
    document: dict[str, Any], area_names: dict[str, str], status_names: dict[str, str]
) -> EmployeeOut:
    area_name = area_names.get(str(document.get("area_id")), "")
    status_name = status_names.get(str(document.get("estado_id")), "")
    return EmployeeOut(**document, area_name=area_name, status_name=status_name)


async def _to_employee_out(document: dict[str, Any]) -> EmployeeOut:
    area_names, status_names = await _resolve_catalog_names([document])
    return _build_employee_out(document, area_names, status_names)


async def create_employee(actor: dict[str, Any], data: EmployeeCreate) -> EmployeeOut:
    if data.position not in CARGOS_VALIDOS:
        raise InvalidPositionError(data.position)

    area_entry = await _validate_catalog_reference("areas", data.area_id)
    status_entry = await _validate_catalog_reference("estados", data.status_id)

    fields = _to_mongo_document(data)
    full_name = fields["nombre_completo"].strip()
    position = fields["cargo"]
    area_name = area_entry["name"]

    if await find_employee_by_identity(full_name, position, area_name) is not None:
        raise DuplicateEmployeeError()

    ahora = _utcnow()
    document = {
        "nombre_completo": full_name,
        "cargo": position,
        "area": area_name,
        "area_id": area_entry["_id"],
        "estado_id": status_entry["_id"],
        "estado_actualizado_en": ahora,
        "estado_actualizado_por": actor.get("_id"),
        "creado_en": ahora,
        "creado_por": actor.get("_id"),
    }

    initial_changes = [
        {"field": "full_name", "old_value": None, "new_value": full_name},
        {"field": "position", "old_value": None, "new_value": position},
        {"field": "area", "old_value": None, "new_value": area_name},
    ]

    async with start_transaction() as session:
        try:
            inserted_id = await insert_employee(document, session=session)
            await history_service.record_change(
                session, "employee", inserted_id, "create", initial_changes, actor, ahora
            )
            await history_service.record_change(
                session,
                "employee",
                inserted_id,
                "status_change",
                [{"field": "status", "old_value": None, "new_value": status_entry["name"]}],
                actor,
                ahora,
            )
            await session.commit_transaction()
        except DuplicateKeyError as exc:
            await session.abort_transaction()
            raise DuplicateEmployeeError() from exc
        except Exception:
            await session.abort_transaction()
            raise

    created = await find_employee_by_id(inserted_id)
    assert created is not None
    return await _to_employee_out(created)


async def get_employee(employee_id: Any) -> EmployeeOut:
    document = await find_employee_by_id(employee_id)
    if document is None:
        raise EmployeeNotFoundError()
    return await _to_employee_out(document)


async def list_employees() -> list[EmployeeOut]:
    documents = await list_employee_documents()
    area_names, status_names = await _resolve_catalog_names(documents)
    return [_build_employee_out(document, area_names, status_names) for document in documents]


async def update_employee(
    actor: dict[str, Any], employee_id: Any, changes: EmployeeUpdate
) -> EmployeeOut:
    current = await find_employee_by_id(employee_id)
    if current is None:
        raise EmployeeNotFoundError()

    provided = _to_mongo_document(changes)
    new_full_name = provided.get("nombre_completo", current["nombre_completo"]).strip()
    new_position = provided.get("cargo", current["cargo"])

    if new_position not in CARGOS_VALIDOS:
        raise InvalidPositionError(new_position)

    if changes.area_id is not None:
        area_entry = await _validate_catalog_reference("areas", changes.area_id)
        new_area_name = area_entry["name"]
    else:
        area_entry = None
        new_area_name = current["area"]

    identity_changed = (
        new_full_name != current["nombre_completo"]
        or new_position != current["cargo"]
        or new_area_name != current["area"]
    )
    if identity_changed and await find_employee_by_identity(new_full_name, new_position, new_area_name) is not None:
        raise DuplicateEmployeeError()

    diffs = history_service.compute_diff(
        {
            "full_name": current["nombre_completo"],
            "position": current["cargo"],
            "area": current["area"],
        },
        {"full_name": new_full_name, "position": new_position, "area": new_area_name},
        ["full_name", "position", "area"],
    )
    if not diffs:
        return await _to_employee_out(current)

    ahora = _utcnow()
    updates: dict[str, Any] = {
        "nombre_completo": new_full_name,
        "cargo": new_position,
        "area": new_area_name,
        "actualizado_en": ahora,
        "actualizado_por": actor.get("_id"),
    }
    if area_entry is not None:
        updates["area_id"] = area_entry["_id"]

    async with start_transaction() as session:
        try:
            await update_employee_fields(employee_id, updates, session=session)
            await history_service.record_change(
                session, "employee", employee_id, "update", diffs, actor, ahora
            )
            await session.commit_transaction()
        except DuplicateKeyError as exc:
            await session.abort_transaction()
            raise DuplicateEmployeeError() from exc
        except Exception:
            await session.abort_transaction()
            raise

    updated = await find_employee_by_id(employee_id)
    assert updated is not None
    return await _to_employee_out(updated)


async def update_employee_status(
    employee_id: Any, status_id: str, actor: dict[str, Any], ahora: datetime
) -> EmployeeOut:
    current = await find_employee_by_id(employee_id)
    if current is None:
        raise EmployeeNotFoundError()

    status_entry = await _validate_catalog_reference("estados", status_id)

    old_status_entry = await catalog.find_entry_by_id("estados", current.get("estado_id"))
    old_status_name = old_status_entry["name"] if old_status_entry is not None else None
    changes = [
        {"field": "status", "old_value": old_status_name, "new_value": status_entry["name"]}
    ]

    async with start_transaction() as session:
        try:
            await update_employee_status_fields(
                employee_id, status_entry["_id"], actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, "employee", employee_id, "status_change", changes, actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    updated = await find_employee_by_id(employee_id)
    assert updated is not None
    return await _to_employee_out(updated)
