"""Rutas HTTP del catálogo de Plantillas de turno: solo orquestan (spec 009, RF-2)."""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import require_admin, require_read
from src.schemas.shift_template import (
    ShiftTemplateCreate,
    ShiftTemplateOut,
    ShiftTemplateUpdate,
)
from src.services import shift_template_service

router = APIRouter(prefix="/shift-templates", tags=["shift-templates"])


def _parse_template_id(template_id: str) -> ObjectId:
    try:
        return ObjectId(template_id)
    except InvalidId as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"No existe una {shift_template_service.ENTITY_LABEL} con ese id",
        ) from exc


@router.post("", response_model=ShiftTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template_route(
    data: ShiftTemplateCreate, actor: dict = Depends(require_admin)
) -> ShiftTemplateOut:
    try:
        template = await shift_template_service.create_template(data, actor)
    except shift_template_service.InvalidNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except shift_template_service.DuplicateTemplateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ShiftTemplateOut(**template)


@router.get("", response_model=list[ShiftTemplateOut])
async def list_templates_route(_actor: dict = Depends(require_read)) -> list[ShiftTemplateOut]:
    templates = await shift_template_service.list_templates()
    return [ShiftTemplateOut(**template) for template in templates]


@router.patch("/{template_id}", response_model=ShiftTemplateOut)
async def update_template_route(
    template_id: str, data: ShiftTemplateUpdate, actor: dict = Depends(require_admin)
) -> ShiftTemplateOut:
    try:
        template = await shift_template_service.update_template(
            _parse_template_id(template_id), data, actor
        )
    except shift_template_service.TemplateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except shift_template_service.InvalidNameError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except shift_template_service.DuplicateTemplateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return ShiftTemplateOut(**template)
