from fastapi import APIRouter

from src.api.routes import auth, employees, health, users

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(employees.router)
