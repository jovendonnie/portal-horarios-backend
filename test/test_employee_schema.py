import pytest
from pydantic import ValidationError

from src.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate

SPANISH_KEYS = {
    "nombre_completo",
    "cargo",
    "activo",
    "creado_en",
    "creado_por",
    "actualizado_en",
    "actualizado_por",
    "estado_actualizado_en",
    "estado_actualizado_por",
}


def _make_mongo_document() -> dict:
    return {
        "_id": "66f1000000000000000000aa",
        "nombre_completo": "Carla Gómez",
        "cargo": "lider",
        "area": "Ventas",
        "activo": True,
        "creado_en": "2026-09-21T10:00:00Z",
        "creado_por": "66f0000000000000000000bb",
        "actualizado_en": None,
        "actualizado_por": None,
        "estado_actualizado_en": None,
        "estado_actualizado_por": None,
    }


def _make_employee_out_kwargs() -> dict:
    # area_name/status_name no vienen del documento Mongo (decisión 5 del
    # plan): el service las resuelve aparte y se pasan como kwargs planos.
    return {**_make_mongo_document(), "area_name": "Ventas", "status_name": "Activo"}


def test_employee_out_translates_spanish_document_to_english_attributes() -> None:
    employee_out = EmployeeOut(**_make_employee_out_kwargs())

    assert employee_out.id == "66f1000000000000000000aa"
    assert employee_out.full_name == "Carla Gómez"
    assert employee_out.position == "lider"
    assert employee_out.area == "Ventas"
    assert employee_out.is_active is True
    assert employee_out.created_by == "66f0000000000000000000bb"
    assert employee_out.updated_by is None
    assert employee_out.updated_at is None


def test_employee_out_never_exposes_spanish_keys() -> None:
    employee_out = EmployeeOut(**_make_employee_out_kwargs())

    dumped_keys = set(employee_out.model_dump().keys())

    assert dumped_keys.isdisjoint(SPANISH_KEYS)


def test_employee_out_includes_legacy_area_and_resolved_catalog_fields() -> None:
    document = _make_employee_out_kwargs()
    document["estado_actualizado_en"] = "2026-09-22T08:30:00Z"
    document["estado_actualizado_por"] = "66f0000000000000000000cc"

    employee_out = EmployeeOut(**document)

    assert employee_out.area == "Ventas"  # legado (spec 002), se mantiene
    assert employee_out.area_name == "Ventas"  # nuevo, resuelto (spec 003)
    assert employee_out.status_name == "Activo"  # nuevo, resuelto (spec 003)
    assert employee_out.status_updated_at is not None
    assert employee_out.status_updated_by == "66f0000000000000000000cc"


def test_employee_out_status_updated_fields_default_to_none() -> None:
    employee_out = EmployeeOut(**_make_employee_out_kwargs())

    assert employee_out.status_updated_at is None
    assert employee_out.status_updated_by is None


def test_employee_create_builds_with_area_id_and_status_id() -> None:
    employee_create = EmployeeCreate(
        full_name="Ana Pérez",
        position="recursos_humanos",
        area_id="66f2000000000000000000dd",
        status_id="66f2000000000000000000ee",
    )

    assert employee_create.position == "recursos_humanos"
    assert employee_create.area_id == "66f2000000000000000000dd"
    assert employee_create.status_id == "66f2000000000000000000ee"


def test_employee_create_accepts_practicante_position() -> None:
    employee_create = EmployeeCreate(
        full_name="Ana Pérez",
        position="practicante",
        area_id="66f2000000000000000000dd",
        status_id="66f2000000000000000000ee",
    )

    assert employee_create.position == "practicante"


def test_employee_create_rejects_invalid_position() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            full_name="Ana Pérez",
            position="gerente",
            area_id="66f2000000000000000000dd",
            status_id="66f2000000000000000000ee",
        )


def test_employee_create_requires_status_id() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            full_name="Ana Pérez",
            position="recursos_humanos",
            area_id="66f2000000000000000000dd",
        )


def test_employee_create_requires_area_id() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(
            full_name="Ana Pérez",
            position="recursos_humanos",
            status_id="66f2000000000000000000ee",
        )


def test_employee_update_with_no_arguments_is_valid_and_dumps_empty() -> None:
    employee_update = EmployeeUpdate()

    assert employee_update.model_dump(exclude_unset=True) == {}


def test_employee_update_only_dumps_explicitly_set_fields() -> None:
    employee_update = EmployeeUpdate(area_id="66f2000000000000000000dd")

    assert employee_update.model_dump(exclude_unset=True) == {
        "area_id": "66f2000000000000000000dd"
    }


def test_employee_update_rejects_invalid_position() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(position="gerente")


def test_employee_update_accepts_practicante_position() -> None:
    employee_update = EmployeeUpdate(position="practicante")

    assert employee_update.position == "practicante"
