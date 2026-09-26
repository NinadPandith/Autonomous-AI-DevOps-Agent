"""Loyalty points: customers earn points on what they spend and redeem them for store credit."""
import math

POINTS_PER_DOLLAR = 1  # one point per whole dollar spent; fractions of a dollar earn nothing
POINT_VALUE = 0.05  # each point is worth 5 cents of store credit
REDEEM_BLOCK = 100  # points are redeemed in blocks of 100


class InsufficientPoints(Exception):
    pass


class LoyaltyAccount:
    def __init__(self) -> None:
        self.points = 0

    def earn(self, amount_spent: float) -> int:
        """Credit points for a purchase and return how many were earned."""
        earned = round(amount_spent * POINTS_PER_DOLLAR)
        self.points += earned
        return earned

    def redeem(self, points: int) -> float:
        """Spend `points` (a positive multiple of REDEEM_BLOCK); return the store credit in dollars."""
        if points <= 0 or points % REDEEM_BLOCK:
            raise ValueError(f"Points must be a positive multiple of {REDEEM_BLOCK}")
        if points > self.points:
            raise InsufficientPoints(f"Only {self.points} points available")
        self.points -= points
        return round(points // REDEEM_BLOCK * POINT_VALUE, 2)
