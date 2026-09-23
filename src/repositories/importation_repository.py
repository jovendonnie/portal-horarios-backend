from motor.motor_asyncio import AsyncIOMotorDatabase


class ImportacionRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.importaciones_excel

    async def crear(
        self,
        fecha_subida,
        nombre_archivo,
        desde
    ):
        importacion = {
            "fecha_subida": fecha_subida,
            "nombre_archivo": nombre_archivo,
            "desde": desde,
            "hasta": None,
            "vigente": True
        }

        resultado = await self.collection.insert_one(
            importacion
        )

        return await self.collection.find_one(
            {
                "_id": resultado.inserted_id
            }
        )

    async def cerrar_vigente(
        self,
        hasta
    ):
        await self.collection.update_many(
            {
                "vigente": True
            },
            {
                "$set": {
                    "vigente": False,
                    "hasta": hasta
                }
            }
        )