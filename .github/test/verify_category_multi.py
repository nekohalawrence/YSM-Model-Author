# -*- coding: utf-8 -*-
"""临时验证：build_category_map 对数组分类 + 枚举细化的支持（验证后由主流程回归覆盖）。"""
import sys
import pathlib

sys.stdout.reconfigure(encoding='utf-8')
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".github" / "scripts"))
from lib.kb.category import CATEGORIES, CATEGORY_TITLES, build_category_map

assert CATEGORIES == ["Game", "Anime", "Manga", "Novel", "Music", "Original", "Other"], CATEGORIES

data = {"works": {
    "AK": {"en": ["Arknights"], "category": "Game"},
    "5Toubun": {"en": ["5Toubun"], "category": ["Anime", "Manga", "Novel"]},
    "FGO": {"en": ["FGO"], "category": "Game"},
    "NoCat": {"en": ["X"]},
}}
m = build_category_map(data)
# 单分类：Game 含 AK、FGO
assert m["Game"] == ["AK", "FGO"], m["Game"]
# 数组分类：5Toubun 同时出现在 Anime/Manga/Novel
assert m["Anime"] == ["5Toubun"], m.get("Anime")
assert m["Manga"] == ["5Toubun"], m.get("Manga")
assert m["Novel"] == ["5Toubun"], m.get("Novel")
# 未分类归 Other
assert m["Other"] == ["NoCat"], m.get("Other")
print("CATEGORIES =", CATEGORIES)
for c in CATEGORIES:
    if c in m:
        print(f"  {c:<8} {CATEGORY_TITLES.get(c, '')} -> {m[c]}")
print("多分类数组逻辑验证: 全部通过")
