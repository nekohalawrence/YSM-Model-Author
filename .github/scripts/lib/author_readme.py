# -*- coding: utf-8 -*-
"""作者 README 生成共享逻辑：按 authors.json 数据渲染作者 README。

作者 README 直接由集中作者数据（author-info/authors.json）生成：
  # <编号> + ## Author（Name + 平台分类段）+ ## Models（模型列表，按作品分组折叠）。
不含 Role——作者在不同模型里负责的功能不一致，角色只记录在模型级
（co_creators.json / .ysm 作者块），作者级不再固定 Role。

被 03_generate_author_readmes.py（生成作者 README）与 01_organize_models.py
（归档登记作者名）共用。抽到 lib/ 避免跨脚本 import 含 `&` 等非法字符的文件名。
"""
from __future__ import annotations

import re

from lib import paths as lib_paths
from lib import ysm as lib_ysm

# 平台分类输出顺序（与模型 README 的 author_block 模板一致）
PLATFORM_ORDER = ['SocialPlatform', 'SupportPlatform', 'OtherPlatform', 'GroupChat']


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


def _classify_platforms(platforms: dict,
                        platform_map: dict) -> dict[str, list[tuple[str, str]]]:
    """把扁平 {平台键: 值} 按 platform_map 分类为 {分类: [(规范平台名, 值)]}。

    键与别名（小写）反查归属，规范名本身也参与匹配；未命中归 OtherPlatform。
    """
    reverse: dict[str, tuple[str, str]] = {}
    for field, pmap in platform_map.items():
        for canonical, aliases in pmap.items():
            for alias in [canonical, *aliases]:
                reverse.setdefault(alias.strip().lower(), (field, canonical))
    out: dict[str, list[tuple[str, str]]] = {}
    for key, value in platforms.items():
        hit = reverse.get(key.strip().lower())
        field, canonical = hit if hit else ('OtherPlatform', key.strip())
        out.setdefault(field, []).append((canonical, str(value)))
    return out


def load_work_names() -> dict[str, str]:
    """读 character/*.json 构建 {作品键: 中文规范名}（work.name.zh）。"""
    rdir = lib_paths.data_path('model-info', 'character')
    out: dict[str, str] = {}
    if rdir.is_dir():
        for f in sorted(rdir.glob('*.json')):
            content = lib_paths.load_json(f, {})
            if not isinstance(content, dict):
                continue
            work = content.get('work')
            if not isinstance(work, dict):
                continue
            abbr = work.get('abbr') or work.get('name') or ''
            name_map = work.get('name') or {}
            zh = name_map.get('zh') if isinstance(name_map, dict) else name_map
            if abbr and zh:
                out[str(abbr)] = str(zh)
    return out


def render_models_section(models: list[str], work_names: dict[str, str]) -> str:
    """渲染 ## Models 段：按作品字母序分组（Unknown 最后），每组 <details> 折叠。

    作品前缀取模型文件夹名第一个 '_' 前部分；无前缀或 Unknown_ 归 Unknown。
    """
    groups: dict[str, list[str]] = {}
    for name in models:
        prefix = name.split('_', 1)[0].strip() if '_' in name else 'Unknown'
        if not prefix or prefix.lower() == 'unknown':
            prefix = 'Unknown'
        groups.setdefault(prefix, []).append(name)

    ordered = sorted(groups, key=lambda k: (k.lower() == 'unknown', k.lower()))
    lines = ['## Models', '']
    for prefix in ordered:
        items = groups[prefix]
        # Unknown 本身即"未知"，不再叠加完整名；其余作品查 character/*.json 的中文名
        full = '' if prefix.lower() == 'unknown' else work_names.get(prefix, '')
        title = f'{prefix} {full}（{len(items)}）' if full else f'{prefix}（{len(items)}）'
        lines.append('<details>')
        lines.append(f'<summary><b>{title}</b></summary>')
        lines.append('')
        for n in items:
            lines.append(f'- [{n}]({n})')
        lines.append('')
        lines.append('</details>')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def render_author_readme(author_id: str, entry: dict,
                         models: list[str] | None = None) -> str:
    """按 authors.json 的 entry 生成作者 README（Name + 平台段 + 可选 Models 段）。

    entry: {'name': [...], 'platforms': {平台键: 值}}（authors.json 作者条目）。
    models: 模型文件夹名列表（非空时渲染 ## Models 段，按作品分组折叠）。
    """
    names = entry.get('name') or []
    if isinstance(names, str):
        names = [names]
    names = [str(n) for n in names if str(n)]
    name_str = ' | '.join(names) if names else '暂无'
    label = names[0].lstrip('#＃') if names else name_str

    lines = [f'# {author_id}', '', '## Author', '', f'- **Name**: {name_str}']
    classified = _classify_platforms(entry.get('platforms') or {},
                                     lib_ysm.load_platform_map())
    for field in PLATFORM_ORDER:
        pairs = classified.get(field) or []
        if not pairs:
            continue
        tags = ' #'.join(key for key, _ in pairs)
        lines.append(f'  - **{field}**: #{tags}')
        for key, value in pairs:
            if value.startswith('http'):
                lines.append(f'    - **{key}**: [{label}]({value})')
            else:
                lines.append(f'    - **{key}**: {value}')

    if models:
        lines.append('')
        lines.append(render_models_section(models, load_work_names()).rstrip('\n'))
    return '\n'.join(lines) + '\n'
