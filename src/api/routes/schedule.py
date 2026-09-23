from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.database import get_database
from src.services.schedule_service import ScheduleService


router = APIRouter(
    prefix="/schedule",
    tags=["schedule"]
)


@router.get("")
async def get_current_schedule(
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    service = ScheduleService(db)

    return await service.obtener_horario_actual()


@router.get("/range")
async def get_schedule_range(
    desde: str,
    hasta: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    service = ScheduleService(db)

    return await service.consultar_por_rango(
        desde,
        hasta
    )


@router.get("/{fecha}")
async def get_schedule_by_date(
    fecha: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):

    service = ScheduleService(db)

    return await service.consultar_por_fecha(
        fecha
    )