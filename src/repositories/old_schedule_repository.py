from motor.motor_asyncio import AsyncIOMotorDatabase


class OldScheduleRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.horarios_antiguos

    async def guardar(
        self,
        importacion_id,
        fecha,
        horarios: list
    ):

        # Contar cuántos horarios antiguos existen
        cantidad = await self.collection.count_documents({})

        numero = cantidad + 1

        horario_antiguo = {
            "nombre": f"horario_antiguo_{numero}",
            "importacion_id": importacion_id,
            "fecha": fecha,
            "horarios": horarios
        }

        resultado = await self.collection.insert_one(
            horario_antiguo
        )

        return await self.collection.find_one(
            {
                "_id": resultado.inserted_id
            }
        )

