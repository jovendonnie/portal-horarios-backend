from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import router
from src.core.config import settings
from src.core.database import close_mongo_connection, connect_to_mongo


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router)
