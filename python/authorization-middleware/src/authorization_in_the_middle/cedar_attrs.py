"""Generic Cedar attribute helpers (no service-specific field maps)."""

from __future__ import annotations


def tier1_actor_flags(
    actors: list[str],
    actor_classes: frozenset[str],
) -> dict[str, bool]:
    """Cedar booleans ``isClinician``, ``isOperator``, … from JWT actor list."""
    jwt_set = set(actors)
    flags: dict[str, bool] = {}
    for actor in actor_classes:
        flags[f"is{actor[0].upper()}{actor[1:]}"] = actor in jwt_set
    return flags
