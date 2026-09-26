from dataclasses import dataclass
from datetime import date

from .cart import Cart
from .inventory import Inventory
from .models import Coupon
from .pricing import (
    apply_percentage_discount,
    calculate_tax,
    find_coupon,
    is_coupon_valid,
    line_total_with_bulk,
)
from .shipping_client import FREE_SHIPPING_THRESHOLD, parse_shipping_quote

TAX_RATE = 0.08


@dataclass
class OrderSummary:
    subtotal: float
    discount: float
    tax: float
    shipping: float
    total: float


def checkout(
    cart: Cart,
    inventory: Inventory,
    shipping_response: dict,
    coupon_code: str | None = None,
    coupons: dict[str, Coupon] | None = None,
    today: date | None = None,
) -> OrderSummary:
    """Reserve stock for every item and price the order.

    Order of operations: bulk discounts -> coupon -> tax -> shipping.
    If any item is out of stock, no stock stays reserved and OutOfStockError is raised.
    """
    if cart.is_empty():
        raise ValueError("Cannot check out an empty cart")
    today = today or date.today()
    coupons = coupons or {}

    for item in cart.items.values():
        inventory.reserve(item.product.sku, item.quantity)

    subtotal = round(sum(line_total_with_bulk(item) for item in cart.items.values()), 2)

    discounted = subtotal
    coupon = find_coupon(coupon_code, coupons)
    if coupon and is_coupon_valid(coupon, today):
        discounted = apply_percentage_discount(subtotal, coupon.percent_off / 100)
    discount = round(subtotal - discounted, 2)

    tax = calculate_tax(discounted, TAX_RATE)

    if subtotal >= FREE_SHIPPING_THRESHOLD:
        shipping = 0.0
    else:
        shipping = parse_shipping_quote(shipping_response)

    total = round(discounted + tax + shipping, 2)
    return OrderSummary(subtotal, discount, tax, shipping, total)
