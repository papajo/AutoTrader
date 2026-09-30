"""Pure mathematical ephemeris calculation of lunar phases."""

from __future__ import annotations
import math
from datetime import date, datetime, timezone
from typing import List, Tuple


class LunarEphemeris:
    """Computes exact lunar phase angles and new/full moon dates using astronomical algorithms."""

    # Reference epoch: 2000-01-06 18:14 UTC (Known New Moon)
    SYNODIC_MONTH = 29.53058867  # Mean synodic month in days
    KNOWN_NEW_MOON_JD = 2451549.26  # Julian Day of 2000-01-06 18:14 UTC

    @staticmethod
    def datetime_to_julian_day(dt: datetime) -> float:
        """Convert a UTC datetime to astronomical Julian Day."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        year = dt.year
        month = dt.month
        day = dt.day + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0

        if month <= 2:
            year -= 1
            month += 12

        A = math.floor(year / 100.0)
        B = 2 - A + math.floor(A / 4.0)

        jd = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5
        return jd

    @classmethod
    def get_phase_fraction(cls, dt: datetime) -> float:
        """Get moon cycle fraction from 0.0 (New Moon) to 0.5 (Full Moon) to 1.0 (Next New Moon)."""
        jd = cls.datetime_to_julian_day(dt)
        diff_days = jd - cls.KNOWN_NEW_MOON_JD
        cycles = diff_days / cls.SYNODIC_MONTH
        fraction = cycles - math.floor(cycles)
        return fraction

    @classmethod
    def is_new_moon(cls, dt: datetime, tolerance_days: float = 0.75) -> bool:
        """Check if date is within tolerance of a New Moon."""
        frac = cls.get_phase_fraction(dt)
        phase_days = frac * cls.SYNODIC_MONTH
        return (phase_days <= tolerance_days) or (phase_days >= cls.SYNODIC_MONTH - tolerance_days)

    @classmethod
    def is_full_moon(cls, dt: datetime, tolerance_days: float = 0.75) -> bool:
        """Check if date is within tolerance of a Full Moon."""
        frac = cls.get_phase_fraction(dt)
        phase_days = frac * cls.SYNODIC_MONTH
        half_cycle = cls.SYNODIC_MONTH / 2.0
        return abs(phase_days - half_cycle) <= tolerance_days
