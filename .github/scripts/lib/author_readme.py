# -*- coding: utf-8 -*-
"""作者 README 生成共享逻辑：新作者 README 的默认 Role 与渲染。

被 01_organize_models（归档新建作者时）与 models_organize/03_generate&update_author_readme.py
（作者 README 生成/格式化）共用。抽到 lib/ 避免跨脚本 import 含 `&` 等非法字符的文件名。
"""
from __future__ import annotations

import re

TARGET_ROLE = "#模型 #动作 #动画 | #Model #Motion #Animation"


def format_author_name(authors_str: str) -> str:
    """'鸡姬(raw_chicken)' -> '#鸡姬 | #raw_chicken'（保留原始顺序，每个别名加 #）。

    与 organize_models 原实现一致：按分隔符拆段，'中文(English)' 括号对拆成两个别名。
    """
    tags: list[str] = []
    for seg in re.split(r'[\s|｜,，、;/；]+', authors_str):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r'^([^()（）]*)[(（]([^)）]*)[)）]$', seg)
        if m:
            outer, inner = m.group(1).strip(), m.group(2).strip()
            parts = [outer, inner] if outer and inner else [outer or inner]
        else:
            parts = [seg]
        for tag in parts:
            tag = tag.strip()
            if tag and not tag.startswith('#') and not tag.startswith('＃'):
                tag = '#' + tag
            if tag and tag not in tags:
                tags.append(tag)
    return ' | '.join(tags)


def render_author_readme(author_id: str, authors_str: str) -> str:
    """生成新作者 README（模仿现有作者 README 风格：编号标题 + Author 段）。"""
    name_line = format_author_name(authors_str) or '暂无'
    return (
        f'# {author_id}\n'
        '\n'
        '## Author\n'
        '\n'
        f'- **Name**: {name_line}\n'
        f'  - **Role**: {TARGET_ROLE}\n'
    )
