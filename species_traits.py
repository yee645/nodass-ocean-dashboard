"""Target fish species traits and habitat scoring helpers.

The dashboard uses these traits as the canonical species data source.
Temperature is still the main signal, but each species now also carries
preferences for thermal fronts, current speed, seasonality, depth, and region.
"""

from __future__ import annotations

from math import exp
from typing import Any


SPECIES: list[dict[str, Any]] = [
    {
        "name": "鬼頭刀",
        "en": "Mahi-mahi",
        "sci": "Coryphaena hippurus",
        "sst_min": 21,
        "opt_lo": 25,
        "opt_hi": 28,
        "sst_max": 31,
        "season": [3, 4, 5, 6, 10, 11],
        "region": "東部黑潮流域、離岸暖水鋒面",
        "depth": "表層",
        "habit": "表層洄游性掠食魚，常追捕飛魚，偏好暖水、流速與鋒面交會帶。",
        "front_opt": 2.4,
        "front_max": 5.0,
        "current_opt": 0.45,
        "current_max": 1.2,
        "temp_sigma": 1.15,
        "season_floor": 0.45,
        "weights": {"sst": 0.58, "front": 0.18, "current": 0.14, "season": 0.10},
        "signals": ["暖水", "黑潮", "表層洄游", "鋒面", "流速"],
    },
    {
        "name": "太平洋黑鮪",
        "en": "Pacific bluefin tuna",
        "sci": "Thunnus orientalis",
        "sst_min": 16,
        "opt_lo": 18,
        "opt_hi": 22,
        "sst_max": 25,
        "season": [4, 5, 6],
        "region": "東部外海、東港外海、黑潮邊緣較冷水團",
        "depth": "中表層",
        "habit": "大洋洄游魚，偏好較涼水團與溫度梯度，端午前後黑鮪季為重要漁期。",
        "front_opt": 2.8,
        "front_max": 5.5,
        "current_opt": 0.35,
        "current_max": 1.0,
        "temp_sigma": 1.1,
        "season_floor": 0.40,
        "weights": {"sst": 0.62, "front": 0.20, "current": 0.08, "season": 0.10},
        "signals": ["冷水團", "溫度梯度", "黑潮邊緣", "中表層"],
    },
    {
        "name": "黃鰭鮪",
        "en": "Yellowfin tuna",
        "sci": "Thunnus albacares",
        "sst_min": 20,
        "opt_lo": 24,
        "opt_hi": 28,
        "sst_max": 31,
        "season": [1, 2, 3, 4, 11, 12],
        "region": "東部與南部外海、黑潮與暖水大洋域",
        "depth": "表至中層",
        "habit": "暖水大洋性魚種，常隨黑潮分布，群游追食小魚與頭足類。",
        "front_opt": 2.2,
        "front_max": 5.0,
        "current_opt": 0.40,
        "current_max": 1.1,
        "temp_sigma": 1.35,
        "season_floor": 0.50,
        "weights": {"sst": 0.55, "front": 0.18, "current": 0.12, "season": 0.15},
        "signals": ["暖水", "黑潮", "大洋洄游", "餌料聚集"],
    },
    {
        "name": "正鰹",
        "en": "Skipjack tuna",
        "sci": "Katsuwonus pelamis",
        "sst_min": 20,
        "opt_lo": 24,
        "opt_hi": 29,
        "sst_max": 31,
        "season": [4, 5, 6, 7, 8, 9],
        "region": "東部與東北部外海、黑潮流域",
        "depth": "表層",
        "habit": "暖水群游性魚種，表層成大群，對流速與餌料聚集敏感。",
        "front_opt": 2.0,
        "front_max": 4.5,
        "current_opt": 0.35,
        "current_max": 1.0,
        "temp_sigma": 1.45,
        "season_floor": 0.55,
        "weights": {"sst": 0.52, "front": 0.18, "current": 0.15, "season": 0.15},
        "signals": ["暖水", "表層群游", "黑潮", "鋒面"],
    },
    {
        "name": "白帶魚",
        "en": "Largehead hairtail",
        "sci": "Trichiurus japonicus",
        "sst_min": 16,
        "opt_lo": 19,
        "opt_hi": 23,
        "sst_max": 26,
        "season": [3, 4, 5, 6, 7, 8],
        "region": "東北部、台灣海峽、西南部陸棚",
        "depth": "底層 60-100m，夜間上浮",
        "habit": "暖溫性底棲魚，晝沉夜浮，常見於陸棚與較緩流海域。",
        "front_opt": 1.4,
        "front_max": 4.0,
        "current_opt": 0.18,
        "current_max": 0.8,
        "temp_sigma": 1.25,
        "season_floor": 0.50,
        "weights": {"sst": 0.60, "front": 0.16, "current": 0.10, "season": 0.14},
        "signals": ["陸棚", "底層", "夜間上浮", "緩流"],
    },
    {
        "name": "白腹鯖(花飛)",
        "en": "Chub mackerel",
        "sci": "Scomber japonicus",
        "sst_min": 14,
        "opt_lo": 17,
        "opt_hi": 20,
        "sst_max": 23,
        "season": [10, 11, 12, 1, 2, 3],
        "region": "東北部南方澳、蘇澳與較冷表中層水域",
        "depth": "表至中層",
        "habit": "溫水群游性魚種，秋冬為盛漁期，偏好較冷水與餌料聚集。",
        "front_opt": 1.8,
        "front_max": 4.5,
        "current_opt": 0.28,
        "current_max": 0.9,
        "temp_sigma": 1.05,
        "season_floor": 0.35,
        "weights": {"sst": 0.62, "front": 0.18, "current": 0.08, "season": 0.12},
        "signals": ["冷水", "群游", "東北部", "秋冬"],
    },
    {
        "name": "秋刀魚",
        "en": "Pacific saury",
        "sci": "Cololabis saira",
        "sst_min": 8,
        "opt_lo": 12,
        "opt_hi": 16,
        "sst_max": 19,
        "season": [6, 7, 8, 9, 10],
        "region": "西北太平洋公海冷水域",
        "depth": "表層",
        "habit": "冷水表層群游魚，台灣多為遠洋棒受網漁業目標。",
        "front_opt": 2.0,
        "front_max": 5.0,
        "current_opt": 0.25,
        "current_max": 0.9,
        "temp_sigma": 1.0,
        "season_floor": 0.30,
        "weights": {"sst": 0.68, "front": 0.12, "current": 0.06, "season": 0.14},
        "signals": ["冷水", "遠洋", "表層群游"],
    },
    {
        "name": "旗魚",
        "en": "Marlin/Sailfish",
        "sci": "Istiophoridae",
        "sst_min": 21,
        "opt_lo": 24,
        "opt_hi": 27,
        "sst_max": 30,
        "season": [10, 11, 12, 1],
        "region": "東部成功、新港外海與黑潮支流",
        "depth": "表層",
        "habit": "大洋表層掠食魚，秋冬隨黑潮支流近岸，是東部傳統鏢旗魚目標。",
        "front_opt": 2.4,
        "front_max": 5.0,
        "current_opt": 0.38,
        "current_max": 1.1,
        "temp_sigma": 1.25,
        "season_floor": 0.40,
        "weights": {"sst": 0.55, "front": 0.20, "current": 0.12, "season": 0.13},
        "signals": ["黑潮支流", "表層掠食", "秋冬", "東部"],
    },
    {
        "name": "飛魚",
        "en": "Flying fish",
        "sci": "Cypselurus spp.",
        "sst_min": 23,
        "opt_lo": 25,
        "opt_hi": 28,
        "sst_max": 30,
        "season": [3, 4, 5, 6],
        "region": "蘭嶼、綠島、東部黑潮表層水域",
        "depth": "表層",
        "habit": "暖水表層群游魚，春夏隨黑潮北上，是達悟族重要文化漁獲。",
        "front_opt": 1.8,
        "front_max": 4.2,
        "current_opt": 0.32,
        "current_max": 1.0,
        "temp_sigma": 1.15,
        "season_floor": 0.45,
        "weights": {"sst": 0.60, "front": 0.14, "current": 0.12, "season": 0.14},
        "signals": ["暖水", "表層", "黑潮", "春夏北上"],
    },
    {
        "name": "鎖管(透抽)",
        "en": "Swordtip squid",
        "sci": "Uroteuthis edulis",
        "sst_min": 18,
        "opt_lo": 21,
        "opt_hi": 25,
        "sst_max": 28,
        "season": [5, 6, 7, 8, 9],
        "region": "東北部、北部海域、近岸產卵聚集區",
        "depth": "表至中層",
        "habit": "暖溫頭足類，夏季群聚產卵，趨光性強，常見於北部與東北部。",
        "front_opt": 1.6,
        "front_max": 4.0,
        "current_opt": 0.22,
        "current_max": 0.8,
        "temp_sigma": 1.25,
        "season_floor": 0.50,
        "weights": {"sst": 0.58, "front": 0.16, "current": 0.10, "season": 0.16},
        "signals": ["北部", "產卵聚集", "趨光", "暖溫"],
    },
]


