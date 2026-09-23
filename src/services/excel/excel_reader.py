import pandas as pd

from io import BytesIO


class ExcelReader:

    # ==========================
    # LEER ARCHIVO
    # ==========================

    async def leer_archivo(self, archivo):

        contenido = await archivo.read()

        if not contenido:
            return {
                "valido": False,
                "errores": [
                    {
                        "error": "El archivo está vacío."
                    }
                ]
            }

        nombre_archivo = archivo.filename or ""

        if not nombre_archivo.lower().endswith(".xlsx"):
            return {
                "valido": False,
                "errores": [
                    {
                        "error": "El archivo debe ser un Excel con formato .xlsx."
                    }
                ]
            }

        excel = BytesIO(contenido)

        try:

            archivo_excel = pd.ExcelFile(excel)

        except Exception:

            return {
                "valido": False,
                "errores": [
                    {
                        "error": "El archivo no es un Excel válido o está dañado."
                    }
                ]
            }

        return {
            "valido": True,
            "nombre_archivo": nombre_archivo,
            "excel": excel,
            "archivo_excel": archivo_excel
        }

    # ==========================
    # VALIDAR HOJAS
    # ==========================

    def validar_hojas(self, archivo_excel):

        hojas_requeridas = [
            "empleados",
            "horarios"
        ]

        errores_hojas = []

        for hoja in hojas_requeridas:

            if hoja not in archivo_excel.sheet_names:

                errores_hojas.append({
                    "hoja": hoja,
                    "error": "Falta esta hoja en el Excel."
                })

        if errores_hojas:

            return {
                "valido": False,
                "errores": errores_hojas
            }

        return {
            "valido": True
        }

    # ==========================
    # LEER EXCEL
    # ==========================

    def leer_hojas(self, excel):

        try:

            empleados = pd.read_excel(
                excel,
                sheet_name="empleados",
                skiprows=2
            )

            horarios = pd.read_excel(
                excel,
                sheet_name="horarios",
                skiprows=2
            )

        except Exception as error:

            return {
                "valido": False,
                "errores": [
                    {
                        "error": "No fue posible leer correctamente el contenido del Excel.",
                        "detalle": str(error)
                    }
                ]
            }

        return {
            "valido": True,
            "empleados": empleados,
            "horarios": horarios
        }
