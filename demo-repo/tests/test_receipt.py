from shopcart.cart import Cart
from shopcart.receipt import format_receipt

from .conftest import MUG, PEN


def test_format_receipt_lists_each_line():
    cart = Cart()
    cart.add_item(MUG, 2)
    assert format_receipt(cart) == ["2 x Mug @ $12.00 = $24.00", "Subtotal: $24.00"]


def test_receipts_for_different_carts_are_independent():
    cart_a = Cart()
    cart_a.add_item(MUG, 1)
    cart_b = Cart()
    cart_b.add_item(PEN, 1)

    format_receipt(cart_a)
    assert format_receipt(cart_b) == ["1 x Pen @ $1.50 = $1.50", "Subtotal: $1.50"]
