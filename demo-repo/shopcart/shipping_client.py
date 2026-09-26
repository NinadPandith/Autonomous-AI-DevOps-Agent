"""Helpers for the carrier-rates HTTP API.

Successful responses look like:
    {"status": "ok", "data": {"rates": [{"carrier": "UPS", "amount_cents": 899}, ...]}}

Failed responses look like:
    {"status": "error", "error": {"code": "INVALID_ZIP", "message": "Unknown destination ZIP code"}}
"""

FREE_SHIPPING_THRESHOLD = 50.00  # dollars, applied to the order after discounts


class ShippingAPIError(Exception):
    pass


def parse_shipping_quote(response: dict) -> float:
    """Return the cheapest shipping rate in the response, in dollars.

    Raises ShippingAPIError if the API reported an error or returned no rates.
    """
    rates = response["data"]["rates"]
    if not rates:
        raise ShippingAPIError("No shipping rates available")
    cheapest_cents = min(rate["amount_cents"] for rate in rates)
    return round(cheapest_cents / 100, 2)
