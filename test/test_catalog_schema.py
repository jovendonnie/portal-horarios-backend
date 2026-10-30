import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.schemas.area import AreaCreate, AreaOut, AreaUpdate
from src.schemas.estado import EstadoCreate, EstadoOut, EstadoUpdate

CATALOG_SCHEMAS = [
    (AreaCreate, AreaUpdate, AreaOut),
    (EstadoCreate, EstadoUpdate, EstadoOut),
]


def _make_document() -> dict:
    return {
        "_id": ObjectId(),
        "name": "Ventas",
        "is_enabled": True,
        "created_at": "2026-09-24T10:00:00Z",
        "created_by": ObjectId(),
        "updated_at": None,
        "updated_by": None,
    }


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_create_rejects_empty_name(create_cls, update_cls, out_cls) -> None:
    with pytest.raises(ValidationError):
        create_cls(name="")


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_create_rejects_name_longer_than_100_chars(create_cls, update_cls, out_cls) -> None:
    with pytest.raises(ValidationError):
        create_cls(name="x" * 101)


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_create_accepts_valid_name(create_cls, update_cls, out_cls) -> None:
    entry = create_cls(name="Ventas")

    assert entry.name == "Ventas"


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_update_rejects_empty_name(create_cls, update_cls, out_cls) -> None:
    with pytest.raises(ValidationError):
        update_cls(name="")


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_update_rejects_name_longer_than_100_chars(create_cls, update_cls, out_cls) -> None:
    with pytest.raises(ValidationError):
        update_cls(name="x" * 101)


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_update_accepts_valid_name(create_cls, update_cls, out_cls) -> None:
    entry = update_cls(name="Comercial")

    assert entry.name == "Comercial"


@pytest.mark.parametrize("create_cls,update_cls,out_cls", CATALOG_SCHEMAS)
def test_out_stringifies_object_ids_from_mongo_document(create_cls, update_cls, out_cls) -> None:
    document = _make_document()

    entry_out = out_cls(**document)

    assert entry_out.id == str(document["_id"])
    assert entry_out.name == "Ventas"
    assert entry_out.is_enabled is True
    assert entry_out.created_by == str(document["created_by"])
    assert entry_out.updated_at is None
    assert entry_out.updated_by is None


def test_estado_out_exposes_same_field_names_as_area_out_plus_its_own() -> None:
    """Spec 005: EstadoOut gana `is_predefined`. Spec 009: gana `blocks_shifts`.
    Ambos son exclusivos de Estados (RNF-2 de 005, RF-5 de 009)."""
    assert set(EstadoOut.model_fields) == set(AreaOut.model_fields) | {
        "is_predefined",
        "blocks_shifts",
    }


def test_estado_out_defaults_blocks_shifts_to_false_when_missing_from_document() -> None:
    """Un Estado creado antes de la spec 009 no tiene la clave: se lee sin migrar (RNF-6)."""
    document = _make_document()

    entry_out = EstadoOut(**document)

    assert entry_out.blocks_shifts is False


def test_estado_out_respects_blocks_shifts_true_from_document() -> None:
    document = _make_document()
    document["blocks_shifts"] = True

    entry_out = EstadoOut(**document)

    assert entry_out.blocks_shifts is True


def test_estado_create_defaults_blocks_shifts_to_false() -> None:
    assert EstadoCreate(name="Comisión").blocks_shifts is False


def test_estado_create_accepts_blocks_shifts_true() -> None:
    assert EstadoCreate(name="Licencia", blocks_shifts=True).blocks_shifts is True


def test_estado_out_defaults_is_predefined_to_false_when_missing_from_document() -> None:
    document = _make_document()

    entry_out = EstadoOut(**document)

    assert entry_out.is_predefined is False


def test_estado_out_respects_is_predefined_true_from_document() -> None:
    document = _make_document()
    document["is_predefined"] = True

    entry_out = EstadoOut(**document)

    assert entry_out.is_predefined is True
