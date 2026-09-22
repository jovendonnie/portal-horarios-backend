from fastapi import APIRouter

from src.api.routes import health
from src.api.routes import excel


router = APIRouter()

router.include_router(health.router)
router.include_router(excel.router)