from fastapi import APIRouter

from src.api.routes import areas, auth, employees, health, history, schedules, statuses, users

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(employees.router)
router.include_router(areas.router)
router.include_router(statuses.router)
router.include_router(history.router)
router.include_router(schedules.router)
