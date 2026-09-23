from motor.motor_asyncio import AsyncIOMotorDatabase


class OldEmployeeRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.empleados_antiguos

    async def guardar(
        self,
        empleado: dict
    ):

        resultado = await self.collection.insert_one(
            empleado
        )

        return await self.collection.find_one(
            {
                "_id": resultado.inserted_id
            }
        )

    async def existe(
        self,
        correo_electronico: str
    ):

        return await self.collection.find_one(
            {
                "correo_electronico": correo_electronico
            }
        )

