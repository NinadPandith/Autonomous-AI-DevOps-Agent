from datetime import date

import pytest

from shopcart.models import Coupon, Product

LAMP = Product("LAMP-01", "Desk Lamp", 100.00)
SCARF = Product("SCARF-01", "Wool Scarf", 55.00)
SOCKS = Product("SOCKS-01", "Socks", 15.00)
PEN = Product("PEN-01", "Pen", 1.50)
MUG = Product("MUG-01", "Mug", 12.00)

TODAY = date(2026, 9, 26)


@pytest.fixture
def coupons():
    return {"SAVE20": Coupon("SAVE20", 20, date(2026, 12, 31))}


@pytest.fixture
def shipping_ok():
    return {
        "status": "ok",
        "data": {"rates": [{"carrier": "UPS", "amount_cents": 899}, {"carrier": "USPS", "amount_cents": 599}]},
    }
