from datetime import date

from .models import CartItem, Coupon

BULK_THRESHOLD = 10  # units of a single product
BULK_DISCOUNT = 0.05  # 5% off that line


def apply_percentage_discount(amount: float, percent: float) -> float:
    """Reduce `amount` by `percent`, given as a whole number (15 means 15%)."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(amount * (1 - percent / 100), 2)


def bulk_discount_rate(quantity: int) -> float:
    """Lines with BULK_THRESHOLD or more units get BULK_DISCOUNT off."""
    return BULK_DISCOUNT if quantity > BULK_THRESHOLD else 0.0


def line_total_with_bulk(item: CartItem) -> float:
    return round(item.line_total * (1 - bulk_discount_rate(item.quantity)), 2)


def find_coupon(code: str | None, coupons: dict[str, Coupon]) -> Coupon | None:
    """Look up a coupon by code, ignoring case and surrounding whitespace.

    Returns None when no code was given or the code is unknown.
    """
    return coupons.get(code.strip().upper())


def is_coupon_valid(coupon: Coupon, today: date) -> bool:
    return today <= coupon.expires_on


def calculate_tax(amount: float, rate: float) -> float:
    """Tax on `amount`, rounded half-up to the cent as tax authorities require (e.g. $0.125 -> $0.13)."""
    return round(amount * rate, 2)
