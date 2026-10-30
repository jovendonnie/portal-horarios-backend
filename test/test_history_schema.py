from datetime import datetime, timezone

import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.schemas.history import HistoryChange, HistoryEntryOut, HistoryQuery


def _make_entry_document(**overrides) -> dict:
    document = {
        "_id": ObjectId(),
        "entity_type": "employee",
        "entity_id": ObjectId(),
        "action": "update",
        "actor_id": ObjectId(),
        "actor_name": "Ana Torres",
        "changes": [
            {"field": "full_name", "old_value": "Carla Gomez", "new_value": "Carla G."}
        ],
        "occurred_at": datetime.now(timezone.utc),
    }
    document.update(overrides)
    return document


def test_history_entry_out_validates_plan_example_document() -> None:
    document = _make_entry_document()

    entry = HistoryEntryOut(**document)

    assert entry.id == str(document["_id"])
    assert entry.entity_type == "employee"
    assert entry.entity_id == str(document["entity_id"])
    assert entry.action == "update"
    assert entry.actor_id == str(document["actor_id"])
    assert entry.actor_name == "Ana Torres"
    assert entry.changes == [
        HistoryChange(field="full_name", old_value="Carla Gomez", new_value="Carla G.")
    ]


def test_history_entry_out_accepts_login_failed_with_null_entity_and_actor() -> None:
    document = _make_entry_document(
        entity_type="login",
        entity_id=None,
        action="login_failed",
        actor_id=None,
        actor_name="correo-no-registrado@example.com",
        changes=[],
    )

    entry = HistoryEntryOut(**document)

    assert entry.entity_id is None
    assert entry.actor_id is None
    assert entry.actor_name == "correo-no-registrado@example.com"
    assert entry.changes == []


def test_history_entry_out_accepts_login_success_with_actor() -> None:
    actor_id = ObjectId()
    document = _make_entry_document(
        entity_type="login",
        entity_id=None,
        action="login_success",
        actor_id=actor_id,
        actor_name="Ana Torres",
        changes=[],
    )

    entry = HistoryEntryOut(**document)

    assert entry.entity_id is None
    assert entry.actor_id == str(actor_id)
    assert entry.changes == []


def test_history_entry_out_rejects_entity_type_outside_literal() -> None:
    document = _make_entry_document(entity_type="invalid_type")

    with pytest.raises(ValidationError):
        HistoryEntryOut(**document)


@pytest.mark.parametrize(
    "entity_type", ["employee", "area", "status", "user", "login"]
)
def test_history_entry_out_accepts_all_known_entity_types(entity_type: str) -> None:
    document = _make_entry_document(entity_type=entity_type)

    entry = HistoryEntryOut(**document)

    assert entry.entity_type == entity_type


def test_history_entry_out_converts_real_bson_object_ids_to_str() -> None:
    document = _make_entry_document()

    entry = HistoryEntryOut(**document)

    assert isinstance(entry.id, str)
    assert isinstance(entry.entity_id, str)
    assert isinstance(entry.actor_id, str)


def test_history_change_standalone_validates_minimal_fields() -> None:
    change = HistoryChange(field="full_name", old_value=None, new_value="Carla Gomez")

    assert change.field == "full_name"
    assert change.old_value is None
    assert change.new_value == "Carla Gomez"


def test_history_query_with_no_arguments_is_valid() -> None:
    query = HistoryQuery()

    assert query.entity_type is None
    assert query.entity_id is None
    assert query.actor_id is None
    assert query.date_from is None
    assert query.date_to is None


@pytest.mark.parametrize(
    "filters",
    [
        {"entity_type": "employee"},
        {"actor_id": str(ObjectId()), "date_from": datetime.now(timezone.utc)},
        {
            "entity_id": str(ObjectId()),
            "date_from": datetime.now(timezone.utc),
            "date_to": datetime.now(timezone.utc),
        },
    ],
)
def test_history_query_accepts_partial_filter_combinations(filters: dict) -> None:
    query = HistoryQuery(**filters)

    for field, value in filters.items():
        assert getattr(query, field) == value

    for field in {"entity_type", "entity_id", "actor_id", "date_from", "date_to"} - filters.keys():
        assert getattr(query, field) is None


def test_history_query_rejects_entity_type_outside_literal() -> None:
    with pytest.raises(ValidationError):
        HistoryQuery(entity_type="invalid_type")


def test_entity_type_includes_the_configuration_catalogs() -> None:
    """Spec 009, RNF-2: sin estos valores, GET /history falla al serializar las
    entradas de Cargos, Plantillas de turno y Festivos."""
    from typing import get_args

    from src.schemas.history import EntityType

    assert {"position", "shift_template", "holiday"} <= set(get_args(EntityType))
