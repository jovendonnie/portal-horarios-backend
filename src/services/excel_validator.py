import re

import pandas as pd


class ExcelValidator:

    # ==========================
    # COLUMNAS EMPLEADOS
    # ==========================

    EMPLOYEE_COLUMNS = [
        "Area",
        "Cargo",
        "Nombre completo",
        "Correo electronico"
    ]

    # ==========================
    # COLUMNAS HORARIOS
    # ==========================

    SCHEDULE_COLUMNS = [
        "Nombre completo",

        "Lunes entrada",
        "lunes salida",
        "Lunes estado",

        "Martes entrada",
        "Martes salida",
        "Martes estado",

        "Miercoles entrada",
        "Miercoles salida",
        "Miercoles estado",

        "Jueves entrada",
        "Jueves salida",
        "Jueves estado",

        "Viernes entrada",
        "Viernes salida",
        "Viernes estado"
    ]

    DAYS = [
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes"
    ]

    VALID_STATES = [
        "casa",
        "oficina"
    ]

    # ==========================
    # UTILIDADES
    # ==========================

    @staticmethod
    def _is_empty(value):

        if value is None:
            return True

        if pd.isna(value):
            return True

        if str(value).strip() == "":
            return True

        return False

    @staticmethod
    def _normalize(value):

        if ExcelValidator._is_empty(value):
            return ""

        return str(value).strip().lower()

    @staticmethod
    def _valid_email(email):

        if ExcelValidator._is_empty(email):
            return False

        pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        return bool(
            re.match(
                pattern,
                str(email).strip()
            )
        )

    @staticmethod
    def _valid_time(value):

        if ExcelValidator._is_empty(value):
            return False

        # pandas puede leer las horas como time
        if hasattr(value, "strftime"):

            try:
                value.strftime("%H:%M")
                return True
            except Exception:
                return False

        value = str(value).strip()

        # Formato HH:MM
        pattern = r"^(?:[01]\d|2[0-3]):[0-5]\d$"

        return bool(
            re.match(
                pattern,
                value
            )
        )

    @staticmethod
    def _format_value(value):

        if ExcelValidator._is_empty(value):
            return ""

        if hasattr(value, "strftime"):

            try:
                return value.strftime("%H:%M")
            except Exception:
                pass

        return str(value).strip()

    # ==========================
    # VALIDAR COLUMNAS
    # ==========================

    @staticmethod
    def _validate_columns(
        df,
        required_columns,
        sheet_name
    ):

        errores = []

        columns = list(df.columns)

        for column in required_columns:

            if column not in columns:

                errores.append({
                    "hoja": sheet_name,
                    "campo": column,
                    "error": "Falta esta columna en el Excel."
                })

        return errores

    # ==========================
    # VALIDAR EMPLEADOS
    # ==========================

    @staticmethod
    def _validate_employees(df):

        errores = []
        nombres = set()
        correos = set()

        for index, row in df.iterrows():

            fila = index + 4

            # --------------------------
            # Saltar fila completamente vacía
            # --------------------------

            if all(
                ExcelValidator._is_empty(valor)
                for valor in row
            ):
                continue

            # --------------------------
            # Campos obligatorios
            # --------------------------

            for campo in ExcelValidator.EMPLOYEE_COLUMNS:

                if campo not in df.columns:
                    continue

                if ExcelValidator._is_empty(row[campo]):

                    errores.append({
                        "hoja": "empleados",
                        "fila": fila,
                        "campo": campo,
                        "error": "Campo obligatorio."
                    })

            # --------------------------
            # Nombre
            # --------------------------

            if "Nombre completo" in df.columns:

                nombre = ExcelValidator._normalize(
                    row["Nombre completo"]
                )

                if nombre:

                    if len(nombre) < 2:

                        errores.append({
                            "hoja": "empleados",
                            "fila": fila,
                            "campo": "Nombre completo",
                            "valor": nombre,
                            "error": "El nombre es demasiado corto."
                        })

                    if nombre in nombres:

                        errores.append({
                            "hoja": "empleados",
                            "fila": fila,
                            "campo": "Nombre completo",
                            "valor": nombre,
                            "error": "El empleado está duplicado."
                        })

                    else:

                        nombres.add(nombre)

            # --------------------------
            # Correo
            # --------------------------

            if "Correo electronico" in df.columns:

                correo = ExcelValidator._normalize(
                    row["Correo electronico"]
                )

                if correo:

                    if not ExcelValidator._valid_email(correo):

                        errores.append({
                            "hoja": "empleados",
                            "fila": fila,
                            "campo": "Correo electronico",
                            "valor": correo,
                            "error": "El correo electronico no tiene un formato valido."
                        })

                    if correo in correos:

                        errores.append({
                            "hoja": "empleados",
                            "fila": fila,
                            "campo": "Correo electronico",
                            "valor": correo,
                            "error": "El correo electronico está duplicado."
                        })

                    else:

                        correos.add(correo)

        return errores

    # ==========================
    # VALIDAR HORARIOS
    # ==========================

    @staticmethod
    def _validate_schedules(
        df,
        employee_names
    ):

        errores = []
        nombres_horarios = set()

        for index, row in df.iterrows():

            fila = index + 4

            # --------------------------
            # Saltar fila vacía
            # --------------------------

            if all(
                ExcelValidator._is_empty(valor)
                for valor in row
            ):
                continue

            # --------------------------
            # Nombre
            # --------------------------

            nombre = ExcelValidator._normalize(
                row["Nombre completo"]
            )

            if ExcelValidator._is_empty(nombre):

                errores.append({
                    "hoja": "horarios",
                    "fila": fila,
                    "campo": "Nombre completo",
                    "error": "Campo obligatorio."
                })

                continue

            # --------------------------
            # Comprobar empleado existente
            # --------------------------

            if nombre not in employee_names:

                errores.append({
                    "hoja": "horarios",
                    "fila": fila,
                    "campo": "Nombre completo",
                    "valor": nombre,
                    "error": "El empleado no existe en la hoja empleados."
                })

            # --------------------------
            # Duplicados
            # --------------------------

            if nombre in nombres_horarios:

                errores.append({
                    "hoja": "horarios",
                    "fila": fila,
                    "campo": "Nombre completo",
                    "valor": nombre,
                    "error": "El empleado está duplicado en la hoja horarios."
                })

            else:

                nombres_horarios.add(nombre)

            # --------------------------
            # Validar cada día
            # --------------------------

            for dia in ExcelValidator.DAYS:

                entrada_column = f"{dia} entrada"

                salida_column = f"{dia} salida"

                estado_column = f"{dia} estado"

                # Caso especial del Excel actual
                if dia == "Lunes":

                    salida_column = "lunes salida"

                # --------------------------
                # Entrada
                # --------------------------

                entrada = row[entrada_column]

                if ExcelValidator._is_empty(entrada):

                    errores.append({
                        "hoja": "horarios",
                        "fila": fila,
                        "campo": entrada_column,
                        "error": "Campo obligatorio."
                    })

                elif not ExcelValidator._valid_time(entrada):

                    errores.append({
                        "hoja": "horarios",
                        "fila": fila,
                        "campo": entrada_column,
                        "valor": ExcelValidator._format_value(entrada),
                        "error": "La hora no tiene un formato valido."
                    })

                # --------------------------
                # Salida
                # --------------------------

                salida = row[salida_column]

                if ExcelValidator._is_empty(salida):

                    errores.append({
                        "hoja": "horarios",
                        "fila": fila,
                        "campo": salida_column,
                        "error": "Campo obligatorio."
                    })

                elif not ExcelValidator._valid_time(salida):

                    errores.append({
                        "hoja": "horarios",
                        "fila": fila,
                        "campo": salida_column,
                        "valor": ExcelValidator._format_value(salida),
                        "error": "La hora no tiene un formato valido."
                    })

                # --------------------------
                # Estado
                # --------------------------

                estado = ExcelValidator._normalize(
                    row[estado_column]
                )

                if not estado:

                    errores.append({
                        "hoja": "horarios",
                        "fila": fila,
                        "campo": estado_column,
                        "error": "Campo obligatorio."
                    })

                elif estado not in ExcelValidator.VALID_STATES:

                    errores.append({
                        "hoja": "horarios",
                        "fila": fila,
                        "campo": estado_column,
                        "valor": estado,
                        "error": (
                            "Estado no valido. "
                            "Debe ser 'casa' u 'oficina'."
                        )
                    })

        return errores

    # ==========================
    # VALIDACIÓN PRINCIPAL
    # ==========================

    @staticmethod
    def validate(
        empleados,
        horarios
    ):

        errores = []

        # ==========================
        # VALIDAR COLUMNAS EMPLEADOS
        # ==========================

        errores.extend(
            ExcelValidator._validate_columns(
                empleados,
                ExcelValidator.EMPLOYEE_COLUMNS,
                "empleados"
            )
        )

        # ==========================
        # VALIDAR COLUMNAS HORARIOS
        # ==========================

        errores.extend(
            ExcelValidator._validate_columns(
                horarios,
                ExcelValidator.SCHEDULE_COLUMNS,
                "horarios"
            )
        )

        # Si faltan columnas, no continuar
        # porque podrían provocar KeyError.
        columnas_empleados_completas = all(
            columna in empleados.columns
            for columna in ExcelValidator.EMPLOYEE_COLUMNS
        )

        columnas_horarios_completas = all(
            columna in horarios.columns
            for columna in ExcelValidator.SCHEDULE_COLUMNS
        )

        # ==========================
        # VALIDAR EMPLEADOS
        # ==========================

        if columnas_empleados_completas:

            errores.extend(
                ExcelValidator._validate_employees(
                    empleados
                )
            )

        # ==========================
        # NOMBRES DE EMPLEADOS
        # ==========================

        employee_names = set()

        if "Nombre completo" in empleados.columns:

            for value in empleados["Nombre completo"]:

                nombre = ExcelValidator._normalize(value)

                if nombre:
                    employee_names.add(nombre)

        # ==========================
        # VALIDAR HORARIOS
        # ==========================

        if columnas_horarios_completas:

            errores.extend(
                ExcelValidator._validate_schedules(
                    horarios,
                    employee_names
                )
            )

        return errores