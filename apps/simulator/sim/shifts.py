"""Shift calendar: which shift is active at a UTC instant, and when the next change happens."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sim.catalog import ShiftSpec

SEARCH_DAYS = 8


class ShiftCalendar:
    def __init__(self, shifts: list[ShiftSpec], working_days: list[int], timezone: str) -> None:
        self.shifts = shifts
        self.working_days = set(working_days)
        self.tz = ZoneInfo(timezone)

    def _instances(
        self, first_day: datetime, days: int
    ) -> list[tuple[ShiftSpec, datetime, datetime]]:
        """Shift occurrences starting on working days; a shift belongs to the day it starts."""
        out = []
        for offset in range(days):
            day = first_day + timedelta(days=offset)
            if day.weekday() not in self.working_days:
                continue
            for shift in self.shifts:
                start = datetime.combine(day.date(), shift.start, self.tz)
                end = datetime.combine(day.date(), shift.end, self.tz)
                if end <= start:
                    end += timedelta(days=1)
                out.append((shift, start, end))
        return out

    def active(self, t: datetime) -> ShiftSpec | None:
        local = t.astimezone(self.tz)
        for shift, start, end in self._instances(local - timedelta(days=1), 2):
            if start <= local < end:
                return shift
        return None

    def next_change(self, t: datetime) -> datetime:
        local = t.astimezone(self.tz)
        boundaries = [
            edge
            for _, start, end in self._instances(local - timedelta(days=1), SEARCH_DAYS)
            for edge in (start, end)
            if edge > local
        ]
        return min(boundaries) if boundaries else local + timedelta(days=1)
