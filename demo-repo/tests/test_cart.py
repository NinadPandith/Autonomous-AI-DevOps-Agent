from shopcart.cart import Cart

from .conftest import LAMP, MUG, SOCKS


def test_add_same_product_merges_quantity():
    cart = Cart()
    cart.add_item(SOCKS, 2)
    cart.add_item(SOCKS, 3)
    assert len(cart.items) == 1
    assert cart.item_count == 5


def test_update_quantity_to_zero_removes_item():
    cart = Cart()
    cart.add_item(LAMP, 1)
    cart.update_quantity(LAMP.sku, 0)
    assert cart.is_empty()


def test_subtotal_sums_line_totals():
    cart = Cart()
    cart.add_item(MUG, 2)
    cart.add_item(SOCKS, 1)
    assert cart.subtotal == 39.00
