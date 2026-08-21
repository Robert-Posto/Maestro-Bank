"""Teste pentru app/tools/registry.py::_to_minor — singurul loc unde se
face conversia RON -> bani/subunități (GPT trimite mereu lei, nu bani)."""

import pytest

from app.tools.registry import _to_minor
from app.tools.errors import ToolError


def test_to_minor_converts_whole_number():
    assert _to_minor(2000, "x") == 200000


def test_to_minor_converts_decimal():
    assert _to_minor(799.99, "x") == 79999


def test_to_minor_accepts_numeric_string():
    # unele modele trimit uneori numărul ca string în JSON — tot valid.
    assert _to_minor("500", "x") == 50000


def test_to_minor_rejects_non_numeric_value():
    with pytest.raises(ToolError):
        _to_minor("mult", "requested_amount_ron")


def test_to_minor_rejects_none():
    with pytest.raises(ToolError):
        _to_minor(None, "requested_amount_ron")
