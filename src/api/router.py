from fastapi import APIRouter

from src.api.routes import auth, health, users

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
