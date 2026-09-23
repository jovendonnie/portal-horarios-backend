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
    }


def test_employee_out_translates_spanish_document_to_english_attributes() -> None:
    employee_out = EmployeeOut(**_make_mongo_document())

    assert employee_out.id == "66f1000000000000000000aa"
    assert employee_out.full_name == "Carla Gómez"
    assert employee_out.position == "lider"
    assert employee_out.area == "Ventas"
    assert employee_out.is_active is True
    assert employee_out.created_by == "66f0000000000000000000bb"
    assert employee_out.updated_by is None
    assert employee_out.updated_at is None


def test_employee_out_never_exposes_spanish_keys() -> None:
    employee_out = EmployeeOut(**_make_mongo_document())

    dumped_keys = set(employee_out.model_dump().keys())

    assert dumped_keys.isdisjoint(SPANISH_KEYS)


def test_employee_create_builds_with_valid_position() -> None:
    employee_create = EmployeeCreate(full_name="Ana Pérez", position="recursos_humanos", area="RRHH")

    assert employee_create.position == "recursos_humanos"


def test_employee_create_rejects_invalid_position() -> None:
    with pytest.raises(ValidationError):
        EmployeeCreate(full_name="Ana Pérez", position="gerente", area="RRHH")


def test_employee_update_with_no_arguments_is_valid_and_dumps_empty() -> None:
    employee_update = EmployeeUpdate()

    assert employee_update.model_dump(exclude_unset=True) == {}


def test_employee_update_only_dumps_explicitly_set_fields() -> None:
    employee_update = EmployeeUpdate(area="Marketing")

    assert employee_update.model_dump(exclude_unset=True) == {"area": "Marketing"}


def test_employee_update_rejects_invalid_position() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdate(position="gerente")
