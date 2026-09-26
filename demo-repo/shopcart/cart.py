from .models import CartItem, Product


class Cart:
    def __init__(self) -> None:
        self.items: dict[str, CartItem] = {}

    @classmethod
    def from_dict(cls, data: dict) -> "Cart":
        """Build a cart from an order payload such as a submitted web form:

            {"items": [{"sku": "MUG-01", "name": "Mug", "price": "12.00", "quantity": "2"}, ...]}

        Form fields arrive as strings, so prices and quantities are converted to numbers.
        The same SKU may appear more than once; its quantities are combined.
        """
        cart = cls()
        for item in data["items"]:
            product = Product(item["sku"], item["name"], float(item["price"]))
            cart.items[product.sku] = CartItem(product, item["quantity"])
        return cart

    def add_item(self, product: Product, quantity: int = 1) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if product.sku in self.items:
            self.items[product.sku].quantity += quantity
        else:
            self.items[product.sku] = CartItem(product, quantity)

    def remove_item(self, sku: str) -> None:
        if sku not in self.items:
            raise KeyError(f"No item with SKU {sku!r} in cart")
        del self.items[sku]

    def update_quantity(self, sku: str, quantity: int) -> None:
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        if quantity == 0:
            self.remove_item(sku)
            return
        self.items[sku].quantity = quantity

    def is_empty(self) -> bool:
        return not self.items

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.values())

    @property
    def subtotal(self) -> float:
        return round(sum(item.line_total for item in self.items.values()), 2)
