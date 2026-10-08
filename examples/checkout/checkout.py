"""Small, intentionally buggy checkout module used by the offline demonstration."""


def calculate_total(price: float, discount: float | None = None) -> float:
    """Apply a percentage discount; an omitted discount defaults to ten percent."""
    effective_discount = discount or 10
    return round(price * (1 - effective_discount / 100), 2)
