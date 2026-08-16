#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 作者 README 生成工具——按 authors.json 数据生成作者 README。

作者 README 直接由集中作者数据（author-info/authors.json）渲染：
  # <编号> + ## Author + Name + 平台分类段（无 Role）。
作者在不同模型里负责的功能不一致，作者级 Role 已废弃，角色只记录在
模型级（co_creators.json / .ysm 作者块）。

用法:
  python .github/scripts/models_organize/03_generate_author_readmes.py              # 全量预览（dry-run）
  python .github/scripts/models_organize/03_generate_author_readmes.py 0058 0093    # 指定编号（dry-run）
  python .github/scripts/models_organize/03_generate_author_readmes.py --apply      # 真正写入
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as lib_paths
from lib import readme as lib_readme
from lib.author_readme import render_author_readme

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('authors', nargs='*',
                        help='作者编号（可多个；不给则按 authors.json 全量生成）')
    parser.add_argument('--root', metavar='PATH', default=None,
                        help='仓库根目录（默认自动检测）')
    parser.add_argument('--apply', action='store_true',
                        help='真正写入（默认 dry-run 只预览）')
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

    print(f'将按 authors.json 生成 {len(entries)} 位作者的 README：')
    generated = 0
    for aid, entry in entries:
        names = ' | '.join(entry.get('name') or [])
        print(f"  {'[生成]' if args.apply else '[计划]'} {aid}  {names}")
        if args.apply:
            model_dir = models_dir / aid
            models = sorted(p.name for p in model_dir.iterdir()
                            if p.is_dir() and not p.name.startswith('.')
                            and p.name.lower() != 'previews')
            readme = model_dir / 'README.md'
            readme.write_text(render_author_readme(aid, entry, models), encoding='utf-8')
            generated += 1

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
