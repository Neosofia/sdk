"""Tier-1 actor allow-list helpers for JWT middleware and services."""


def parse_tier1_actor_classes(valid_actors: str) -> frozenset[str]:
    """Parse comma-separated VALID_ACTORS into a frozenset."""
    return frozenset(part.strip() for part in valid_actors.split(",") if part.strip())
