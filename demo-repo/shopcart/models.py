from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: float  # unit price in dollars


@dataclass
class CartItem:
    product: Product
    quantity: int

    @property
    def line_total(self) -> float:
        return round(self.product.price * self.quantity, 2)


@dataclass(frozen=True)
class Coupon:
    code: str
    percent_off: int  # whole-number percentage, e.g. 15 means 15% off
    expires_on: date  # last day the coupon can be used
