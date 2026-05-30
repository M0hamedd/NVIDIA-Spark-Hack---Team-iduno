from __future__ import annotations

import math
import re
from typing import Iterable


def normalize_name(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", "and")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9 /'.-]", "", text)
    return text


def to_number(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def minmax(value: float, values: Iterable[float]) -> float:
    numbers = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not numbers:
        return 0.0
    low = min(numbers)
    high = max(numbers)
    if math.isclose(low, high):
        return 50.0 if value > 0 else 0.0
    return clamp(((value - low) / (high - low)) * 100.0)


def safe_divide(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return numerator / denominator


def log_signal(value: float) -> float:
    return math.log1p(max(0.0, value))
