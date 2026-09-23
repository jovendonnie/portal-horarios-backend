from fastapi import APIRouter, Depends, UploadFile, File
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.database import get_database
from src.services.excel_service import ExcelService


router = APIRouter(
    prefix="/excel",
    tags=["excel"]
)


@router.post("/employees")
async def import_employees(
    archivo: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    service = ExcelService(db)

    return await service.import_excel(archivo)


@router.get("/schedule")
async def get_current_schedule(
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    service = ExcelService(db)

    return await service.get_current_schedule()