from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.database import get_database

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncIOMotorDatabase = Depends(get_database)):
    await db.command("ping")
    return {"status": "ok"}
