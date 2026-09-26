def paginate(items: list, page: int, page_size: int) -> list:
    """Return one page of `items`. Pages are 1-indexed."""
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be at least 1")
    start = page * page_size
    return items[start:start + page_size]


def format_currency(amount: float) -> str:
    return f"${amount:,.2f}"
