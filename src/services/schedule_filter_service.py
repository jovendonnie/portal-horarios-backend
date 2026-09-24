class ScheduleFilterService:

    def filtrar(
        self,
        horarios: list,
        areas=None,
        cargos=None
    ):

        resultado = []

        # ==========================
        # NORMALIZAR ÁREAS
        # ==========================

        areas_normalizadas = []

        if areas:

            areas_normalizadas = [
                str(area).strip().lower()
                for area in areas
            ]

        # ==========================
        # NORMALIZAR CARGOS
        # ==========================

        cargos_normalizados = []

        if cargos:

            cargos_normalizados = [
                str(cargo).strip().lower()
                for cargo in cargos
            ]

        # ==========================
        # APLICAR FILTROS
        # ==========================

        for horario in horarios:

            area = str(
                horario.get("area", "")
            ).strip().lower()

            cargo = str(
                horario.get("cargo", "")
            ).strip().lower()

            # ==========================
            # FILTRO POR ÁREA
            # ==========================

            if areas_normalizadas:

                if area not in areas_normalizadas:
                    continue

            # ==========================
            # FILTRO POR CARGO
            # ==========================

            if cargos_normalizados:

                if cargo not in cargos_normalizados:
                    continue

            resultado.append(
                horario
            )

        return resultado