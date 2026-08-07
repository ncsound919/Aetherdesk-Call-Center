"""Canonical pricing catalog for AetherDesk rental billing.

Single source of truth for:
  - Rental periods (concurrent agent capacity rented for a duration)
  - Included call minutes per rental (40 min per agent-hour)
  - Per-minute rates for BYOK vs managed DeepSeek
  - Prepaid top-up minute packs

Stripe Prices are resolved from environment variables (see `price_key_to_env`),
which lets ops configure Stripe price IDs without code changes. When Stripe is
unconfigured the checkout service falls back to mock mode.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, UTC

# Per-minute prepaid rates (USD) by AI mode.
RATE_PER_MINUTE = {
    "byok": 0.03,
    "deepseek": 0.05,
}

# Prepaid top-up packs (minutes) available in any mode.
TOPUP_PACKS = [100, 500, 1000, 5000]

# Minutes included per agent-hour of a rental.
MINUTES_PER_AGENT_HOUR = 40


@dataclass(frozen=True)
class RentalPeriod:
    key: str
    label: str
    hours: int
    price: float
    included_minutes: int

    @property
    def effective_hourly(self) -> float:
        return round(self.price / self.hours, 2)


PERIODS: list[RentalPeriod] = [
    RentalPeriod("hour", "1 Hour", 1, 2.00, MINUTES_PER_AGENT_HOUR),
    RentalPeriod("four_hour", "4 Hours", 4, 7.20, 4 * MINUTES_PER_AGENT_HOUR),
    RentalPeriod("day", "8 Hours (Day)", 8, 13.30, 8 * MINUTES_PER_AGENT_HOUR),
    RentalPeriod("week", "1 Week", 40, 64.00, 40 * MINUTES_PER_AGENT_HOUR),
    RentalPeriod("month", "1 Month", 176, 239.00, 176 * MINUTES_PER_AGENT_HOUR),
    RentalPeriod("quarter", "3 Months", 528, 644.00, 528 * MINUTES_PER_AGENT_HOUR),
    RentalPeriod("half_year", "6 Months", 1056, 1204.00, 1056 * MINUTES_PER_AGENT_HOUR),
    RentalPeriod("year", "1 Year", 2112, 2239.00, 2112 * MINUTES_PER_AGENT_HOUR),
]

PERIODS_BY_KEY: dict[str, RentalPeriod] = {p.key: p for p in PERIODS}


def get_period(key: str) -> RentalPeriod | None:
    """Return a rental period by key, or None."""
    return PERIODS_BY_KEY.get(key)


def topup_price(pack: int, mode: str) -> float | None:
    """Return the USD price for a top-up pack in a mode, or None if invalid."""
    if pack not in TOPUP_PACKS:
        return None
    rate = RATE_PER_MINUTE.get(mode)
    if rate is None:
        return None
    return round(pack * rate, 2)


def rental_duration(key: str) -> timedelta:
    """Return the wall-clock duration of a rental period."""
    period = PERIODS_BY_KEY[key]
    return timedelta(hours=period.hours)


def rental_window(key: str, start: datetime | None = None) -> tuple[datetime, datetime]:
    """Return (rental_start, rental_end) for a period from an optional start."""
    start = start or datetime.now(UTC)
    return start, start + rental_duration(key)


def catalog() -> dict:
    """Public, serializable pricing catalog for GET /billing/plans."""
    return {
        "rental_periods": [
            {
                "key": p.key,
                "label": p.label,
                "hours": p.hours,
                "price": p.price,
                "effective_hourly": p.effective_hourly,
                "included_minutes": p.included_minutes,
            }
            for p in PERIODS
        ],
        "rates_per_minute": RATE_PER_MINUTE,
        "topup_packs": {
            str(pack): {
                "minutes": pack,
                "price": topup_price(pack, mode),
            }
            for pack in TOPUP_PACKS
            for mode in RATE_PER_MINUTE
        },
        "minutes_per_agent_hour": MINUTES_PER_AGENT_HOUR,
    }


# --- Stripe price env mapping -----------------------------------------------

RENTAL_PRICE_ENV = "STRIPE_PRICE_RENTAL_{}"
TOPUP_PRICE_ENV = "STRIPE_PRICE_TOPUP_{}_{}"


def rental_price_env(key: str) -> str:
    return RENTAL_PRICE_ENV.format(key.upper())


def topup_price_env(pack: int, mode: str) -> str:
    return TOPUP_PRICE_ENV.format(pack, mode.upper())
