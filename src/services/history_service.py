"""Lógica de negocio del historial de auditoría (RF-1..RF-6, RNF-1, RNF-2).

Único módulo que sabe construir y leer entradas de `history_entries`
(plan.md sección 2). `record_change`/`record_login_attempt` insertan
dentro de la `session`/transacción que abre el caller (Fases 6-9,
todavía no conectadas). `resolve_entity_exists`/`query_history` NO
reciben `session`: los modelos que consultan (`find_employee_by_id`,
`catalog.find_entry_by_id`, `find_user_by_id`) todavía no lo soportan
(Fase 5).
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClientSession

from src.models import catalog
from src.models.employee import find_employee_by_id
from src.models.history import insert_entry, list_entries
from src.models.user import find_user_by_id
from src.schemas.history import EntityType, HistoryQuery

LoginOutcome = Literal["login_success", "login_failed"]


class EntityTypeRequiredError(Exception):
    """entity_id llegó sin entity_type: no hay forma de saber en qué
    colección buscarlo (plan.md sección 4c)."""

    def __init__(self) -> None:
        super().__init__("entity_type es obligatorio cuando se filtra por entity_id")


class EntityNotFoundError(Exception):
    """No existe una entidad con el entity_id/entity_type indicados (RF-5)."""

    def __init__(self) -> None:
        super().__init__("No existe una entidad con ese entity_id")


def compute_diff(
    current: dict[str, Any], requested: dict[str, Any], fields: list[str]
) -> list[dict[str, Any]]:
    """Compara current vs requested campo a campo, solo sobre `fields`.

    Función pura (plan.md sección 5, decisión 6): sin I/O, reutilizable
    tal cual por employee_service/catalog_service (Fases 6-7). Devuelve
    dicts planos `{"field", "old_value", "new_value"}` (Mongo necesita
    dicts BSON-serializables, no instancias de HistoryChange) solo para
    los campos donde difieren; lista vacía si son idénticos en todos
    los `fields` (no-op).
    """
    return [
        {"field": field, "old_value": current.get(field), "new_value": requested.get(field)}
        for field in fields
        if requested.get(field) != current.get(field)
    ]


async def record_change(
    session: AsyncIOMotorClientSession | None,
    entity_type: EntityType,
    entity_id: Any,
    action: str,
    changes: list[dict[str, Any]],
    actor: dict[str, Any],
    ahora: datetime,
) -> dict[str, Any]:
    """Arma e inserta una entrada de historial dentro de `session`.

    `actor_name` se copia de `actor["full_name"]` en este instante
    (snapshot, plan.md sección 5 decisión 5), nunca queda como
    referencia a resolver después. Devuelve el propio documento armado
    con su `_id` ya seteado (no hace falta releer de Mongo).
    """
    document: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "actor_id": actor.get("_id"),
        "actor_name": actor["full_name"],
        "changes": changes,
        "occurred_at": ahora,
    }
    document["_id"] = await insert_entry(document, session=session)
    return document


async def record_login_attempt(
    session: AsyncIOMotorClientSession | None,
    outcome: LoginOutcome,
    attempted_email: str,
    user: dict[str, Any] | None,
    ahora: datetime,
) -> dict[str, Any]:
    """Variante de record_change para RF-4: sin entidad ni campos
    modificados, solo identidad + resultado del intento de login.

    Si `user` es None, actor_id queda en None y actor_name es el
    correo intentado tal cual.
    """
    actor = user if user is not None else {"_id": None, "full_name": attempted_email}
    return await record_change(session, "login", None, outcome, [], actor, ahora)


async def _find_area(entry_id: Any) -> dict[str, Any] | None:
    return await catalog.find_entry_by_id("areas", entry_id)


async def _find_status(entry_id: Any) -> dict[str, Any] | None:
    return await catalog.find_entry_by_id("estados", entry_id)


_ENTITY_LOOKUPS: dict[str, Callable[[Any], Awaitable[dict[str, Any] | None]]] = {
    "employee": find_employee_by_id,
    "area": _find_area,
    "status": _find_status,
    "user": find_user_by_id,
}


async def resolve_entity_exists(entity_type: EntityType, entity_id: str) -> bool:
    """True si existe una entidad con ese id en la colección de entity_type.

    No aplica a entity_type="login" (las entradas de login nunca
    referencian una entidad): se rechaza con ValueError si se invoca así,
    porque sería un error de uso del propio código, no un caso de
    negocio (query_history ya evita llamarlo para login).

    Un entity_id con formato inválido se trata igual que "no existe"
    (mismo criterio que employee_service._validate_catalog_reference).
    """
    if entity_type == "login":
        raise ValueError('resolve_entity_exists no aplica a entity_type="login"')

    try:
        object_id = ObjectId(entity_id)
    except InvalidId:
        return False

    lookup = _ENTITY_LOOKUPS[entity_type]
    return await lookup(object_id) is not None


def _to_query_value(raw_id: str) -> Any:
    """Convierte un id de filtro (string) al ObjectId guardado en Mongo.

    Si el formato es inválido se devuelve tal cual: nunca matchea un
    ObjectId real, así que el filtro simplemente no encuentra nada.
    """
    try:
        return ObjectId(raw_id)
    except InvalidId:
        return raw_id


async def query_history(filters: HistoryQuery) -> list[dict[str, Any]]:
    """Arma el filtro Mongo dinámico a partir de `filters` y delega en
    models.history.list_entries (plan.md sección 4c)."""
    if filters.entity_id is not None:
        if filters.entity_type is None:
            raise EntityTypeRequiredError()
        if filters.entity_type != "login" and not await resolve_entity_exists(
            filters.entity_type, filters.entity_id
        ):
            raise EntityNotFoundError()

    mongo_query: dict[str, Any] = {}
    if filters.entity_type is not None:
        mongo_query["entity_type"] = filters.entity_type
    if filters.entity_id is not None:
        mongo_query["entity_id"] = _to_query_value(filters.entity_id)
    if filters.actor_id is not None:
        mongo_query["actor_id"] = _to_query_value(filters.actor_id)
    if filters.date_from is not None or filters.date_to is not None:
        date_range: dict[str, datetime] = {}
        if filters.date_from is not None:
            date_range["$gte"] = filters.date_from
        if filters.date_to is not None:
            date_range["$lte"] = filters.date_to
        mongo_query["occurred_at"] = date_range

    return await list_entries(mongo_query)
