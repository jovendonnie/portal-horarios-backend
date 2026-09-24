from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.repositories.importation_repository import ImportacionRepository
from src.repositories.old_schedule_repository import OldScheduleRepository
from src.repositories.schedule_repository import ScheduleRepository
from src.repositories.employees_repository import EmployeesRepository

from src.services.schedule_filter_service import ScheduleFilterService


class ScheduleService:

    def __init__(self, db: AsyncIOMotorDatabase):

        self.importacion_repository = ImportacionRepository(db)

        self.old_schedule_repository = OldScheduleRepository(db)

        self.schedule_repository = ScheduleRepository(db)

        self.employees_repository = EmployeesRepository(db)

        self.filter_service = ScheduleFilterService()

    # ==========================
    # OBTENER HORARIO ACTUAL
    # ==========================

    async def obtener_horario_actual(
        self,
        areas=None,
        cargos=None
    ):

        horarios = await self.schedule_repository.obtener_todos()

        resultado = []

        for horario in horarios:

            usuario_id = horario.get(
                "usuario_id"
            )

            usuario = await self.employees_repository.collection.find_one(
                {
                    "_id": usuario_id
                }
            )

            if not usuario:
                continue

            resultado.append({
                "usuario_id": str(usuario_id),
                "nombre_completo": usuario.get(
                    "nombre_completo"
                ),
                "area": usuario.get(
                    "area"
                ),
                "cargo": usuario.get(
                    "cargo"
                ),
                "correo_electronico": usuario.get(
                    "correo_electronico"
                ),
                "lunes": horario.get(
                    "lunes"
                ),
                "martes": horario.get(
                    "martes"
                ),
                "miercoles": horario.get(
                    "miercoles"
                ),
                "jueves": horario.get(
                    "jueves"
                ),
                "viernes": horario.get(
                    "viernes"
                )
            })

        # ==========================
        # APLICAR FILTROS
        # ==========================

        resultado = self.filter_service.filtrar(
            horarios=resultado,
            areas=areas,
            cargos=cargos
        )

        return {
            "vigente": True,
            "total": len(resultado),
            "horarios": resultado
        }

    # ==========================
    # CONSULTAR HORARIO POR FECHA
    # ==========================

    async def consultar_por_fecha(
        self,
        fecha: str,
        areas=None,
        cargos=None
    ):

        fecha = datetime.fromisoformat(
            fecha
        )

        # ==========================
        # DETERMINAR DÍA DE LA SEMANA
        # ==========================

        dias = {
            0: "lunes",
            1: "martes",
            2: "miercoles",
            3: "jueves",
            4: "viernes"
        }

        dia = dias.get(
            fecha.weekday()
        )

        # ==========================
        # VALIDAR QUE SEA LUNES A VIERNES
        # ==========================

        if not dia:

            return {
                "vigente": False,
                "mensaje": "No hay horario para sábados ni domingos",
                "fecha": fecha.date(),
                "dia": None,
                "horarios": []
            }

        # ==========================
        # BUSCAR IMPORTACIÓN
        # ==========================

        importacion = await self.importacion_repository.buscar_por_fecha(
            fecha
        )

        # ==========================
        # NO EXISTE IMPORTACIÓN
        # ==========================

        if not importacion:

            primera_importacion = (
                await self.importacion_repository.obtener_primera_importacion()
            )

            if not primera_importacion:

                return {
                    "vigente": False,
                    "mensaje": "No existen horarios registrados",
                    "fecha": fecha.date(),
                    "dia": dia,
                    "horarios": []
                }

            if fecha < primera_importacion["desde"]:

                return {
                    "vigente": False,
                    "mensaje": "No existía horario para esta fecha",
                    "fecha": fecha.date(),
                    "dia": dia,
                    "horarios": []
                }

            return {
                "vigente": False,
                "mensaje": "No se encontró un horario para esta fecha",
                "fecha": fecha.date(),
                "dia": dia,
                "horarios": []
            }

        importacion_id = str(
            importacion["_id"]
        )

        # ==========================
        # HORARIO ACTUAL
        # ==========================

        if importacion["vigente"]:

            resultado_actual = await self.obtener_horario_actual(
                areas=areas,
                cargos=cargos
            )

            horarios_dia = []

            for horario in resultado_actual["horarios"]:

                horarios_dia.append({
                    "usuario_id": horario["usuario_id"],
                    "nombre_completo": horario["nombre_completo"],
                    "area": horario["area"],
                    "cargo": horario["cargo"],
                    "correo_electronico": horario["correo_electronico"],
                    "entrada": horario[dia]["entrada"],
                    "salida": horario[dia]["salida"],
                    "estado": horario[dia]["estado"]
                })

            return {
                "fecha": fecha.date(),
                "dia": dia,
                "vigente": True,
                "mensaje": "Horario vigente hasta nuevo cambio",
                "importacion_id": importacion_id,
                "nombre_archivo": importacion["nombre_archivo"],
                "desde": importacion["desde"],
                "hasta": importacion["hasta"],
                "total": len(horarios_dia),
                "horarios": horarios_dia
            }

        # ==========================
        # HORARIO ANTIGUO
        # ==========================

        horario_antiguo = (
            await self.old_schedule_repository.buscar_por_importacion(
                importacion_id
            )
        )

        if not horario_antiguo:

            return {
                "vigente": False,
                "mensaje": "No se encontraron horarios históricos para esta fecha",
                "fecha": fecha.date(),
                "dia": dia,
                "importacion_id": importacion_id,
                "horarios": []
            }

        horarios_dia = []

        for horario in horario_antiguo.get(
            "horarios",
            []
        ):

            usuario_id = horario.get(
                "usuario_id"
            )

            usuario = await self.employees_repository.collection.find_one(
                {
                    "_id": usuario_id
                }
            )

            if not usuario:
                continue

            horarios_dia.append({
                "usuario_id": str(usuario_id),
                "nombre_completo": usuario.get(
                    "nombre_completo"
                ),
                "area": usuario.get(
                    "area"
                ),
                "cargo": usuario.get(
                    "cargo"
                ),
                "correo_electronico": usuario.get(
                    "correo_electronico"
                ),
                "entrada": horario[dia]["entrada"],
                "salida": horario[dia]["salida"],
                "estado": horario[dia]["estado"]
            })

        # ==========================
        # APLICAR FILTROS
        # ==========================

        horarios_dia = self.filter_service.filtrar(
            horarios=horarios_dia,
            areas=areas,
            cargos=cargos
        )

        return {
            "fecha": fecha.date(),
            "dia": dia,
            "vigente": False,
            "mensaje": "Horario correspondiente a una importación anterior",
            "importacion_id": importacion_id,
            "nombre_archivo": importacion["nombre_archivo"],
            "desde": importacion["desde"],
            "hasta": importacion["hasta"],
            "total": len(horarios_dia),
            "horarios": horarios_dia
        }

    # ==========================
    # CONSULTAR HORARIO POR RANGO
    # ==========================

    async def consultar_por_rango(
        self,
        desde: str,
        hasta: str,
        areas=None,
        cargos=None
    ):

        fecha_desde = datetime.fromisoformat(
            desde
        )

        fecha_hasta = datetime.fromisoformat(
            hasta
        )

        # ==========================
        # VALIDAR RANGO
        # ==========================

        if fecha_desde > fecha_hasta:

            return {
                "valido": False,
                "mensaje": "La fecha inicial no puede ser posterior a la fecha final",
                "dias": []
            }

        resultados = []

        fecha_actual = fecha_desde

        # ==========================
        # CONSULTAR CADA FECHA
        # ==========================

        while fecha_actual.date() <= fecha_hasta.date():

            resultado = await self.consultar_por_fecha(
                fecha=fecha_actual.strftime(
                    "%Y-%m-%d"
                ),
                areas=areas,
                cargos=cargos
            )

            resultados.append(
                resultado
            )

            fecha_actual += timedelta(
                days=1
            )

        return {
            "valido": True,
            "desde": fecha_desde.date(),
            "hasta": fecha_hasta.date(),
            "total_dias": len(resultados),
            "dias": resultados
        }