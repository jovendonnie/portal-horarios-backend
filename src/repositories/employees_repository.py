from motor.motor_asyncio import AsyncIOMotorDatabase


class EmployeesRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.usuarios

    async def create_or_update(
        self,
        nombre_completo: str,
        area: str,
        cargo: str,
        correo_electronico: str
    ):

        await self.collection.update_one(
            {
                "nombre_completo": nombre_completo
            },
            {
                "$set": {
                    "nombre_completo": nombre_completo,
                    "area": area,
                    "cargo": cargo,
                    "correo_electronico": correo_electronico,
                    "activo": True
                }
            },
            upsert=True
        )

        return await self.collection.find_one(
            {
                "nombre_completo": nombre_completo
            }
        )

    async def obtener_todos(self):

        return await self.collection.find({}).to_list(
            length=None
        )

    async def desactivar(
        self,
        correo_electronico: str
    ):

        await self.collection.update_one(
            {
                "correo_electronico": correo_electronico
            },
            {
                "$set": {
                    "activo": False
                }
            }
        )

