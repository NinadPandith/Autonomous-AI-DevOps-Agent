import pytest

from shopcart.cart import Cart
from shopcart.checkout import OrderSummary, checkout
from shopcart.inventory import Inventory, OutOfStockError

from .conftest import LAMP, PEN, SCARF, SOCKS, TODAY


def stocked_inventory():
    return Inventory({LAMP.sku: 50, SCARF.sku: 50, SOCKS.sku: 50, PEN.sku: 50})


def test_checkout_rejects_empty_cart(shipping_ok):
    with pytest.raises(ValueError):
        checkout(Cart(), stocked_inventory(), shipping_ok, today=TODAY)


def test_checkout_without_coupon_charges_shipping(shipping_ok):
    cart = Cart()
    cart.add_item(SOCKS, 2)
    summary = checkout(cart, stocked_inventory(), shipping_ok, today=TODAY)
    assert summary == OrderSummary(subtotal=30.00, discount=0.00, tax=2.40, shipping=5.99, total=38.39)


def test_checkout_applies_percentage_coupon(shipping_ok, coupons):
    cart = Cart()
    cart.add_item(LAMP, 1)
    summary = checkout(cart, stocked_inventory(), shipping_ok, "SAVE20", coupons, today=TODAY)
    assert summary == OrderSummary(subtotal=100.00, discount=20.00, tax=6.40, shipping=0.00, total=86.40)


def test_free_shipping_threshold_uses_discounted_total(shipping_ok, coupons):
    # $55 qualifies for free shipping, but after 20% off it's $44 — shipping must be charged.
    cart = Cart()
    cart.add_item(SCARF, 1)
    summary = checkout(cart, stocked_inventory(), shipping_ok, "SAVE20", coupons, today=TODAY)
    assert summary == OrderSummary(subtotal=55.00, discount=11.00, tax=3.52, shipping=5.99, total=53.51)


def test_checkout_applies_bulk_discount(shipping_ok):
    cart = Cart()
    cart.add_item(PEN, 10)  # $15.00, 5% bulk discount -> $14.25
    summary = checkout(cart, stocked_inventory(), shipping_ok, today=TODAY)
    assert summary == OrderSummary(subtotal=14.25, discount=0.00, tax=1.14, shipping=5.99, total=21.38)


def test_failed_checkout_releases_reserved_stock(shipping_ok):
    cart = Cart()
    cart.add_item(LAMP, 2)
    cart.add_item(SOCKS, 3)
    inventory = Inventory({LAMP.sku: 5, SOCKS.sku: 1})

    with pytest.raises(OutOfStockError):
        checkout(cart, inventory, shipping_ok, today=TODAY)

    assert inventory.available(LAMP.sku) == 5
    assert inventory.available(SOCKS.sku) == 1
