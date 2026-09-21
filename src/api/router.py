from fastapi import APIRouter

from src.api.routes import health

router = APIRouter()
router.include_router(health.router)
