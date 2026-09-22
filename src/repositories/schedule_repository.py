from motor.motor_asyncio import AsyncIOMotorDatabase


class ScheduleRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.horarios

    async def create_or_update(
        self,
        usuario_id,
        horario: dict
    ):
        await self.collection.update_one(
            {
                "usuario_id": usuario_id
            },
            {
                "$set": horario
            },
            upsert=True
        )

        return await self.collection.find_one(
            {
                "usuario_id": usuario_id
            }
        )