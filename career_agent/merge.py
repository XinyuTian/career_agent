from typing import Any


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, (list, dict, set, tuple)) and len(value) == 0:
        return True
    return False


def merge_scalar(existing: Any, incoming: Any) -> tuple[Any, str | None]:
    if is_empty(existing) and is_empty(incoming):
        return existing, None
    if is_empty(existing):
        return incoming, None
    if is_empty(incoming):
        return existing, None
    if existing == incoming:
        return existing, None
    return existing, f"Conflict: existing={existing!r}, incoming={incoming!r}"


def merge_list(existing: list, incoming: list) -> list:
    seen: set[Any] = set()
    merged: list[Any] = []
    for item in existing + incoming:
        if item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def merge_record(
    existing: dict,
    incoming: dict,
    list_fields: set[str],
) -> tuple[dict, list[str]]:
    merged: dict[str, Any] = {}
    conflicts: list[str] = []

    for key in existing.keys() | incoming.keys():
        existing_value = existing.get(key)
        incoming_value = incoming.get(key)

        if key in list_fields:
            existing_list = existing_value if isinstance(existing_value, list) else []
            incoming_list = incoming_value if isinstance(incoming_value, list) else []
            merged[key] = merge_list(existing_list, incoming_list)
            continue

        value, conflict = merge_scalar(existing_value, incoming_value)
        merged[key] = value
        if conflict is not None:
            conflicts.append(f"{key}: {conflict}")

    return merged, conflicts
