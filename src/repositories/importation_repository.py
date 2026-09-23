from datetime import datetime, time

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

    async def buscar_por_fecha(
        self,
        fecha
    ):

        inicio_dia = datetime.combine(
            fecha.date(),
            time.min
        )

        fin_dia = datetime.combine(
            fecha.date(),
            time.max
        )

        return await self.collection.find_one(
            {
                "desde": {
                    "$lte": fin_dia
                },
                "$or": [
                    {
                        "hasta": None
                    },
                    {
                        "hasta": {
                            "$gt": inicio_dia
                        }
                    }
                ]
            },
            sort=[
                ("desde", -1)
            ]
        )

    async def obtener_primera_importacion(self):

        return await self.collection.find_one(
            {},
            sort=[
                ("desde", 1)
            ]
        )