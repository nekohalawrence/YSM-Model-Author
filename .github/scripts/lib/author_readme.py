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
from pathlib import Path

from lib import paths as lib_paths
from lib import ysm as lib_ysm

# 平台分类输出顺序（与模型 README 的 author_block 模板一致）
PLATFORM_ORDER = ['SocialPlatform', 'SupportPlatform', 'OtherPlatform', 'GroupChat']

# ---- 作者标记（根 README 与作者 README 共用，tags 键驱动） ----
HIGH_OUTPUT_THRESHOLD = 20          # 模型数 ≥ 此值 → 🔥 高产
R18_KEYWORDS = ('nsfw', 'r18', 'r-18', '18+')   # 模型文件夹名含 → 🔞 R18
TEAM_KEYWORDS = ('工作室', '制作组', '官方', 'official', 'team', '团队', '组')
# tag 键 → 展示（emoji / 中文名）
MARK_EMOJI = {'recommended': '⭐', 'high-output': '🔥', 'r18': '🔞', 'team': '👥'}
MARK_LABEL = {'recommended': '推荐', 'high-output': '高产', 'r18': 'R18', 'team': '团队'}


def is_team_author(names: list[str]) -> bool:
    """团队/工作室作者：任一别名含团队关键词（忽略大小写）。"""
    for n in names:
        nl = n.lower()
        if any(kw in nl for kw in TEAM_KEYWORDS):
            return True
    return False


def is_r18_author(author_dir: Path | None) -> bool:
    """R18 作者：作者目录下存在模型文件夹名含 nsfw/r18/18+（忽略大小写）。

    author_dir 为空（作者 README 渲染无目录时）返回 False，仅依赖 tags 人工标记。
    """
    if author_dir is None or not author_dir.is_dir():
        return False
    pat = re.compile('|'.join(re.escape(k) for k in R18_KEYWORDS), re.IGNORECASE)
    return any(pat.search(p.name) for p in author_dir.iterdir()
               if p.is_dir() and not p.name.startswith('.'))


def compute_author_marks(entry: dict, model_count: int,
                         author_dir: Path | None = None) -> list[str]:
    """计算作者标记（tag 键名列表：recommended/high-output/r18/team）。

    手工 tags（authors.json）+ 自动判定，根 README 与作者 README 共用：
      recommended: tags 含 或 旧 recommended 字段（兼容迁移前）
      high-output: model_count ≥ 阈值（自动）
      r18: tags 含 或 目录下模型文件夹名含 nsfw/r18（人工+自动并集）
      team: name 含团队关键词（自动）
    """
    tags = {str(t).lower() for t in (entry.get('tags') or []) if isinstance(t, str)}
    marks: list[str] = []
    if 'recommended' in tags or entry.get('recommended'):
        marks.append('recommended')
    if model_count >= HIGH_OUTPUT_THRESHOLD:
        marks.append('high-output')
    if 'r18' in tags or is_r18_author(author_dir):
        marks.append('r18')
    if is_team_author(entry.get('name') or []):
        marks.append('team')
    return marks


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


def load_work_names() -> dict[str, dict]:
    """读 character/*.json 构建 {作品键: {'zh': 中文名, 'en': 英文名}}。

    英文名可能缺失（如 OC/部分动漫作品只有中文名），调用方需回退处理。
    """
    rdir = lib_paths.data_path('model-info', 'character')
    out: dict[str, dict] = {}
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
            en = name_map.get('en') if isinstance(name_map, dict) else ''
            if abbr and (zh or en):
                out[str(abbr)] = {'zh': str(zh) if zh else '',
                                  'en': str(en) if en else ''}
    return out


def render_models_section(models: list[str], work_names: dict[str, str],
                          links: list[str] | None = None) -> str:
    """渲染 ## Models 段：按作品字母序分组（Unknown 最后），每组 <details> 折叠。

    作品前缀取模型文件夹名第一个 '_' 前部分；无前缀或 Unknown_ 归 Unknown。
    links 提供时用于链接目标（如相对路径），models 仅作显示名与分组键；缺省同名
    （作者 README 场景 links=None）。顶层 Other-YSM-Models 索引用它做路径链接。
    """
    if links is None:
        links = models
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, link in zip(models, links):
        prefix = name.split('_', 1)[0].strip() if '_' in name else 'Unknown'
        if not prefix or prefix.lower() == 'unknown':
            prefix = 'Unknown'
        groups.setdefault(prefix, []).append((name, link))

    ordered = sorted(groups, key=lambda k: (k.lower() == 'unknown', k.lower()))
    lines = ['## Models', '']
    for prefix in ordered:
        items = groups[prefix]
        # Unknown 本身即"未知"，不再叠加完整名；其余作品查 character/*.json 的中英文名
        info = {} if prefix.lower() == 'unknown' else work_names.get(prefix, {})
        zh = info.get('zh', '') if isinstance(info, dict) else ''
        en = info.get('en', '') if isinstance(info, dict) else ''
        if zh and en:
            title = f'{en} | {zh}（{len(items)}）'
        elif zh:
            title = f'{zh}（{len(items)}）'
        elif en:
            title = f'{en}（{len(items)}）'
        else:
            title = f'{prefix}（{len(items)}）'
        lines.append('<details>')
        lines.append(f'<summary><b>{title}</b></summary>')
        lines.append('')
        for n, ln in items:
            lines.append(f'- [{n}]({ln})')
        lines.append('')
        lines.append('</details>')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def render_author_readme(author_id: str, entry: dict,
                         models: list[str] | None = None,
                         author_dir: Path | None = None) -> str:
    """按 authors.json 的 entry 生成作者 README（Name + Marks + 平台段 + 可选 Models 段）。

    entry: {'name': [...], 'platforms': {平台键: 值}, 'tags': [...]}（authors.json 作者条目）。
    models: 模型文件夹名列表（非空时渲染 ## Models 段，按作品分组折叠）。
    author_dir: 作者目录（R18 自动判定用，可为空）。
    """
    names = entry.get('name') or []
    if isinstance(names, str):
        names = [names]
    names = [str(n) for n in names if str(n)]
    name_str = ' | '.join(names) if names else '暂无'
    label = names[0].lstrip('#＃') if names else name_str

    lines = [f'# {author_id}', '', '## Author', '', f'- **Name**: {name_str}']
    # 作者标记（⭐ 推荐 · 🔥 高产 · 🔞 R18 · 👥 团队），与根 README 同判定
    marks = compute_author_marks(entry, len(models) if models else 0, author_dir)
    if marks:
        mark_str = ' · '.join(f'{MARK_EMOJI[m]} {MARK_LABEL[m]}' for m in marks)
        lines.append(f'- **Marks**: {mark_str}')
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
