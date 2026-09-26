from datetime import date

from shopcart.models import Coupon
from shopcart.pricing import (
    apply_percentage_discount,
    bulk_discount_rate,
    find_coupon,
    is_coupon_valid,
)


def test_apply_percentage_discount():
    assert apply_percentage_discount(200.00, 15) == 170.00


def test_bulk_discount_applies_at_exactly_ten_units():
    assert bulk_discount_rate(10) == 0.05


def test_bulk_discount_not_applied_below_threshold():
    assert bulk_discount_rate(9) == 0.0


def test_find_coupon_ignores_case_and_whitespace(coupons):
    assert find_coupon("  save20 ", coupons) == coupons["SAVE20"]


def test_find_coupon_returns_none_when_no_code_given(coupons):
    assert find_coupon(None, coupons) is None


def test_coupon_valid_through_expiry_day():
    coupon = Coupon("JAN", 10, date(2026, 1, 31))
    assert is_coupon_valid(coupon, date(2026, 1, 31))
    assert not is_coupon_valid(coupon, date(2026, 2, 1))
