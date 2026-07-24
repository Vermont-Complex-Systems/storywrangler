"""
Zero-padding of time-partition path segments (_format_tp_value).

Regression: a corpus whose first on-disk month is December registers
month raw_value='12'. The old "pad only when the sample starts with 0" rule
then rendered January as 'month=1', a path that matches no 'month=01'
directory — so instruments (top-ngrams/allotax/rtd/wordshift) returned empty
for mid-month single dates on reddit/bluesky. Width comes from the sample, not
a leading zero.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.duckdb_query import _format_tp_value, derive_time_partitions


def _month(raw):
    return {"column": "month", "type": "time_partition", "raw_value": raw}


class TestFormatTpValue:
    def test_two_wide_sample_pads_single_digit(self):
        # The bug: first data month is December → raw '12' → Jan must be '01'.
        assert _format_tp_value(1, _month("12")) == "01"
        assert _format_tp_value(9, _month("12")) == "09"
        assert _format_tp_value(12, _month("12")) == "12"

    def test_leading_zero_sample_still_pads(self):
        assert _format_tp_value(1, _month("03")) == "01"

    def test_one_wide_sample_stays_unpadded(self):
        # Genuinely unpadded layout (dirs '1'..'12'): a 1-wide sample is a no-op,
        # and a naturally-2-wide value keeps its width.
        assert _format_tp_value(1, _month("3")) == "1"
        assert _format_tp_value(12, _month("3")) == "12"

    def test_year_four_wide(self):
        yr = {"column": "year", "type": "time_partition", "raw_value": "2024"}
        assert _format_tp_value(2025, yr) == "2025"

    def test_missing_raw_value_falls_back_to_convention(self):
        # Pre-raw_value datasets: month/day use the conventional 2-digit width.
        assert _format_tp_value(3, {"column": "month", "type": "time_partition"}) == "03"


class TestDeriveTimePartitionsPinnedMonth:
    LEVELS = [
        {"column": "year", "type": "time_partition", "raw_value": "2024"},
        {"column": "month", "type": "time_partition", "raw_value": "12"},
    ]

    def test_midmonth_single_date_pins_padded_month(self):
        # ±6-day pad stays inside one month → month pinned in the path, and it
        # must be zero-padded to match month=01 on disk.
        pv, cond, params = derive_time_partitions(["2025-01-15", "2025-01-15"], self.LEVELS)
        assert pv == {"year": "2025", "month": "01"}
        assert cond == [] and params == []

    def test_cross_month_pad_uses_where_in(self):
        # Near a month edge the pad spans two months → WHERE IN (ints), which
        # DuckDB coerces against the varchar partitions; month stays a wildcard.
        pv, cond, params = derive_time_partitions(["2025-03-01", "2025-03-01"], self.LEVELS)
        assert "month" not in pv
        assert cond == ["month IN (?,?)"] and params == [2, 3]
