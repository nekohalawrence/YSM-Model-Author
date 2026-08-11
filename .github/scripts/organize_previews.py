#!/usr/bin/env python3
"""为每个模型文件夹创建 previews/ 子目录,并将顶层 preview 图片移入其中。

设计目标(与 generate_model_readmes.py 保持兼容):
- 只处理文件名为 preview* 的图片(与 generate_model_readmes.py 的 is_preview_image 一致)
- 移动后自动重跑 generate_model_readmes.py 更新 README 引用为 previews/xxx.png
  注意:generate_model_readmes.py 会整体模板化重写模型 README,模板外的手工内容会被覆盖
- 幂等:已有 previews/ 且顶层无 preview 图片的目录会被跳过
- 安全:默认 dry-run,加 --apply 才真正移动;目标已存在同名文件时跳过并计数

用法:
    python .github/scripts/organize_previews.py                # 预览将移动哪些文件
    python .github/scripts/organize_previews.py --apply        # 真正移动 + 重生成 README
    python .github/scripts/organize_previews.py --apply --no-regenerate
    python .github/scripts/organize_previews.py --root Models  # 只处理指定根目录
    python .github/scripts/organize_previews.py --only "Models/0001/AveMujica_三角初华_LB"
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent

ROOT_DIRS = [
    WORKSPACE_ROOT / 'Models',
    WORKSPACE_ROOT / 'Blockbench-Models',
    WORKSPACE_ROOT / 'Other-YSM-Models',
]
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
PREVIEW_MARKER = re.compile(r'preview', re.I)
PREVIEWS_DIRNAME = 'previews'
GENERATE_SCRIPT = SCRIPT_DIR / 'generate_model_readmes.py'


def is_preview_image(path: Path) -> bool:
    """与 generate_model_readmes.py 相同的识别规则:文件名含 preview 的图片"""
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS and PREVIEW_MARKER.search(path.stem)


def iter_model_dirs(root_dir: Path):
    """与 generate_model_readmes.py 相同的目录遍历规则"""
    if root_dir.name == 'Models':
        for author_dir in sorted(root_dir.iterdir()):
            if not (author_dir.is_dir() and author_dir.name.isdigit() and len(author_dir.name) == 4):
                continue
            for model_dir in sorted(author_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                if model_dir.name.startswith('.') or model_dir.name == PREVIEWS_DIRNAME:
                    continue
                yield model_dir
    else:
        for model_dir in sorted(root_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            if model_dir.name.startswith('.') or model_dir.name == PREVIEWS_DIRNAME:
                continue
            yield model_dir


def collect_deep_model_dirs(root_dir: Path):
    """递归收集所有含顶层 preview 图片的目录(任意层级)。

    除了标准的 作者目录/模型目录 两层结构,Models 下还存在「系列包」式的
    嵌套变体目录(如 Models/0058/WW_抽象鸣潮系列/抽象鸣潮 嘉贝莉娜/)。
    这些目录通常没有 README,generate_model_readmes.py 不会处理它们,
    但它们同样携带 preview 图片,应一并为它们创建 previews/ 归类。
    返回按路径排序的目录列表,不含 previews/ 目录本身。
    """
    dirs = set()
    for p in root_dir.rglob('*'):
        if p.is_file() and is_preview_image(p) and p.parent.name.lower() != PREVIEWS_DIRNAME.lower():
            dirs.add(p.parent)
    return sorted(dirs)


def organize_model(model_dir: Path, apply: bool) -> dict:
    """处理单个模型目录,返回统计信息"""
    result = {'moved': 0, 'skipped_conflict': 0, 'skipped_not_preview': 0, 'status': 'unchanged'}

    # 顶层 preview 图片(不进入已有 previews/ 递归,只移动顶层)
    top_images = sorted(p for p in model_dir.iterdir() if is_preview_image(p))
    # 顶层其他图片(含 preview 字样之外)仅统计,不移动
    other_images = sorted(
        p for p in model_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not PREVIEW_MARKER.search(p.stem)
    )

    if not top_images:
        if other_images:
            result['status'] = 'no-preview-but-other-images'
            result['other_images'] = [p.name for p in other_images]
        return result

    target_dir = model_dir / PREVIEWS_DIRNAME
    conflicts = []
    moves = []
    for src in top_images:
        dst = target_dir / src.name
        if dst.exists():
            conflicts.append(src.name)
            continue
        moves.append((src, dst))

    result['status'] = 'has-preview'
    result['moved'] = len(moves)
    result['skipped_conflict'] = len(conflicts)
    result['conflicts'] = conflicts
    result['moves'] = [(src.name, PREVIEWS_DIRNAME) for src, _ in moves]
    result['other_images'] = [p.name for p in other_images]

    if not apply:
        return result

    if moves:
        target_dir.mkdir(exist_ok=True)
        for src, dst in moves:
            shutil.move(str(src), str(dst))
    return result


def run_generate_readmes() -> int:
    """重跑 generate_model_readmes.py 更新 README 引用"""
    proc = subprocess.run(
        [sys.executable, str(GENERATE_SCRIPT)],
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    for line in (proc.stdout or '').splitlines():
        print(f'  [generate] {line}')
    if proc.returncode != 0:
        print(f'  [generate] stderr: {proc.stderr}', file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true',
                        help='真正创建 previews/ 并移动文件;缺省为 dry-run')
    parser.add_argument('--no-regenerate', action='store_true',
                        help='移动后不重跑 generate_model_readmes.py(默认会重跑)')
    parser.add_argument('--root', choices=[r.name for r in ROOT_DIRS],
                        help='只处理指定根目录(默认全部)')
    parser.add_argument('--only', metavar='REL_PATH',
                        help='只处理单个模型目录(相对仓库根,如 Models/0001/xxx)')
    args = parser.parse_args()

    roots = [r for r in ROOT_DIRS if args.root is None or r.name == args.root]

    model_dirs = []
    if args.only:
        p = WORKSPACE_ROOT / args.only
        if not p.is_dir():
            print(f'错误:目录不存在: {args.only}', file=sys.stderr)
            return 2
        model_dirs.append(p)
    else:
        for root in roots:
            if not root.is_dir():
                continue
            # 递归收集所有含 preview 图片的目录,覆盖系列包嵌套变体
            model_dirs.extend(collect_deep_model_dirs(root))

    total_moved = 0
    total_conflicts = 0
    total_other = 0
    processed = 0
    unchanged = 0

    print(f'模式: {"APPLY(执行)" if args.apply else "DRY-RUN(预览)"}  模型目录数: {len(model_dirs)}')
    print('-' * 60)

    for model_dir in model_dirs:
        rel = model_dir.relative_to(WORKSPACE_ROOT).as_posix()
        info = organize_model(model_dir, apply=args.apply)
        if info['status'] == 'unchanged':
            unchanged += 1
            continue
        processed += 1
        total_moved += info['moved']
        total_conflicts += info['skipped_conflict']
        total_other += len(info.get('other_images', []))

        verb = '移动' if args.apply else '将移动'
        print(f'{rel}')
        if info.get('moves'):
            for name, _ in info['moves']:
                print(f'    {verb} {name} -> {PREVIEWS_DIRNAME}/')
        for name in info.get('conflicts', []):
            print(f'    跳过(目标已存在) {name}')
        for name in info.get('other_images', []):
            print(f'    保留(非 preview 命名) {name}')

    print('-' * 60)
    print(f'处理目录: {processed}  未变更: {unchanged}  移动文件: {total_moved}  '
          f'冲突跳过: {total_conflicts}  保留的其他图片: {total_other}')

    if args.apply and total_moved > 0 and not args.no_regenerate:
        print('正在重跑 generate_model_readmes.py 更新 README 引用 ...')
        rc = run_generate_readmes()
        if rc != 0:
            print('错误:generate_model_readmes.py 返回非零,README 引用可能未更新', file=sys.stderr)
            return rc
    elif args.apply and total_moved > 0 and args.no_regenerate:
        print('提示:已跳过 README 重生成(--no-regenerate)。请手动运行 '
              'python .github/scripts/generate_model_readmes.py 更新引用。')

    # 冲突文件会同时被顶层与 previews/ 收集,导致 README 重复引用,必须提示
    if total_conflicts > 0:
        print('警告:存在冲突文件未移动(见上),请手动处理以免 README 重复引用', file=sys.stderr)
        return 3

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
