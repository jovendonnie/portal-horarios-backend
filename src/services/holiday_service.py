"""Lógica de negocio del calendario de Festivos (spec 009, RF-3, RF-4).

El día se identifica por su fecha (`YYYY-MM-DD`), no por su `_id`: es la clave
natural del calendario y la que ya usa el portal en la URL. El `_id` solo se
usa como `entity_id` de la auditoría.
"""

from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from src.core.database import start_transaction
from src.models import holiday
from src.services import history_service

ENTITY_LABEL = "día del calendario"

# Festivos de Colombia con fecha fija que no se trasladan.
_FIXED_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Año Nuevo"),
    (5, 1, "Día del Trabajo"),
    (7, 20, "Día de la Independencia"),
    (8, 7, "Batalla de Boyacá"),
    (12, 8, "Inmaculada Concepción"),
    (12, 25, "Navidad"),
)

# Festivos de fecha fija sujetos a la Ley Emiliani: se trasladan al lunes
# siguiente cuando no caen lunes.
_EMILIANI_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 6, "Día de los Reyes Magos"),
    (3, 19, "Día de San José"),
    (6, 29, "San Pedro y San Pablo"),
    (8, 15, "Asunción de la Virgen"),
    (10, 12, "Día de la Raza"),
    (11, 1, "Día de Todos los Santos"),
    (11, 11, "Independencia de Cartagena"),
)

# Festivos derivados de la Pascua que conservan su día de la semana.
_EASTER_FIXED_OFFSETS: tuple[tuple[int, str], ...] = (
    (-3, "Jueves Santo"),
    (-2, "Viernes Santo"),
)

# Derivados de la Pascua que por ley caen siempre lunes: el desplazamiento ya
# los deja en lunes, no hace falta aplicarles Emiliani.
_EASTER_MONDAY_OFFSETS: tuple[tuple[int, str], ...] = (
    (43, "Ascensión del Señor"),
    (64, "Corpus Christi"),
    (71, "Sagrado Corazón de Jesús"),
)


class DuplicateHolidayError(Exception):
    def __init__(self) -> None:
        super().__init__("Ya hay un día registrado en esa fecha")


class HolidayNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__(f"No existe un {ENTITY_LABEL} en esa fecha")


class NationalHolidayError(Exception):
    def __init__(self) -> None:
        super().__init__("Un festivo nacional no se puede eliminar; solo los días de la empresa")