def _bell(value: float | None, optimum: float, max_value: float) -> float:
    if value is None:
        return 0.0
    if value <= 0:
        return 0.0
    sigma = max(max_value / 2.5, 0.01)
    return max(0.0, min(1.0, exp(-((value - optimum) ** 2) / (2 * sigma**2))))


def thermal_score(sst: float | None, sp: dict[str, Any]) -> float:
    if sst is None:
        return 0.0
    lo_min, opt_lo, opt_hi, hi_max = (
        sp["sst_min"],
        sp["opt_lo"],
        sp["opt_hi"],
        sp["sst_max"],
    )
    if sst <= lo_min or sst >= hi_max:
        return 0.0
    center = (opt_lo + opt_hi) / 2
    sigma = float(sp.get("temp_sigma", max((opt_hi - opt_lo) / 2, 1.0)))
    score = exp(-((sst - center) ** 2) / (2 * sigma**2))
    if opt_lo <= sst <= opt_hi:
        return max(0.72, score)
    return max(0.0, min(1.0, score))


def suitability(
    sst: float | None,
    sp: dict[str, Any],
    month: int,
    *,
    front: float | None = None,
    current: float | None = None,
    trend: float | None = None,
) -> float:
    """Return species habitat suitability from 0-100."""
    weights = sp.get("weights", {})
    w_sst = float(weights.get("sst", 0.6))
    w_front = float(weights.get("front", 0.15))
    w_current = float(weights.get("current", 0.1))
    w_season = float(weights.get("season", 0.15))
    total = max(w_sst + w_front + w_current + w_season, 0.01)

    season_score = 1.0 if month in sp["season"] else float(sp.get("season_floor", 0.45))
    front_score = _bell(front, float(sp.get("front_opt", 2.0)), float(sp.get("front_max", 5.0)))
    current_score = _bell(
        current,
        float(sp.get("current_opt", 0.3)),
        float(sp.get("current_max", 1.0)),
    )
    trend_bonus = 0.0
    if trend is not None:
        warm_species = ((sp["opt_lo"] + sp["opt_hi"]) / 2) >= 23
        trend_bonus = max(-0.05, min(0.05, trend * (1 if warm_species else -1) * 1.5))

    score = (
        thermal_score(sst, sp) * w_sst
        + front_score * w_front
        + current_score * w_current
        + season_score * w_season
    ) / total
    return round(max(0.0, min(100.0, 100 * (score + trend_bonus))), 1)
