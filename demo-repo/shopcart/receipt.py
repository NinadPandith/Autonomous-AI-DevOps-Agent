from .cart import Cart
from .utils import format_currency


def format_receipt(cart: Cart, lines: list[str] = []) -> list[str]:
    """Render one line per cart item followed by the subtotal.

    Pass `lines` to append to an existing receipt (e.g. one with a header).
    """
    for item in cart.items.values():
        lines.append(
            f"{item.quantity} x {item.product.name} @ {format_currency(item.product.price)}"
            f" = {format_currency(item.line_total)}"
        )
    lines.append(f"Subtotal: {format_currency(cart.subtotal)}")
    return lines
