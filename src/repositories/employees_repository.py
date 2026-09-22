from motor.motor_asyncio import AsyncIOMotorDatabase


class EmployeesRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.usuarios

    async def create_or_update(
        self,
        nombre_completo: str,
        area: str,
        cargo: str
    ):
        await self.collection.update_one(
            {
                "nombre_completo": nombre_completo
            },
            {
                "$set": {
                    "nombre_completo": nombre_completo,
                    "area": area,
                    "cargo": cargo
                }
            },
            upsert=True
        )

        return await self.collection.find_one(
            {
                "nombre_completo": nombre_completo
            }
        )