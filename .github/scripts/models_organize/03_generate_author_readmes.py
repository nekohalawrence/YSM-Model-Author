#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 作者 README 生成工具——按 authors.json 数据生成作者 README。

作者 README 直接由集中作者数据（author-info/authors.json）渲染：
  # <编号> + ## Author + Name + 平台分类段（无 Role）。
作者在不同模型里负责的功能不一致，作者级 Role 已废弃，角色只记录在
模型级（co_creators.json / .ysm 作者块）。

用法:
  python .github/scripts/models_organize/03_generate_author_readmes.py                       # 合并模式预览（dry-run）
  python .github/scripts/models_organize/03_generate_author_readmes.py --apply               # 合并模式：先反向合并 README 手写信息进 authors.json，再生成 README
  python .github/scripts/models_organize/03_generate_author_readmes.py --overwrite --apply   # 覆盖模式：专门从 authors.json 生成 README（忽略手写）
  python .github/scripts/models_organize/03_generate_author_readmes.py 0058 0093             # 指定编号（合并模式 dry-run）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as lib_paths
from lib import readme as lib_readme
from lib.author_readme import render_author_readme, load_tag_labels
from lib.kb.authors import merge_author_updates

REPO_ROOT = lib_paths.WORKSPACE_ROOT
MODELS_DIR = REPO_ROOT / 'Models'


def author_entries(models_dir: Path,
                   only: list[str] | None = None) -> list[tuple[str, dict]]:
    """返回 (编号, entry) 列表：authors.json 里有 name 且目录存在的作者；only 限定编号。"""
    data = lib_readme.load_authors_index()
    authors = data.get('authors') or {}
    out: list[tuple[str, dict]] = []
    for aid in sorted(authors):
        if only and aid not in only:
            continue
        entry = authors[aid]
        if not (entry.get('name') or []):
            continue  # 无名字的作者跳过
        if not (models_dir / aid).is_dir():
            continue  # 目录不存在的作者（幽灵条目）跳过
        out.append((aid, entry))
    return out


# ---------------------------------------------------------------------------
# 合并模式：把作者 README 的手写信息（team/平台）反向合并进 authors.json
# ---------------------------------------------------------------------------
TEAM_LINE_RE = re.compile(r'^\s*-\s*\*\*team\*\*\s*[:：]\s*(?P<val>.+)$',
                          re.MULTILINE | re.IGNORECASE)
PLATFORM_SUB_RE = re.compile(r'^\s{2,}-\s*\*\*(?P<key>[^*]+)\*\*\s*[:：]\s*(?P<val>.*)$')
TAGS_LINE_RE = re.compile(r'^\s*-\s*\*\*(?:tags|标签)\*\*\s*[:：]\s*(?P<val>.+)$',
                          re.MULTILINE | re.IGNORECASE)


def _tag_text_to_keys(labels: dict, text: str) -> list[str]:
    """把作者 README tags 行的显示文本反查为词表键（推荐/Recommended -> recommended）。

    支持分隔符 ·•、,，;；；反查匹配中文名/英文名/中英成对。
    """
    keys: list[str] = []
    for seg in re.split(r'[·•、,，;；]', text):
        seg = seg.strip()
        if not seg:
            continue
        for k, meta in labels.items():
            zh = str(meta.get('zh') or '')
            en = str(meta.get('en') or '')
            if seg in (zh, en, f'{zh}/{en}'):
                keys.append(k)
                break
    return keys
TAGS_LINE_RE = re.compile(r'^\s*-\s*\*\*(?:tags|标签)\*\*\s*[:：]\s*(?P<val>.+)$',
                          re.MULTILINE | re.IGNORECASE)


def _tag_text_to_keys(labels: dict, text: str) -> list[str]:
    """把作者 README tags 行的显示文本反查为词表键（推荐/Recommended -> recommended）。

    支持分隔符 ·•、,，;；；反查匹配中文名/英文名/中英成对。
    """
    keys: list[str] = []
    for seg in re.split(r'[·•、,，;；]', text):
        seg = seg.strip()
        if not seg:
            continue
        for k, meta in labels.items():
            zh = str(meta.get('zh') or '')
            en = str(meta.get('en') or '')
            if seg in (zh, en, f'{zh}/{en}'):
                keys.append(k)
                break
    return keys


def parse_readme_author_info(text: str) -> dict:
    """从作者 README 提取可反向合并的作者信息：{team, platforms}。

    team 取 `- **team**: <值>` 行（忽略大小写）；平台取缩进子行
    `    - **Key**: [label](url)` / `    - **Key**: 值`（[label](url) 还原为 url）。
    供合并模式反向同步 authors.json 用；无信息返回 {}。
    """
    info: dict = {}
    m = TEAM_LINE_RE.search(text)
    if m and m.group('val').strip():
        info['team'] = m.group('val').strip()
    m = TAGS_LINE_RE.search(text)
    if m:
        tags = _tag_text_to_keys(load_tag_labels(), m.group('val'))
        if tags:
            info['tags'] = tags
    platforms: dict[str, str] = {}
    for line in text.splitlines():
        m = PLATFORM_SUB_RE.match(line)
        if not m:
            continue
        key = m.group('key').strip()
        val = m.group('val').strip()
        if not val:
            continue
        um = re.match(r'^\[[^\]]*\]\((?P<url>https?://[^)]+)\)$', val)
        if um:
            val = um.group('url')
        platforms[key] = val
    if platforms:
        info['platforms'] = platforms
    return info


