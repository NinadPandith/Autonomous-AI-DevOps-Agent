import pytest

from shopcart.shipping_client import ShippingAPIError, parse_shipping_quote


def test_parse_shipping_quote_returns_cheapest_rate_in_dollars(shipping_ok):
    assert parse_shipping_quote(shipping_ok) == 5.99


def test_parse_shipping_quote_raises_on_error_response():
    response = {"status": "error", "error": {"code": "INVALID_ZIP", "message": "Unknown destination ZIP code"}}
    with pytest.raises(ShippingAPIError, match="Unknown destination ZIP code"):
        parse_shipping_quote(response)
