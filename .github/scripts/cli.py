#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型仓库统一命令行入口（人工使用）。

把 ingest/ naming/ publish/ 全部脚本与数据校验收纳为子命令，不用记脚本路径：
  python .github/scripts/cli.py <子命令> [转发参数...]

子命令对应脚本一览（--list 查看）：
  organize       归档 .ysm → ingest/organize_models.py
  previews       预览图归位 → ingest/organize_previews.py
  rename-files   重命名模型文件 → ingest/rename_model_files.py
  rename-folders 重命名模型文件夹 → naming/rename_model_folders.py
  kb             命名知识库维护 → naming/kb_tool.py
  authors        重建作者数据 → publish/build_authors_index.py
  readmes        生成模型 README → publish/generate_model_readmes.py
  authors-list   更新根 README 作者表 → publish/build_readme_authors.py
  format         格式化作者 README → publish/format_author_readme.py
  translate      翻译 README-EN → publish/translate_readme.py
  site           生成静态网站 → publish/build_site.py
  flow           流程编排(inbox/full/...) → pipeline.py
  check          数据契约校验 → lib/validate.py

子命令后的所有参数原样转发给目标脚本（如 --apply / --check 等），
由目标脚本自行解释，保证与直接运行脚本行为完全一致。

注意：本入口不做参数解析（薄转发层），只识别第一个位置参数为子命令，
其余参数一律透传——避免 argparse REMAINDER 在子命令场景吞不掉选项的问题。
"""
import os
import subprocess
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path（本脚本位于 scripts/ 根，直接加父目录）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import paths as lib_paths  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = lib_paths.WORKSPACE_ROOT

# 子命令 -> (脚本相对 scripts/ 的路径, 一句话说明)
COMMANDS: dict[str, tuple[str, str]] = {
    'organize': ('ingest/organize_models.py', '归档 .ysm 到 Models/<编号>/'),
    'previews': ('ingest/organize_previews.py', '预览图归入 previews/ 并规范命名'),
    'rename-files': ('ingest/rename_model_files.py', '按命名规范重命名模型文件'),
    'rename-folders': ('naming/rename_model_folders.py', '按知识库重命名模型文件夹'),
    'kb': ('naming/kb_tool.py', '命名知识库维护(--build-kb/--add/--alias/...)'),
    'authors': ('publish/build_authors_index.py', '重建集中作者数据 authors.json'),
    'readmes': ('publish/generate_model_readmes.py', '生成/重写模型 README'),
    'authors-list': ('publish/build_readme_authors.py', '更新根 README 作者表格'),
    'format': ('publish/format_author_readme.py', '格式化作者级 README'),
    'translate': ('publish/translate_readme.py', '翻译 README → README-EN'),
    'site': ('publish/build_site.py', '生成静态模型浏览站 index.html'),
    'flow': ('pipeline.py', '流程编排(inbox/full/rename/...)'),
    'check': ('lib/validate.py', '数据契约校验(schemas/)'),
}

USAGE = (
    '用法: python .github/scripts/cli.py <子命令> [转发参数...]\n'
    '      python .github/scripts/cli.py --list    查看全部子命令\n'
)


def run_script(rel_script: str, args: list[str]) -> int:
    """子进程运行目标脚本；返回其退出码。cwd=仓库根，与 pipeline.py 一致。"""
    script = SCRIPT_DIR / rel_script
    if not script.is_file():
        print(f'[错误] 未找到脚本: {script}', file=sys.stderr)
        return 2
    cmd = [sys.executable, str(script), *args]
    print(f'$ {os.path.relpath(script, REPO_ROOT)} {" ".join(args) if args else ""}')
    return subprocess.run(cmd, cwd=REPO_ROOT, env=os.environ).returncode


def print_commands() -> None:
    """打印全部子命令清单。"""
    print('可用子命令:')
    for name, (_, desc) in COMMANDS.items():
        print(f'  {name:<14} {desc}')
    print()


def main() -> int:
    argv = sys.argv[1:]

    # 帮助/清单类参数单独处理，其余一律视为 (子命令, 转发参数...)
    if not argv:
        print(USAGE, end='')
        return 2
    if argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        print(USAGE)
        return 0
    if argv[0] in ('--list', 'list'):
        print_commands()
        return 0

    command, *forwarded = argv
    entry = COMMANDS.get(command)
    if entry is None:
        print(f'[错误] 未知子命令: {command}', file=sys.stderr)
        print_commands()
        return 2

    rel_script, _ = entry
    return run_script(rel_script, forwarded)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