def _easter_sunday(year: int) -> date_type:
    """Domingo de Pascua por el algoritmo gregoriano anónimo (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date_type(year, month, day)


def _next_monday(value: date_type) -> date_type:
    """La misma fecha si ya es lunes, o el lunes siguiente (Ley Emiliani)."""
    return value + timedelta(days=(7 - value.weekday()) % 7)


def national_holidays(year: int) -> list[tuple[str, str]]:
    """Los festivos nacionales de Colombia de un año, ordenados por fecha.

    Función pura: se calculan en vez de leerse de una tabla por año, para que no
    haya que mantenerla cada diciembre (spec 009, plan.md sección 3).

    Son 18 celebraciones, pero dos pueden caer el mismo día (en 2025 el Sagrado
    Corazón y San Pedro y San Pablo coinciden el 30 de junio): en ese caso se
    devuelve un único día con los dos nombres, porque la fecha es la clave del
    calendario y un día festivo no se cuenta dos veces.
    """
    easter = _easter_sunday(year)
    entries: list[tuple[date_type, str]] = []

    entries.extend((date_type(year, month, day), name) for month, day, name in _FIXED_HOLIDAYS)
    entries.extend(
        (_next_monday(date_type(year, month, day)), name) for month, day, name in _EMILIANI_HOLIDAYS
    )
    entries.extend((easter + timedelta(days=offset), name) for offset, name in _EASTER_FIXED_OFFSETS)
    entries.extend((easter + timedelta(days=offset), name) for offset, name in _EASTER_MONDAY_OFFSETS)

    by_date: dict[str, list[str]] = {}
    for value, name in sorted(entries):
        by_date.setdefault(value.isoformat(), []).append(name)

    return [(date, " · ".join(names)) for date, names in by_date.items()]


async def list_holidays(year: int) -> list[dict[str, Any]]:
    return await holiday.list_holidays_by_year(year)


async def create_holiday(date: str, name: str, actor: dict[str, Any]) -> dict[str, Any]:
    """Registra un día de la empresa. Nace bloqueando turnos; Gestión Humana puede
    cambiarlo después con `set_blocks_shifts` (RF-3)."""
    if await holiday.find_holiday_by_date(date) is not None:
        raise DuplicateHolidayError()

    ahora = datetime.now(timezone.utc)

    async with start_transaction() as session:
        try:
            holiday_id = await holiday.insert_holiday(
                date, name, "empresa", True, actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, "holiday", holiday_id, "create", [], actor, ahora
            )
            await session.commit_transaction()
        except DuplicateKeyError as exc:
            await session.abort_transaction()
            raise DuplicateHolidayError() from exc
        except Exception:
            await session.abort_transaction()
            raise

    return await holiday.find_holiday_by_date(date)


async def set_blocks_shifts(
    date: str, blocks_shifts: bool, actor: dict[str, Any]
) -> dict[str, Any]:
    actual = await holiday.find_holiday_by_date(date)
    if actual is None:
        raise HolidayNotFoundError()

    diffs = history_service.compute_diff(
        {"blocks_shifts": actual["blocks_shifts"]},
        {"blocks_shifts": blocks_shifts},
        ["blocks_shifts"],
    )
    if not diffs:
        return actual

    ahora = datetime.now(timezone.utc)

    async with start_transaction() as session:
        try:
            await holiday.set_blocks_shifts(
                date, blocks_shifts, actor.get("_id"), ahora, session=session
            )
            await history_service.record_change(
                session, "holiday", actual["_id"], "update", diffs, actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    return await holiday.find_holiday_by_date(date)


async def delete_holiday(date: str, actor: dict[str, Any]) -> str:
    actual = await holiday.find_holiday_by_date(date)
    if actual is None:
        raise HolidayNotFoundError()
    if actual["type"] == "nacional":
        raise NationalHolidayError()

    ahora = datetime.now(timezone.utc)

    async with start_transaction() as session:
        try:
            await holiday.delete_holiday(date, session=session)
            await history_service.record_change(
                session, "holiday", actual["_id"], "delete", [], actor, ahora
            )
            await session.commit_transaction()
        except Exception:
            await session.abort_transaction()
            raise

    return date


async def import_national_holidays(year: int, actor: dict[str, Any]) -> dict[str, Any]:
    """Crea los festivos nacionales del año que falten y reporta los omitidos.

    No sobrescribe nada: una fecha ya registrada se omite tal cual, para no
    perder lo que Gestión Humana haya configurado en ella (RF-4).
    """
    imported: list[dict[str, Any]] = []
    skipped_dates: list[str] = []

    for date, name in national_holidays(year):
        if await holiday.find_holiday_by_date(date) is not None:
            skipped_dates.append(date)
            continue

        ahora = datetime.now(timezone.utc)
        async with start_transaction() as session:
            try:
                holiday_id = await holiday.insert_holiday(
                    date, name, "nacional", True, actor.get("_id"), ahora, session=session
                )
                await history_service.record_change(
                    session, "holiday", holiday_id, "create", [], actor, ahora
                )
                await session.commit_transaction()
            except DuplicateKeyError:
                # Otra sesión registró la misma fecha entre la verificación y la
                # escritura: cuenta como omitida, no como error (RF-4).
                await session.abort_transaction()
                skipped_dates.append(date)
                continue
            except Exception:
                await session.abort_transaction()
                raise

        imported.append(await holiday.find_holiday_by_date(date))

    return {"imported": imported, "skipped_dates": skipped_dates}
