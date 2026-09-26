from shopcart.utils import format_currency, paginate

ITEMS = list(range(1, 11))


def test_paginate_first_page():
    assert paginate(ITEMS, page=1, page_size=4) == [1, 2, 3, 4]


def test_paginate_last_partial_page():
    assert paginate(ITEMS, page=3, page_size=4) == [9, 10]


def test_format_currency():
    assert format_currency(1234.5) == "$1,234.50"
