import math
from typing import List


def rolling_z_score(changes: List[float], current_change: float) -> float | None:
    """
    Z-score of current_change relative to recent changes.
    Returns None if not enough history (e.g. < 2 points for std).
    """
    if not changes or len(changes) < 2:
        return None
    n = len(changes)
    mean = sum(changes) / n
    variance = sum((x - mean) ** 2 for x in changes) / (n - 1) if n > 1 else 0.0
    if variance <= 0:
        return 0.0
    std = math.sqrt(variance)
    return (current_change - mean) / std
