import pytest
from bson import ObjectId
from pydantic import ValidationError

from src.schemas.shift_template import (
    ShiftTemplateCreate,
    ShiftTemplateOut,
    ShiftTemplateUpdate,
)

VALID = {
    "name": "Mañana",
    "blocks": [{"start": "08:00", "end": "17:00"}],
    "weekdays": ["monday", "tuesday"],
}


def _make_document() -> dict:
    return {
        "_id": ObjectId(),
        "name": "Mañana",
        "blocks": [{"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "18:00"}],
        "weekdays": ["monday", "friday"],
        "created_at": "2026-10-30T10:00:00Z",
        "created_by": ObjectId(),
        "updated_at": None,
        "updated_by": None,
    }


@pytest.mark.parametrize("create_cls", [ShiftTemplateCreate, ShiftTemplateUpdate])
def test_accepts_valid_template(create_cls) -> None:
    template = create_cls(**VALID)

    assert template.name == "Mañana"
    assert template.blocks[0].start == "08:00"
    assert template.weekdays == ["monday", "tuesday"]


@pytest.mark.parametrize("create_cls", [ShiftTemplateCreate, ShiftTemplateUpdate])
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"name": ""}, id="nombre-vacio"),
        pytest.param({"name": "x" * 101}, id="nombre-muy-largo"),
        pytest.param({"blocks": []}, id="sin-bloques"),
        pytest.param({"weekdays": []}, id="sin-dias"),
        pytest.param({"weekdays": ["monday", "monday"]}, id="dia-repetido"),
        pytest.param({"weekdays": ["saturday"]}, id="fin-de-semana"),
        pytest.param({"blocks": [{"start": "17:00", "end": "08:00"}]}, id="fin-antes-del-inicio"),
        pytest.param({"blocks": [{"start": "08:00", "end": "08:00"}]}, id="fin-igual-al-inicio"),
        pytest.param({"blocks": [{"start": "8:00", "end": "17:00"}]}, id="hora-sin-formato"),
        pytest.param(
            {"blocks": [{"start": "08:00", "end": "13:00"}, {"start": "12:00", "end": "18:00"}]},
            id="bloques-solapados",
        ),
    ],
)
def test_rejects_invalid_template(create_cls, overrides) -> None:
    with pytest.raises(ValidationError):
        create_cls(**{**VALID, **overrides})


@pytest.mark.parametrize("create_cls", [ShiftTemplateCreate, ShiftTemplateUpdate])
def test_accepts_split_shift_with_adjacent_blocks(create_cls) -> None:
    """Dos bloques que se tocan en el límite no se solapan: 12:00 cierra uno y abre el otro."""
    template = create_cls(
        **{**VALID, "blocks": [{"start": "08:00", "end": "12:00"}, {"start": "12:00", "end": "18:00"}]}
    )

    assert len(template.blocks) == 2


@pytest.mark.parametrize("create_cls", [ShiftTemplateCreate, ShiftTemplateUpdate])
def test_detects_overlap_regardless_of_block_order(create_cls) -> None:
    with pytest.raises(ValidationError):
        create_cls(
            **{
                **VALID,
                "blocks": [{"start": "12:00", "end": "18:00"}, {"start": "08:00", "end": "13:00"}],
            }
        )


def test_out_stringifies_object_ids_from_mongo_document() -> None:
    document = _make_document()

    template_out = ShiftTemplateOut(**document)

    assert template_out.id == str(document["_id"])
    assert template_out.created_by == str(document["created_by"])
    assert [block.start for block in template_out.blocks] == ["08:00", "14:00"]
    assert template_out.weekdays == ["monday", "friday"]
    assert template_out.updated_at is None
