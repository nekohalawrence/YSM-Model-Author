# -*- coding: utf-8 -*-
"""作品大类分类：从 character/*.json 现算分类 + 根 README 模型分类区块渲染。

数据流（character/*.json 为权威源，不再从根 README.md 读取，也不落盘 category_map.json）：
    character/<作品>.json（含可选 category 字段：字符串或数组，数组表示作品属于多个大类）
      -> build_category_map 现算 {大类: [作品键...]}（供 README 区块 / 模型标签用，不落盘）
      -> render_readme_works_section 渲染根 README 的"模型分类"区块（展示产物，非数据源）
      -> generate_model_readmes 的 Category / Game 标签

"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# 大类（Anime 细分为 动画/漫画/小说；作品 category 可为字符串或数组，数组=多分类）
CATEGORIES = ["Game", "Anime", "Manga", "Novel", "Music", "Original", "Other"]

# 根 README"模型分类"区块的包裹标记（author_index 作者表同款 marker 方案）
README_START_MARKER = "<!-- WORKS_CATEGORY_START -->"
README_END_MARKER = "<!-- WORKS_CATEGORY_END -->"

# 根 README 区块的大类标题
CATEGORY_TITLES = {
    "Game": "## 游戏",
    "Anime": "## 动画",
    "Manga": "## 漫画",
    "Novel": "## 小说",
    "Music": "## 音乐",
    "Original": "## 原创",
    "Other": "## 其他",
}


def build_category_map(data: dict, default: str = "Other") -> dict[str, list[str]]:
    """从 character/*.json 现算 {大类: [作品键...]}（按 CATEGORIES 顺序、键字母序）。

    作品条目（dict）的 category 字段决定大类：字符串=单一分类，数组=多个分类
    （作品会同时出现在多个大类下）；缺失/空时归 default（默认 Other）。
    不再落盘 category_map.json，调用方（README 区块 / 模型标签 / audit）直接从
    character/*.json 现算，保证单一数据源。
    """
    cat_map: dict[str, list[str]] = {}
    for k, v in (data.get("works") or {}).items():
        cat = v.get("category") if isinstance(v, dict) else None
        if isinstance(cat, str):
            cats = [cat] if cat else [default]
        elif isinstance(cat, list):
            cats = [c for c in cat if c] or [default]
        else:
            cats = [default]
        for c in cats:
            cat_map.setdefault(c, []).append(k)
    return {c: sorted(cat_map.get(c, [])) for c in CATEGORIES if c in cat_map}


# ---------------------------------------------------------------------------
# 根 README"模型分类"区块渲染（展示产物，从 works.json 自动生成）
# ---------------------------------------------------------------------------
def _work_names(v, lang: str) -> list[str]:
    if isinstance(v, dict):
        lst = v.get(lang) or []
        return lst if isinstance(lst, list) else [lst]
    return v if isinstance(v, list) else ([v] if v else [])


def _render_work_row(key: str, v) -> str:
    en = ", ".join(_work_names(v, "en"))
    cn = ", ".join(_work_names(v, "zh"))
    ja = ", ".join(_work_names(v, "ja"))
    row = en
    if cn:
        row += " | " + cn
    if ja:
        row += " | " + ja
    return row


def render_readme_works_section(data: dict) -> str:
    """渲染根 README 的"模型分类"区块（含 <details>，不含包裹 marker）。"""
    cat_map = build_category_map(data)
    works = data.get("works") or {}
    lines = [
        "<details>", "",
        "<summary>模型分类</summary>", "",
        "> 本区块由 `.github/data/model-info/character/*.json` 自动生成"
        "（`04_generate&update_root_readme.py --build-category-map`），手改请编辑对应作品文件。", "",
        "> 文件夹命名规则", "",
        "```",
        "<英文作品名称>_<中文角色名>-[中文皮肤]_<英文角色名>-[英文皮肤]_<个人评定等级>",
        "",
        "个人评定等级: LA, LB, LC, LD",
        "```", "",
    ]
    for cat in CATEGORIES:
        keys = cat_map.get(cat) or []
        if not keys:
            continue
        lines.append(CATEGORY_TITLES[cat])
        lines.append("")
        for k in sorted(keys):
            row = _render_work_row(k, works.get(k))
            if row:
                lines.append("- " + row)
        lines.append("")
    lines.append("</details>")
    return "\n".join(lines).rstrip() + "\n"


def update_readme_works_section(readme_path: Path, data: dict) -> tuple[bool, str]:
    """把渲染好的"模型分类"区块写入根 README。返回 (是否变更, 动作)。

    优先替换已有 marker 包裹的区块；无 marker 时替换旧版手写的
    `<details><summary>模型分类</summary>...</details>` 整块；均无则追加到末尾。
    """
    section = render_readme_works_section(data)
    full = f"{README_START_MARKER}\n{section}{README_END_MARKER}"
    content = (readme_path.read_text(encoding="utf-8", errors="ignore")
               if readme_path.exists() else "")
    # 1) 已有 marker：替换 marker 之间内容
    if README_START_MARKER in content and README_END_MARKER in content:
        new = re.sub(re.escape(README_START_MARKER) + r".*?"
                     + re.escape(README_END_MARKER), full, content, flags=re.DOTALL)
        if new == content:
            return False, ""
        readme_path.write_text(new, encoding="utf-8")
        return True, "updated"
    # 2) 无 marker 但有旧版手写"模型分类"<details> 块：整块替换
    old_re = re.compile(
        r"<details>\s*\n\s*<summary>\s*模型分类\s*</summary>.*?</details>",
        re.DOTALL)
    new_content, n = old_re.subn(full + "\n", content, count=1)
    if n:
        if new_content != content:
            readme_path.write_text(new_content, encoding="utf-8")
            return True, "replaced-old-block"
        return False, ""
    # 3) 追加到文件末尾
    sep = "\n" if content and not content.endswith("\n") else ""
    readme_path.write_text(content + sep + full + "\n", encoding="utf-8")
    return True, "appended"


def get_work_entry(works: dict, prefix: str):
    """按作品前缀（文件夹名 _ 前段）匹配 works 条目（大小写不敏感）。未命中返回 None。"""
    key = prefix.strip().lower()
    for k, v in works.items():
        if k.lower() == key:
            return v
    return None


def get_work_tags(works: dict, prefix: str) -> str:
    """作品标签（模型 README 的 Game 字段）：该作品全部名称 -> '#名称' 空格连接。"""
    v = get_work_entry(works, prefix)
    if v is None:
        return "#Unknown"
    names = (_work_names(v, "en") + _work_names(v, "zh") + _work_names(v, "ja"))
    names = [n for n in names if n]
    return " ".join(f"#{n}" for n in names) or "#Unknown"
