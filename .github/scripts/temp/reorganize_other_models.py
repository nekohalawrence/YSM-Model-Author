#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按作品类型重新分类 Other-YSM-Models/ 下无作者信息的模型（一次性整理）。

现状：Other-YSM-Models/ 顶层是模型目录平铺（如 AK_阿米娅_Amiya/、Unknown_艾卡/）。
本脚本按「作品_角色_英文」命名的前缀对照作品键表（.github/data/model-info/character/*.json），
把模型目录移入 Other-YSM-Models/<作品缩写>/ 子目录：
  Other-YSM-Models/AK_阿米娅_Amiya/  ->  Other-YSM-Models/AK/阿米娅_Amiya/
  Other-YSM-Models/Unknown_艾卡/     ->  Other-YSM-Models/Unknown/艾卡/
前缀未匹配作品键表 -> Other-YSM-Models/Unknown/。

安全规则：
  - 默认 dry-run 只打印计划；--apply 才真正移动。
  - 顶层目录名本身就是作品键（已是分类容器）的目录跳过，不递归。
  - 目标已存在同名目录时跳过并报告（不覆盖）。

用法:
  python '.github/scripts/temp/reorganize_other_models.py'           # dry-run 预览
  python '.github/scripts/temp/reorganize_other_models.py' --apply   # 真正移动
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import models as lib_models
from lib import paths as lib_paths

detect_work_prefix = lib_models.detect_work_prefix


def work_map(root: Path) -> dict[str, str]:
    """加载作品键表：{作品键大写: 规范写法}（来自 character/*.json 文件名）。"""
    char_dir = (root / '.github' / 'data' / 'model-info' / 'character'
                if root != lib_paths.WORKSPACE_ROOT else lib_paths.CHARACTER_DIR)
    if not char_dir.is_dir():
        return {}
    return {f.stem.upper(): f.stem for f in char_dir.glob('*.json')}


def plan(root: Path) -> tuple[list[tuple[Path, Path, str]], list[str]]:
    """扫描 Other-YSM-Models/ 顶层，计算移动计划。

    返回 (计划列表 [(源目录, 目标目录, 理由), ...], 跳过说明列表)。
    """
    other = root / 'Other-YSM-Models'
    wmap = work_map(root)
    moves: list[tuple[Path, Path, str]] = []
    skipped: list[str] = []
    if not other.is_dir():
        return moves, skipped
    for sub in sorted(other.iterdir()):
        if not sub.is_dir() or sub.name.startswith('.'):
            continue
        name = sub.name
        # 顶层目录名本身就是作品键 => 已是分类容器，跳过（不递归整理其内部）
        if name.upper() in wmap:
            skipped.append(f"[容器] {name}/（已是作品分类目录）")
            continue
        work = detect_work_prefix(name, wmap)
        dest_dir = other / (work or 'Unknown')
        dest = dest_dir / name
        if dest.exists():
            skipped.append(f"[存在] {name}/ -> {dest.relative_to(root)}（目标已存在，跳过）")
            continue
        reason = f"匹配作品 {work}" if work else "未匹配作品，归 Unknown"
        moves.append((sub, dest, reason))
    return moves, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', metavar='PATH', default=None, help='仓库根目录（默认自动检测）')
    parser.add_argument('--apply', action='store_true', help='真正移动（默认 dry-run）')
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else lib_paths.find_workspace_root()
    moves, skipped = plan(root)
    print(f"Other-YSM-Models 作品分类计划（{'执行' if args.apply else 'dry-run'}）:")
    for src, dest, reason in moves:
        print(f"  [移动] {src.relative_to(root)} -> {dest.relative_to(root)}（{reason}）")
    for s in skipped:
        print(f"  {s}")
    if not moves:
        print("没有需要移动的目录。")
        return 0
    if not args.apply:
        print(f"\n共 {len(moves)} 个目录待移动。确认无误后加 --apply 执行。")
        return 0
    moved = 0
    for src, dest, _ in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dest))
            moved += 1
        except OSError as e:
            print(f"  [错误] 移动 {src} 失败: {e}")
    print(f"\n完成: 移动 {moved} 个目录。")
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
