class OutOfStockError(Exception):
    pass


class Inventory:
    def __init__(self, stock: dict[str, int]) -> None:
        self._stock = dict(stock)

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def reserve(self, sku: str, quantity: int) -> None:
        if self.available(sku) < quantity:
            raise OutOfStockError(
                f"Only {self.available(sku)} of {sku} in stock, requested {quantity}"
            )
        self._stock[sku] -= quantity

    def release(self, sku: str, quantity: int) -> None:
        self._stock[sku] = self.available(sku) + quantity
