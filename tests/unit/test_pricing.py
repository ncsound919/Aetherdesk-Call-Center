"""Unit tests for the canonical pricing catalog."""

import pytest

from api.services import pricing


def test_catalog_has_eight_periods():
    cat = pricing.catalog()
    assert len(cat["rental_periods"]) == 8


def test_hour_period_values():
    p = pricing.get_period("hour")
    assert p.price == 2.00
    assert p.included_minutes == 40
    assert p.effective_hourly == 2.00


def test_minutes_scale_at_forty_per_hour():
    assert pricing.get_period("hour").included_minutes == 40
    assert pricing.get_period("day").included_minutes == 320
    assert pricing.get_period("month").included_minutes == 7040
    assert pricing.get_period("year").included_minutes == 84480


def test_period_prices_and_effective_hourly():
    expected = {
        "four_hour": (7.20, 1.80),
        "day": (13.30, 1.66),
        "week": (64.00, 1.60),
        "month": (239.00, 1.36),
        "quarter": (644.00, 1.22),
        "half_year": (1204.00, 1.14),
        "year": (2239.00, 1.06),
    }
    for key, (price, hourly) in expected.items():
        p = pricing.get_period(key)
        assert p.price == price
        assert p.effective_hourly == hourly


def test_unknown_period_returns_none():
    assert pricing.get_period("bogus") is None


def test_per_minute_rates():
    assert pricing.RATE_PER_MINUTE == {"byok": 0.03, "deepseek": 0.05}


def test_topup_prices_by_mode():
    assert pricing.topup_price(100, "byok") == 3.0
    assert pricing.topup_price(100, "deepseek") == 5.0
    assert pricing.topup_price(1000, "deepseek") == 50.0
    assert pricing.topup_price(5000, "byok") == 150.0


def test_topup_invalid_pack_or_mode():
    assert pricing.topup_price(12345, "byok") is None
    assert pricing.topup_price(100, "bogus") is None


def test_rental_window_duration():
    start, end = pricing.rental_window("hour")
    assert (end - start).total_seconds() == 3600


def test_rental_window_year():
    start, end = pricing.rental_window("year")
    assert (end - start).days == 2112 // 24


def test_price_env_keys():
    assert pricing.rental_price_env("hour") == "STRIPE_PRICE_RENTAL_HOUR"
    assert pricing.topup_price_env(1000, "deepseek") == "STRIPE_PRICE_TOPUP_1000_DEEPSEEK"
