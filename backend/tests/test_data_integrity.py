"""The project's central rule: missing data stays missing.

A metric the provider did not supply must arrive as `None` and never as `0`.
These tests exist because that distinction is easy to erode — one `or 0` added
in a hurry would turn "this company has no P/E ratio" into "this company has a
P/E ratio of zero", which is a fabricated figure presented as a measurement.
"""

from __future__ import annotations

import math

import pytest

from app.services.providers.base import (
    parse_optional_date,
    parse_optional_float,
    parse_optional_int,
    parse_optional_str,
)


class TestMissingValuesBecomeNone:
    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "   ",
            "-",
            "--",
            "None",
            "none",
            "N/A",
            "n/a",
            "NA",
            "null",
            "NaN",
            "unknown",
        ],
    )
    def test_sentinels_parse_to_none(self, raw: object) -> None:
        assert parse_optional_float(raw) is None
        assert parse_optional_int(raw) is None

    @pytest.mark.parametrize("raw", ["", "  ", "-", "None", "N/A"])
    def test_string_sentinels_parse_to_none(self, raw: str) -> None:
        assert parse_optional_str(raw) is None

    def test_none_is_not_zero(self) -> None:
        """The distinction this whole rule exists to protect."""
        value = parse_optional_float("None")
        assert value is None
        assert value != 0
        assert value is not False


class TestRealValuesParse:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("186.40", 186.40),
            ("1,234.56", 1234.56),  # thousands separator
            ("0.8112%", 0.8112),  # trailing percent
            ("-12.5", -12.5),
            ("0", 0.0),  # a genuine zero survives
            (42, 42.0),
            (3.5, 3.5),
        ],
    )
    def test_numeric_values(self, raw: object, expected: float) -> None:
        assert parse_optional_float(raw) == pytest.approx(expected)

    def test_genuine_zero_is_preserved(self) -> None:
        """A real zero must not be mistaken for missing data."""
        assert parse_optional_float("0") == 0.0
        assert parse_optional_float("0") is not None

    def test_large_integers(self) -> None:
        assert parse_optional_int("2900000000000") == 2_900_000_000_000


class TestNonFiniteRejected:
    """`inf` and `nan` would silently poison every downstream calculation."""

    @pytest.mark.parametrize("raw", [math.inf, -math.inf, math.nan, "inf", "-inf"])
    def test_non_finite_becomes_none(self, raw: object) -> None:
        assert parse_optional_float(raw) is None

    def test_booleans_are_not_numbers(self) -> None:
        """`True` is an int in Python; treating it as 1.0 would be nonsense."""
        assert parse_optional_float(True) is None
        assert parse_optional_float(False) is None


class TestDateParsing:
    def test_iso_date(self) -> None:
        parsed = parse_optional_date("2026-07-24")
        assert parsed is not None
        assert (parsed.year, parsed.month, parsed.day) == (2026, 7, 24)

    @pytest.mark.parametrize("raw", ["", "None", "not-a-date", "2026-13-45"])
    def test_invalid_dates_become_none(self, raw: str) -> None:
        assert parse_optional_date(raw) is None
