"""Tests for generic Cedar attribute helpers."""

from authorization_in_the_middle.cedar_attrs import tier1_actor_flags


def test_tier1_actor_flags():
    flags = tier1_actor_flags(
        ["clinician", "operator"],
        frozenset({"clinician", "operator", "study"}),
    )
    assert flags["isClinician"] is True
    assert flags["isOperator"] is True
    assert flags["isStudy"] is False
