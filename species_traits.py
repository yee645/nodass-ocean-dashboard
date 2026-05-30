"""台灣常見經濟魚種習性與適溫資料表（供熱棲地適合度模型使用）。

適溫範圍綜合漁業海洋學常用之表水溫偏好區間，欄位定義：
  sst_min / opt_lo / opt_hi / sst_max：梯形隸屬函數的四個轉折點 (°C)。
  season：盛漁期月份（用於季節因子）。
  region：台灣主要漁場區域。  depth：棲息水層。  habit：習性摘要。
數值為文獻常見範圍之整理，作為透明可解釋之代理指標，非精確物種分布模型。
取得 NODASS 會員管制資料權限後，可用歷史漁獲與衛星葉綠素校正各魚種參數。
"""
from __future__ import annotations

SPECIES: list[dict] = [
    {
        "name": "鬼頭刀", "en": "Mahi-mahi", "sci": "Coryphaena hippurus",
        "sst_min": 21, "opt_lo": 25, "opt_hi": 28, "sst_max": 31,
        "season": [3, 4, 5, 6, 10, 11], "region": "東部黑潮流域",
        "depth": "表層", "habit": "表層洄游性掠食魚，時速可達90km，常追捕飛魚；東部產量近總漁獲半數。",
    },
    {
        "name": "太平洋黑鮪", "en": "Pacific bluefin tuna", "sci": "Thunnus orientalis",
        "sst_min": 16, "opt_lo": 18, "opt_hi": 22, "sst_max": 25,
        "season": [4, 5, 6], "region": "東部、東港外海",
        "depth": "中表層", "habit": "大洋洄游，偏好較涼水團；端午前後黑鮪季為東港重要漁獲。",
    },
    {
        "name": "黃鰭鮪", "en": "Yellowfin tuna", "sci": "Thunnus albacares",
        "sst_min": 20, "opt_lo": 24, "opt_hi": 28, "sst_max": 31,
        "season": [1, 2, 3, 4, 11, 12], "region": "東部、南部外海",
        "depth": "表至中層", "habit": "暖水大洋性，常隨黑潮分布，群游追食小魚與頭足類。",
    },
    {
        "name": "正鰹", "en": "Skipjack tuna", "sci": "Katsuwonus pelamis",
        "sst_min": 20, "opt_lo": 24, "opt_hi": 29, "sst_max": 31,
        "season": [4, 5, 6, 7, 8, 9], "region": "東部、東北部外海",
        "depth": "表層", "habit": "暖水群游性，表層成大群，為鰹節與罐頭主要原料。",
    },
    {
        "name": "白帶魚", "en": "Largehead hairtail", "sci": "Trichiurus japonicus",
        "sst_min": 16, "opt_lo": 19, "opt_hi": 23, "sst_max": 26,
        "season": [3, 4, 5, 6, 7, 8], "region": "東北部、台灣海峽、西南部",
        "depth": "底層60-100m，夜間上浮", "habit": "暖溫性底棲，晝沉夜浮垂直洄游，群游肉食；東海陸棚為全球最大漁場。",
    },
    {
        "name": "白腹鯖(花飛)", "en": "Chub mackerel", "sci": "Scomber japonicus",
        "sst_min": 14, "opt_lo": 17, "opt_hi": 20, "sst_max": 23,
        "season": [10, 11, 12, 1, 2, 3], "region": "東北部南方澳、蘇澳",
        "depth": "表至中層", "habit": "溫水群游性，秋冬季為盛漁期，扒網主要漁獲。",
    },
    {
        "name": "秋刀魚", "en": "Pacific saury", "sci": "Cololabis saira",
        "sst_min": 8, "opt_lo": 12, "opt_hi": 16, "sst_max": 19,
        "season": [6, 7, 8, 9, 10], "region": "西北太平洋公海(遠洋)",
        "depth": "表層", "habit": "冷水表層群游，台灣遠洋棒受網主力，漁場位北方冷水域。",
    },
    {
        "name": "旗魚", "en": "Marlin/Sailfish", "sci": "Istiophoridae",
        "sst_min": 21, "opt_lo": 24, "opt_hi": 27, "sst_max": 30,
        "season": [10, 11, 12, 1], "region": "東部成功、新港(鏢旗魚)",
        "depth": "表層", "habit": "大洋表層掠食，秋冬隨黑潮支流近岸，東部傳統鏢旗魚漁業。",
    },
    {
        "name": "飛魚", "en": "Flying fish", "sci": "Cypselurus spp.",
        "sst_min": 23, "opt_lo": 25, "opt_hi": 28, "sst_max": 30,
        "season": [3, 4, 5, 6], "region": "蘭嶼、綠島、東部黑潮",
        "depth": "表層", "habit": "暖水表層群游，春夏隨黑潮北上，達悟族重要文化漁獲。",
    },
    {
        "name": "鎖管(透抽)", "en": "Swordtip squid", "sci": "Uroteuthis edulis",
        "sst_min": 18, "opt_lo": 21, "opt_hi": 25, "sst_max": 28,
        "season": [5, 6, 7, 8, 9], "region": "東北部、北部海域",
        "depth": "表至中層", "habit": "暖溫頭足類，夏季群聚產卵，趨光性強，棒受網/焰火捕撈。",
    },
]


def suitability(sst: float, sp: dict, month: int) -> float:
    """以梯形隸屬函數計算熱棲地適合度，並乘季節因子，回傳 0-100。"""
    if sst is None:
        return 0.0
    lo_min, lo, hi, hi_max = sp["sst_min"], sp["opt_lo"], sp["opt_hi"], sp["sst_max"]
    if sst <= lo_min or sst >= hi_max:
        therm = 0.0
    elif lo <= sst <= hi:
        therm = 1.0
    elif sst < lo:
        therm = (sst - lo_min) / (lo - lo_min)
    else:
        therm = (hi_max - sst) / (hi_max - hi)
    season_factor = 1.0 if month in sp["season"] else 0.55
    return round(100 * therm * season_factor, 1)
