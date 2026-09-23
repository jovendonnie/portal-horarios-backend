from motor.motor_asyncio import AsyncIOMotorDatabase


class ScheduleRepository:

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.horarios

    # ==========================
    # CREAR O ACTUALIZAR HORARIO ACTUAL
    # ==========================

    async def create_or_update(
        self,
        importacion_id,
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

    # ==========================
    # OBTENER TODOS LOS HORARIOS ACTUALES
    # ==========================

    async def obtener_todos(self):

        return await self.collection.find({}).to_list(
            length=None
        )

    # ==========================
    # ELIMINAR TODOS LOS HORARIOS ACTUALES
    # ==========================

    async def eliminar_todos(self):

        resultado = await self.collection.delete_many({})

        return resultado.deleted_count
