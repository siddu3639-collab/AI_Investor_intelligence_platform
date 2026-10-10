import pytest

from app.services.kpi_service import parse_kpi_response


def test_numbers_inside_strings_are_cleaned():
    data = parse_kpi_response('{"revenue": "1,234.5", "net_income": "(310)", "debt": null}')
    assert data.revenue == 1234.5
    assert data.net_income == -310
    assert data.debt is None


def test_markdown_fences_are_tolerated():
    data = parse_kpi_response('```json\n{"eps": 3.42}\n```')
    assert data.eps == 3.42


def test_net_margin_is_recomputed_not_trusted():
    data = parse_kpi_response('{"revenue": 1000, "net_income": 100, "net_margin": 55}')
    assert data.net_margin == 10.0


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_kpi_response("I could not find any KPIs.")


def test_unparseable_value_becomes_none():
    assert parse_kpi_response('{"revenue": "n/a"}').revenue is None
