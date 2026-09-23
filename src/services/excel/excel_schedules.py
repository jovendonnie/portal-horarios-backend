
from motor.motor_asyncio import AsyncIOMotorDatabase


from src.repositories.schedule_repository import ScheduleRepository
from src.repositories.old_schedule_repository import OldScheduleRepository


class ExcelSchedules:

    def __init__(self, db: AsyncIOMotorDatabase):

        self.schedule_repository = ScheduleRepository(db)

        self.old_schedule_repository = OldScheduleRepository(db)

    # ==========================
    # GUARDAR HORARIOS ACTUALES
    # COMO UN ÚNICO HORARIO ANTIGUO
    # ==========================

    async def guardar_horarios_antiguos(
        self,
        fecha_actual
    ):

        horarios_actuales = await self.schedule_repository.obtener_todos()

        if not horarios_actuales:
            return

        horarios_antiguos = []

        for horario in horarios_actuales:

            horario_antiguo = horario.copy()

            # Mongo creará un nuevo _id
            horario_antiguo.pop("_id", None)

            horarios_antiguos.append(
                horario_antiguo
            )

        # La importación anterior está dentro
        # de los horarios actuales
        importacion_anterior = horarios_antiguos[0].get(
            "importacion_id"
        )

        await self.old_schedule_repository.guardar(
            importacion_id=importacion_anterior,
            fecha=fecha_actual,
            horarios=horarios_antiguos
        )

    # ==========================
    # ELIMINAR HORARIOS ACTUALES
    # ==========================

    async def eliminar_horarios_actuales(self):

        await self.schedule_repository.eliminar_todos()

    # ==========================
    # GUARDAR HORARIOS DEL EXCEL
    # ==========================

    async def guardar_horarios(
        self,
        horarios,
        employee_ids,
        importacion_id
    ):

        horarios_procesados = 0

        for _, schedule in horarios.iterrows():

            nombre = str(
                schedule["Nombre completo"]
            ).strip()

            usuario_id = employee_ids.get(nombre)

            if not usuario_id:
                continue

            horario = {

                "importacion_id": importacion_id,

                "usuario_id": usuario_id,

                "lunes": {
                    "entrada": str(
                        schedule["Lunes entrada"]
                    ),
                    "salida": str(
                        schedule["lunes salida"]
                    ),
                    "estado": str(
                        schedule["Lunes estado"]
                    )
                },

                "martes": {
                    "entrada": str(
                        schedule["Martes entrada"]
                    ),
                    "salida": str(
                        schedule["Martes salida"]
                    ),
                    "estado": str(
                        schedule["Martes estado"]
                    )
                },

                "miercoles": {
                    "entrada": str(
                        schedule["Miercoles entrada"]
                    ),
                    "salida": str(
                        schedule["Miercoles salida"]
                    ),
                    "estado": str(
                        schedule["Miercoles estado"]
                    )
                },

                "jueves": {
                    "entrada": str(
                        schedule["Jueves entrada"]
                    ),
                    "salida": str(
                        schedule["Jueves salida"]
                    ),
                    "estado": str(
                        schedule["Jueves estado"]
                    )
                },

                "viernes": {
                    "entrada": str(
                        schedule["Viernes entrada"]
                    ),
                    "salida": str(
                        schedule["Viernes salida"]
                    ),
                    "estado": str(
                        schedule["Viernes estado"]
                    )
                }
            }

            await self.schedule_repository.create_or_update(
                importacion_id=importacion_id,
                usuario_id=usuario_id,
                horario=horario
            )

            horarios_procesados += 1

        return horarios_procesados
