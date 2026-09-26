import pytest

from shopcart.loyalty import InsufficientPoints, LoyaltyAccount


def test_points_round_trip():
    account = LoyaltyAccount()
    assert account.earn(99.99) == 99
    assert account.earn(1.50) == 1
    assert account.points == 100
    assert account.redeem(100) == 5.00
    assert account.points == 0


def test_redeem_requires_whole_blocks():
    account = LoyaltyAccount()
    account.earn(250)
    with pytest.raises(ValueError):
        account.redeem(150)


def test_cannot_redeem_more_than_balance():
    account = LoyaltyAccount()
    account.earn(50)
    with pytest.raises(InsufficientPoints):
        account.redeem(100)
