from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.database import get_database
from src.services.schedule_service import ScheduleService


router = APIRouter(
    prefix="/schedule",
    tags=["schedule"]
)


@router.get("")
async def get_current_schedule(
    area: list[str] | None = Query(
        default=None
    ),
    cargo: list[str] | None = Query(
        default=None
    ),
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    service = ScheduleService(db)

    return await service.obtener_horario_actual(
        areas=area,
        cargos=cargo
    )


@router.get("/range")
async def get_schedule_range(
    desde: str,
    hasta: str,
    area: list[str] | None = Query(
        default=None
    ),
    cargo: list[str] | None = Query(
        default=None
    ),
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    service = ScheduleService(db)

    return await service.consultar_por_rango(
        desde=desde,
        hasta=hasta,
        areas=area,
        cargos=cargo
    )


@router.get("/{fecha}")
async def get_schedule_by_date(
    fecha: str,
    area: list[str] | None = Query(
        default=None
    ),
    cargo: list[str] | None = Query(
        default=None
    ),
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    service = ScheduleService(db)

    return await service.consultar_por_fecha(
        fecha=fecha,
        areas=area,
        cargos=cargo
    )