def merge_readmes_to_authors(models_dir: Path,
                             entries: list[tuple[str, dict]],
                             apply: bool) -> int:
    """合并模式：把作者 README 手写的 team/平台信息反向合并进 authors.json。

    解析每个作者 README → merge_author_updates 按编号/别名匹配合并
    （幂等：平台只补缺失、team 非空写）→ --apply 写回 authors.json。
    返回合并的作者数。
    """
    path = lib_paths.data_path('author-info', 'authors.json')
    data = lib_paths.load_json(path, {})
    authors = data.get('authors') if isinstance(data, dict) else None
    if not authors:
        print('authors.json 缺失或为空，跳过合并。')
        return 0
    updates: dict[str, dict] = {}
    for aid, _entry in entries:
        readme = models_dir / aid / 'README.md'
        if not readme.is_file():
            continue
        info = parse_readme_author_info(
            readme.read_text(encoding='utf-8', errors='ignore'))
        if info:
            updates[aid] = info
    matched, unmatched = merge_author_updates(authors, updates)
    for aid, changes in matched:
        print(f'  [合并] {aid}  {"、".join(changes)}')
    for key in unmatched:
        print(f'  [未匹配] {key}（authors.json 无此作者，未合并）')
    if matched and apply:
        lib_paths.save_json(path, data)
        print(f'已合并 {len(matched)} 位作者的 README 信息 -> authors.json')
    elif matched:
        print(f'合并模式: 共 {len(matched)} 位作者待合并（加 --apply 写入 authors.json）')
    return len(matched)


# ---------------------------------------------------------------------------
# 自动判定标签（仅生成作者 README 时追加显示，不进 authors.json）
# ---------------------------------------------------------------------------
HIGH_OUTPUT_THRESHOLD = 20          # 模型数 ≥ 此值 → 高产 标签
R18_KEYWORDS = ('nsfw', 'r18', 'r-18', '18+')   # 模型文件夹名含 → 18禁 标签


def auto_author_marks(model_count: int, author_dir: Path) -> list[str]:
    """自动判定的标签键列表（作者 README 的 **tags**: 追加显示，不写 authors.json）。

    high-output: 模型数 ≥ 阈值；nsfw: 目录下模型文件夹名含 nsfw/r18/18+。
    根 README 不用本函数（其标记完全由 authors.json 的 tags 驱动）。
    """
    marks: list[str] = []
    if model_count >= HIGH_OUTPUT_THRESHOLD:
        marks.append('high-output')
    pat = re.compile('|'.join(re.escape(k) for k in R18_KEYWORDS), re.IGNORECASE)
    if author_dir.is_dir() and any(pat.search(p.name) for p in author_dir.iterdir()
                                   if p.is_dir() and not p.name.startswith('.')):
        marks.append('nsfw')
    return marks


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('authors', nargs='*',
                        help='作者编号（可多个；不给则按 authors.json 全量生成）')
    parser.add_argument('--root', metavar='PATH', default=None,
                        help='仓库根目录（默认自动检测）')
    parser.add_argument('--apply', action='store_true',
                        help='真正写入（默认 dry-run 只预览）')
    parser.add_argument('--overwrite', action='store_true',
                        help='覆盖模式：忽略 README 手写信息，专门从 authors.json 生成 README'
                             '（默认合并模式：先反向合并 README 的 team/平台进 authors.json 再生成）')
    args = parser.parse_args()

    models_dir = Path(args.root).resolve() / 'Models' if args.root else MODELS_DIR
    if not models_dir.is_dir():
        print(f'错误: {models_dir} 目录不存在。')
        return 2

    only = [a.zfill(4) for a in args.authors] if args.authors else None
    entries = author_entries(models_dir, only)
    if not entries:
        print('authors.json 中没有可生成的作者。')
        return 0

    mode = '覆盖' if args.overwrite else '合并'
    print(f'将按 authors.json 处理 {len(entries)} 位作者的 README（{mode}模式）：')
    if not args.overwrite:
        # 合并模式：先把 README 手写的 team/平台反向合并进 authors.json
        merge_readmes_to_authors(models_dir, entries, args.apply)
        # 重新读取合并后的 authors.json，渲染使用最新 team/平台
        entries = author_entries(models_dir, only)

    generated = 0
    tags_updated = False
    for aid, entry in entries:
        names = ' | '.join(entry.get('name') or [])
        print(f"  {'[生成]' if args.apply else '[计划]'} {aid}  {names}")
        if args.apply:
            model_dir = models_dir / aid
            models = sorted(p.name for p in model_dir.iterdir()
                            if p.is_dir() and not p.name.startswith('.')
                            and p.name.lower() != 'previews')
            # 自动判定标签落盘进 authors.json tags（追加去重）——authors.json 成为唯一标签来源
            auto = auto_author_marks(len(models), model_dir)
            if auto:
                cur = {str(t).lower() for t in (entry.get('tags') or [])}
                new_tags = [t for t in auto if t not in cur]
                if new_tags:
                    entry.setdefault('tags', []).extend(new_tags)
                    tags_updated = True
            readme = model_dir / 'README.md'
            readme.write_text(render_author_readme(aid, entry, models, model_dir),
                              encoding='utf-8')
            generated += 1

    if args.apply and tags_updated:
        path = lib_paths.data_path('author-info', 'authors.json')
        data = lib_paths.load_json(path, {})
        for aid, entry in entries:
            data.setdefault('authors', {})[aid] = entry
        lib_paths.save_json(path, data)
        print(f'已把自动判定标签写入 authors.json：{path}')

    if args.apply:
        print(f'已生成 {generated} 个作者 README。')
    else:
        print('dry-run 预览：未写入。加 --apply 执行。')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
