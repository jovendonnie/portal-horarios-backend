from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from src.core.database import start_transaction
from src.models import catalog
from src.services import history_service

_ENTITY_TYPES: dict[str, str] = {"areas": "area", "estados": "status"}

PREDEFINED_STATUS_NAMES: list[str] = [
    "Presencial",
    "Virtual/Casa",
    "Permiso",
    "Vacaciones",
    "Licencia",
    "Incapacidad",
    "Día libre",
]


class InvalidNameError(Exception):
    def __init__(self) -> None:
        super().__init__("El nombre no puede estar vacío ni superar 100 caracteres")


class DuplicateEntryError(Exception):
    def __init__(self, entity_label: str) -> None:
        self.entity_label = entity_label
        super().__init__(f"Ya existe un {entity_label} con ese nombre")


class EntryNotFoundError(Exception):
    def __init__(self, entity_label: str) -> None:
        self.entity_label = entity_label
        super().__init__(f"No existe un {entity_label} con ese id")


class LastEnabledEntryError(Exception):
    def __init__(self, entity_label: str) -> None:
        self.entity_label = entity_label
        super().__init__(
            f"No se puede deshabilitar la última {entity_label} habilitada del catálogo"
        )


def _validate_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed or len(trimmed) > 100:
        raise InvalidNameError()
    return trimmed


async def create_entry(
    collection_name: str, entity_label: str, name: str, actor: dict[str, Any]
) -> dict[str, Any]:
    trimmed = _validate_name(name)

    if await catalog.find_entry_by_name(collection_name, trimmed) is not None:
        raise DuplicateEntryError(entity_label)

    ahora = datetime.now(timezone.utc)
    is_predefined = False if collection_name == "estados" else None

    async with start_transaction() as session:
        try:
            entry_id = await catalog.insert_entry(
                collection_name,
                trimmed,
                actor.get("_id"),
                ahora,
                session=session,
                is_predefined=is_predefined,
            )
            await history_service.record_change(
                session, _ENTITY_TYPES[collection_name], entry_id, "create", [], actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    return await catalog.find_entry_by_id(collection_name, entry_id)


async def seed_predefined_estados(actor: dict[str, Any]) -> list[dict[str, Any]]:
    """Asegura que los 7 Estados predefinidos existan y estén marcados como
    tales, sin duplicar ni alterar los que ya existían por nombre (RF-1,
    RNF-3 de spec 005)."""
    results: list[dict[str, Any]] = []
    for name in PREDEFINED_STATUS_NAMES:
        existing = await catalog.find_entry_by_name("estados", name)
        ahora = datetime.now(timezone.utc)

        if existing is not None:
            if not existing.get("is_predefined", False):
                diffs = [{"field": "is_predefined", "old_value": False, "new_value": True}]
                async with start_transaction() as session:
                    try:
                        await catalog.mark_entry_predefined("estados", existing["_id"], session=session)
                        await history_service.record_change(
                            session, "status", existing["_id"], "update", diffs, actor, ahora
                        )
                        await session.commit_transaction()
                    except Exception:
                        await session.abort_transaction()
                        raise
            results.append(await catalog.find_entry_by_id("estados", existing["_id"]))
        else:
            async with start_transaction() as session:
                try:
                    entry_id = await catalog.insert_entry(
                        "estados", name, actor.get("_id"), ahora, session=session, is_predefined=True
                    )
                    await history_service.record_change(
                        session, "status", entry_id, "create", [], actor, ahora
                    )
                    await session.commit_transaction()
                except Exception:
                    await session.abort_transaction()
                    raise
            results.append(await catalog.find_entry_by_id("estados", entry_id))

    return results


async def list_entries(
    collection_name: str, enabled: bool | None = None
) -> list[dict[str, Any]]:
    return await catalog.list_entries(collection_name, enabled)


async def rename_entry(
    collection_name: str, entity_label: str, entry_id: Any, name: str, actor: dict[str, Any]
) -> dict[str, Any]:
    actual = await catalog.find_entry_by_id(collection_name, entry_id)
    if actual is None:
        raise EntryNotFoundError(entity_label)

    trimmed = _validate_name(name)

    duplicate = await catalog.find_entry_by_name(collection_name, trimmed)
    if duplicate is not None and duplicate["_id"] != entry_id:
        raise DuplicateEntryError(entity_label)

    diffs = history_service.compute_diff({"name": actual["name"]}, {"name": trimmed}, ["name"])
    if not diffs:
        return actual

    ahora = datetime.now(timezone.utc)

    async with start_transaction() as session:
        try:
            await catalog.update_entry_name(
                collection_name, entry_id, trimmed, actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, _ENTITY_TYPES[collection_name], entry_id, "update", diffs, actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    return await catalog.find_entry_by_id(collection_name, entry_id)


async def set_enabled(
    collection_name: str,
    entity_label: str,
    entry_id: Any,
    enabled: bool,
    actor: dict[str, Any],
    count_assigned_fn: Callable[[Any], Awaitable[int]],
) -> tuple[dict[str, Any], int | None]:
    actual = await catalog.find_entry_by_id(collection_name, entry_id)
    if actual is None:
        raise EntryNotFoundError(entity_label)

    if actual["is_enabled"] == enabled:
        return actual, None

    if not enabled and await catalog.count_enabled(collection_name) <= 1:
        raise LastEnabledEntryError(entity_label)

    affected = await count_assigned_fn(entry_id) if not enabled else None
    ahora = datetime.now(timezone.utc)
    action = "disable" if not enabled else "enable"

    async with start_transaction() as session:
        try:
            await catalog.set_entry_enabled(
                collection_name, entry_id, enabled, actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, _ENTITY_TYPES[collection_name], entry_id, action, [], actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    updated = await catalog.find_entry_by_id(collection_name, entry_id)
    return updated, affected
