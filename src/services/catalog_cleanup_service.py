from datetime import datetime, timezone
from typing import Any

from src.core.database import start_transaction
from src.models import catalog, employee, schedule
from src.services import history_service

_ENTITY_TYPES: dict[str, str] = {"areas": "area", "estados": "status"}


def _normalize_name(name: str) -> str:
    return name.strip().casefold()


def _group_by_normalized_name(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(_normalize_name(entry["name"]), []).append(entry)
    return groups


async def _count_references(collection_name: str, entry_id: Any) -> int:
    if collection_name == "areas":
        return await employee.count_employees_by_area(entry_id)
    return await employee.count_employees_by_status(
        entry_id
    ) + await schedule.count_exceptions_by_status(entry_id)


async def _pick_keeper(collection_name: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    for entry in group:
        entry["reference_count"] = await _count_references(collection_name, entry["_id"])
    group.sort(key=lambda entry: (-entry["reference_count"], entry["created_at"]))
    return group[0]


async def diagnose_duplicates(collection_name: str, entity_label: str) -> list[dict[str, Any]]:
    groups = _group_by_normalized_name(await catalog.list_entries(collection_name))

    report: list[dict[str, Any]] = []
    for normalized_name, group_entries in groups.items():
        if len(group_entries) <= 1:
            continue
        keeper = await _pick_keeper(collection_name, group_entries)
        report.append(
            {
                "normalized_name": normalized_name,
                "entries": group_entries,
                "keep_id": keeper["_id"],
            }
        )
    return report


async def clean_duplicates(
    collection_name: str, entity_label: str, actor: dict[str, Any]
) -> list[dict[str, Any]]:
    groups = await diagnose_duplicates(collection_name, entity_label)
    results: list[dict[str, Any]] = []

    for group in groups:
        keeper_name = next(
            entry["name"] for entry in group["entries"] if entry["_id"] == group["keep_id"]
        )
        losers = [entry for entry in group["entries"] if entry["_id"] != group["keep_id"]]
        ahora = datetime.now(timezone.utc)
        total_employees = 0
        total_exceptions = 0

        async with start_transaction() as session:
            try:
                for loser in losers:
                    changes = [
                        {
                            "field": "merged_into_id",
                            "old_value": None,
                            "new_value": str(group["keep_id"]),
                        }
                    ]
                    if collection_name == "areas":
                        n = await employee.reassign_area(
                            loser["_id"], group["keep_id"], keeper_name, session=session
                        )
                        changes.append(
                            {"field": "reassigned_employees", "old_value": None, "new_value": n}
                        )
                        total_employees += n
                    else:
                        n = await employee.reassign_status(
                            loser["_id"], group["keep_id"], session=session
                        )
                        m = await schedule.reassign_status_in_exceptions(
                            loser["_id"], group["keep_id"], session=session
                        )
                        changes.append(
                            {"field": "reassigned_employees", "old_value": None, "new_value": n}
                        )
                        changes.append(
                            {"field": "reassigned_exceptions", "old_value": None, "new_value": m}
                        )
                        total_employees += n
                        total_exceptions += m

                    await catalog.delete_entry(collection_name, loser["_id"], session=session)
                    await history_service.record_change(
                        session,
                        _ENTITY_TYPES[collection_name],
                        loser["_id"],
                        "delete_duplicate",
                        changes,
                        actor,
                        ahora,
                    )
                await session.commit_transaction()
            except Exception:
                await session.abort_transaction()
                raise

        results.append(
            {
                "normalized_name": group["normalized_name"],
                "kept_id": group["keep_id"],
                "deleted_ids": [loser["_id"] for loser in losers],
                "reassigned_employees": total_employees,
                "reassigned_exceptions": total_exceptions,
            }
        )

    return results
