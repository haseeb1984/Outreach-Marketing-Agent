from __future__ import annotations

from app.api.account_routes import _bounded_export_rows


def test_bounded_export_rows_marks_truncation_only_when_extra_row_exists():
    rows = [{"id": value} for value in range(4)]

    exported, truncated = _bounded_export_rows(rows, limit=3)

    assert exported == rows[:3]
    assert truncated is True


def test_bounded_export_rows_does_not_mark_exact_limit_as_truncated():
    rows = [{"id": value} for value in range(3)]

    exported, truncated = _bounded_export_rows(rows, limit=3)

    assert exported == rows
    assert truncated is False


def test_bounded_export_rows_rejects_invalid_limit():
    import pytest

    with pytest.raises(ValueError, match="limit_must_be_positive"):
        _bounded_export_rows([], limit=0)


def test_bounded_export_rows_rejects_boolean_limit():
    import pytest

    with pytest.raises(ValueError, match="limit_must_be_positive"):
        _bounded_export_rows([{"id": 1}], limit=True)


def test_bounded_export_rows_keeps_source_rows_unchanged():
    rows = [{"id": value} for value in range(5)]
    original = list(rows)

    exported, truncated = _bounded_export_rows(rows, limit=2)

    assert exported == rows[:2]
    assert truncated is True
    assert rows == original


def test_bounded_export_rows_supports_empty_collection():
    exported, truncated = _bounded_export_rows([], limit=10)

    assert exported == []
    assert truncated is False
