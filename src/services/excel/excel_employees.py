from motor.motor_asyncio import AsyncIOMotorDatabase


from src.repositories.employees_repository import EmployeesRepository
from src.repositories.old_employee_repository import OldEmployeeRepository


class ExcelEmployees:

    def __init__(self, db: AsyncIOMotorDatabase):

        self.employees_repository = EmployeesRepository(db)

        self.old_employee_repository = OldEmployeeRepository(db)

    # ==========================
    # OBTENER EMPLEADOS DEL EXCEL
    # ==========================

    def obtener_empleados_excel(self, empleados):

        empleados_excel = set()

        for _, employee in empleados.iterrows():

            correo = str(
                employee["Correo electronico"]
            ).strip()

            empleados_excel.add(correo)

        return empleados_excel

    # ==========================
    # DETECTAR EMPLEADOS QUE YA NO ESTÁN
    # ==========================

    async def detectar_empleados_que_ya_no_estan(
        self,
        empleados_excel,
        fecha_actual
    ):

        empleados_actuales = await self.employees_repository.obtener_todos()

        for empleado_actual in empleados_actuales:

            correo_actual = empleado_actual.get(
                "correo_electronico"
            )

            if not correo_actual:
                continue

            if correo_actual not in empleados_excel:

                empleado_antiguo = empleado_actual.copy()

                # Mongo creará un nuevo _id
                empleado_antiguo.pop("_id", None)

                # Evitar duplicados en empleados_antiguos
                existe = await self.old_employee_repository.existe(
                    correo_electronico=correo_actual
                )

                if not existe:

                    empleado_antiguo["fecha"] = fecha_actual

                    await self.old_employee_repository.guardar(
                        empleado_antiguo
                    )

                # Marcar empleado como inactivo
                await self.employees_repository.desactivar(
                    correo_electronico=correo_actual
                )

    # ==========================
    # GUARDAR EMPLEADOS
    # ==========================

    async def guardar_empleados(self, empleados):

        employee_ids = {}

        for _, employee in empleados.iterrows():

            nombre = str(
                employee["Nombre completo"]
            ).strip()

            area = str(
                employee["Area"]
            ).strip()

            cargo = str(
                employee["Cargo"]
            ).strip()

            correo = str(
                employee["Correo electronico"]
            ).strip()

            usuario = await self.employees_repository.create_or_update(
                nombre_completo=nombre,
                area=area,
                cargo=cargo,
                correo_electronico=correo
            )

            employee_ids[nombre] = usuario["_id"]

        return employee_ids
