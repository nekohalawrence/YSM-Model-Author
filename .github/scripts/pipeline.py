#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型仓库多脚本流程编排器（本仓库专用）。

各主脚本只负责自己流程的一部分；需要串联多个脚本时，用本编排器按预定义
流程顺序调用。workflow（GitHub Actions）与本地共用同一入口，不用记一堆参数。

预定义流程:
  inbox        推送 _Model-Inbox 新模型后的完整流程:
                归档(organize_models) → 重建作者数据 → 生成模型 README
                → 更新根 README 作者表 → 翻译 README-EN
  full         全套刷新（无新模型时的日常更新）:
                重建作者数据 → 生成模型 README → 作者表 → 翻译
  rename       只运行 rename_model_folders.py --apply（文件夹重命名，需人工 review）
  authors      只重建作者数据 authors.json
  readmes      只生成模型 README
  authors-list 只更新根 README 作者表
  translate    只翻译 README → README-EN

用法:
  python .github/scripts/pipeline.py [流程名] [--dry-run]
  python .github/scripts/pipeline.py --list      # 查看全部流程
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import paths as lib_paths  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = lib_paths.WORKSPACE_ROOT

# 每个步骤 = (脚本相对 scripts/ 的路径, 传给该脚本的参数)
# 顺序即执行顺序；organize_models 只归档，联动交给后续步骤统一跑
STEPS: dict[str, list[tuple[str, list[str]]]] = {
    'inbox': [
        ('ingest/organize_models.py', ['_Model-Inbox', '--apply']),
        ('publish/author_index.py', ['--data']),
        ('publish/generate_model_readmes.py', []),
        ('publish/format_author_readme.py', []),
        ('publish/author_index.py', ['--readme']),
        ('publish/translate_readme.py', []),
    ],
    'full': [
        ('publish/author_index.py', ['--data']),
        ('publish/generate_model_readmes.py', []),
        ('publish/format_author_readme.py', []),
        ('publish/author_index.py', ['--readme']),
        ('publish/translate_readme.py', []),
    ],
    'rename': [
        ('naming/rename_model_folders.py', ['--apply']),
    ],
    'authors': [
        ('publish/author_index.py', ['--data']),
    ],
    'readmes': [
        ('publish/generate_model_readmes.py', []),
    ],
    'authors-list': [
        ('publish/author_index.py', ['--readme']),
    ],
    'translate': [
        ('publish/translate_readme.py', []),
    ],
}

# 每个脚本的一句话说明（--list 用）
STEP_DESC = {
    'ingest/organize_models.py': '归档 .ysm 到 Models/<编号>/',
    'publish/author_index.py': '作者索引(数据 authors.json / 根表)',
    'publish/generate_model_readmes.py': '生成模型 README',
    'publish/format_author_readme.py': '格式化作者级 README',
    'publish/translate_readme.py': '翻译 README → README-EN',
    'naming/rename_model_folders.py': '重命名模型文件夹',
}


def run_step(rel_script: str, args: list[str], dry_run: bool) -> int:
    """运行单个脚本；返回其退出码（dry-run 只打印不执行）。"""
    script = SCRIPT_DIR / rel_script
    if not script.is_file():
        print(f"  [错误] 未找到脚本: {script}", file=sys.stderr)
        return 2
    desc = STEP_DESC.get(rel_script, '')
    print(f"  → {rel_script} {' '.join(args) if args else ''}  {desc}")
    if dry_run:
        print(f"    (dry-run) 未执行")
        return 0
    return subprocess.run([sys.executable, str(script), *args],
                          cwd=REPO_ROOT, env=os.environ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('flow', nargs='?', default='full',
                        help='流程名（默认 full）;用 --list 查看全部')
    parser.add_argument('--dry-run', action='store_true',
                        help='只打印将执行的步骤，不真正运行')
    parser.add_argument('--list', action='store_true', help='列出全部流程及其步骤')
    args = parser.parse_args()

    if args.list:
        for name, steps in STEPS.items():
            print(f"[{name}]")
            for rel, step_args in steps:
                desc = STEP_DESC.get(rel, '')
                suffix = f" {' '.join(step_args)}" if step_args else ''
                print(f"    {rel}{suffix}  {desc}")
        return 0

    if args.flow not in STEPS:
        print(f"未知流程: {args.flow}（可用: {', '.join(STEPS)}）", file=sys.stderr)
        return 2

    print(f"== pipeline: {args.flow} ==")
    for rel, step_args in STEPS[args.flow]:
        code = run_step(rel, step_args, args.dry_run)
        if code != 0:
            print(f"流程中止: {rel} 退出码 {code}", file=sys.stderr)
            return code
    print("== pipeline 完成 ==")
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
