#!/usr/bin/env python3
"""整理模型文件夹中的预览图片,统一归入 previews/ 子目录并规范命名。

设计目标(与 generate_model_readmes.py 保持兼容):
- 移动模式(默认):只处理文件名为 preview* 的图片(与 generate_model_readmes.py
  的 is_preview_image 规则一致),将其移入 previews/
- 重命名模式(--rename):把模型目录顶层与 previews/ 下**所有**图片统一重命名为
  `preview<两位数字>.<扩展名>`,顶层图片一并归入 previews/;已符合规范命名的文件
  保持原名,编号自动跳过已被占用的序号(幂等)
- 移动/重命名后自动重跑 generate_model_readmes.py 更新 README 引用
  注意:generate_model_readmes.py 会整体模板化重写模型 README,模板外的手工内容会被覆盖
- 安全:默认 dry-run,加 --apply 才真正执行;目标已存在同名文件时跳过并计数

退出码:0 成功;1 编号耗尽等错误;2 目录不存在;3 存在未处理的冲突文件

用法:
    python .github/scripts/models_organize/01_organize_previews.py                      # 预览将移动哪些文件
    python .github/scripts/models_organize/01_organize_previews.py --rename             # 预览将如何重命名预览图
    python .github/scripts/models_organize/01_organize_previews.py --apply              # 真正移动 + 重生成 README
    python .github/scripts/models_organize/01_organize_previews.py --apply --rename     # 真正重命名 + 重生成 README
    python .github/scripts/models_organize/01_organize_previews.py --apply --no-regenerate
    python .github/scripts/models_organize/01_organize_previews.py --root Models        # 只处理指定根目录
    python .github/scripts/models_organize/01_organize_previews.py --only "Models/0001/AveMujica_三角初华_LB"
"""
from __future__ import annotations

import argparse
import dataclasses
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import paths as lib_paths
from lib import previews as lib_previews

WORKSPACE_ROOT = lib_paths.WORKSPACE_ROOT
SCRIPT_DIR = Path(__file__).resolve().parent

ROOT_DIRS = [
    WORKSPACE_ROOT / 'Models',
    WORKSPACE_ROOT / 'Blockbench-Models',
    WORKSPACE_ROOT / 'Other-YSM-Models',
]
# 预览图识别规则统一复用 lib/previews.py
IMAGE_EXTS = lib_previews.IMAGE_EXTS
PREVIEW_MARKER = lib_previews.PREVIEW_MARKER
PREVIEWS_DIRNAME = lib_previews.PREVIEWS_DIRNAME
is_preview_image = lib_previews.is_preview_image
is_image_file = lib_previews.is_image_file
find_previews_dir = lib_previews.find_previews_dir
# 规范命名:preview + 两位数字(01~99),如 preview01.png
PREVIEW_NUMBER_RE = re.compile(r'^preview(\d{2})$', re.IGNORECASE)
MAX_PREVIEW_INDEX = 99
# 生成脚本在 models_organize/ 下(与 lib/ 同级目录体系)
GENERATE_SCRIPT = SCRIPT_DIR.parent / 'models_organize' / '03_generate&update_model_readmes.py'


@dataclass(frozen=True)
class MovePlan:
    """单个文件操作,等价于 shutil.move(src, dst)"""

    src: Path
    dst: Path

    @property
    def rename_only(self) -> bool:
        return self.src.parent == self.dst.parent

    @property
    def move_only(self) -> bool:
        return self.src.parent != self.dst.parent and self.src.name == self.dst.name

    @property
    def verb(self) -> str:
        if self.src.parent != self.dst.parent and self.src.name != self.dst.name:
            return '移动并重命名'
        if self.move_only:
            return '移动'
        return '重命名'


@dataclass
class DirResult:
    """一个模型目录的处理计划与统计"""

    plan: list[MovePlan] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    other_images: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_work(self) -> bool:
        return bool(self.plan or self.conflicts)


def collect_model_dirs(roots: list[Path], rename_mode: bool) -> list[Path]:
    """递归收集所有需要处理的模型目录(任意层级)。

    除了标准的「作者目录/模型目录」两层结构,Models 下还存在「系列包」式的
    嵌套变体目录(如 Models/0058/WW_抽象鸣潮系列/抽象鸣潮 嘉贝莉娜/),它们
    同样携带预览图片,应一并处理。这些目录通常没有 README,generate_model_readmes.py
    不会处理它们,本脚本负责为它们归类。

    移动模式:只收集含「文件名含 preview 的顶层图片」的目录。
    重命名模式:顶层或 previews/ 下存在任意图片即收集。
    """
    dirs: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob('*'):
            if not is_image_file(p):
                continue
            parent = p.parent
            if parent.name.lower() == PREVIEWS_DIRNAME.lower():
                if rename_mode:
                    dirs.add(parent.parent)
            elif rename_mode or PREVIEW_MARKER.search(p.stem):
                dirs.add(parent)
    return sorted(dirs)


def plan_move(model_dir: Path) -> DirResult:
    """移动模式:把顶层 preview 命名的图片移入 previews/(原行为)。

    顶层其他图片(文件名不含 preview)仅统计,不移动。
    """
    result = DirResult()
    top_images = sorted(p for p in model_dir.iterdir() if is_preview_image(p))
    result.other_images = sorted(
        p.name
        for p in model_dir.iterdir()
        if is_image_file(p) and not PREVIEW_MARKER.search(p.stem)
    )
    if not top_images:
        return result

    target = find_previews_dir(model_dir) or model_dir / PREVIEWS_DIRNAME
    for src in top_images:
        dst = target / src.name
        if dst.exists():
            result.conflicts.append(src.name)
            continue
        result.plan.append(MovePlan(src, dst))
    return result


def plan_rename(model_dir: Path) -> DirResult:
    """重命名模式:把顶层与 previews/ 下的所有图片统一命名为 previewNN。

    - 已符合 previewNN 命名的文件保持原名;若位于顶层则仅移入 previews/
    - 其余图片按稳定顺序(先 previews/ 内,后顶层,各自按名称排序)分配
      未占用的最小编号,从 01 开始
    - 编号上限为 MAX_PREVIEW_INDEX,超出视为错误
    """
    result = DirResult()
    previews = find_previews_dir(model_dir)
    target = previews or model_dir / PREVIEWS_DIRNAME

    candidates: list[Path] = []
    if previews is not None:
        candidates.extend(sorted(p for p in previews.iterdir() if is_image_file(p)))
    candidates.extend(sorted(p for p in model_dir.iterdir() if is_image_file(p)))

    used: set[int] = set()
    for c in candidates:
        match = PREVIEW_NUMBER_RE.match(c.stem)
        if match:
            used.add(int(match.group(1)))

    # 跟踪本计划内已产生的目标路径,避免两个操作规划到同一目标
    planned_targets: set[Path] = set()
    next_index = 1
    for c in candidates:
        match = PREVIEW_NUMBER_RE.match(c.stem)
        if match:
            # 已规范命名:若已在 previews/ 内则无需处理,否则移入 previews/
            dst = target / c.name
            if dst == c:
                continue
            if dst.exists() or dst in planned_targets:
                result.conflicts.append(c.name)
                continue
            planned_targets.add(dst)
            result.plan.append(MovePlan(c, dst))
            continue

        # 未规范命名:分配最小未占用编号
        while next_index in used:
            next_index += 1
        if next_index > MAX_PREVIEW_INDEX:
            result.errors.append(
                f'{model_dir.name}: 待重命名图片超过 {MAX_PREVIEW_INDEX} 张,编号耗尽,'
                '该目录未处理'
            )
            break
        used.add(next_index)
        dst = target / f'preview{next_index:02d}{c.suffix}'
        next_index += 1
        if dst.exists() or dst in planned_targets:
            result.conflicts.append(c.name)
            continue
        planned_targets.add(dst)
        result.plan.append(MovePlan(c, dst))
    return result


def apply_plan(plan: list[MovePlan]) -> int:
    """执行文件操作,返回成功项数。dst 的父目录不存在时自动创建。"""
    for item in plan:
        item.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.src), str(item.dst))
    return len(plan)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--apply', action='store_true',
                        help='真正创建 previews/ 并移动/重命名文件;缺省为 dry-run')
    parser.add_argument('--rename', action='store_true',
                        help='重命名模式:把顶层与 previews/ 下的图片统一命名为 previewNN')
    parser.add_argument('--no-regenerate', action='store_true',
                        help='执行后不重跑 generate_model_readmes.py(默认会重跑)')
    parser.add_argument('--root', choices=[r.name for r in ROOT_DIRS],
                        help='只处理指定根目录(默认全部)')
    parser.add_argument('--only', metavar='REL_PATH',
                        help='只处理单个模型目录(相对仓库根,如 Models/0001/xxx)')
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.only:
        only_dir = WORKSPACE_ROOT / args.only
        if not only_dir.is_dir():
            print(f'错误:目录不存在: {args.only}', file=sys.stderr)
            return 2
        model_dirs = [only_dir]
    else:
        roots = [r for r in ROOT_DIRS if args.root is None or r.name == args.root]
        model_dirs = collect_model_dirs(roots, rename_mode=args.rename)

    mode_name = 'RENAME(重命名)' if args.rename else 'MOVE(移动)'
    run_mode = 'APPLY(执行)' if args.apply else 'DRY-RUN(预览)'
    print(f'模式: {run_mode} {mode_name}  模型目录数: {len(model_dirs)}')
    print('-' * 60)

    total_ops = 0
    total_conflicts = 0
    total_other = 0
    processed = 0
    unchanged = 0
    error_dirs = 0

    for model_dir in model_dirs:
        rel = model_dir.relative_to(WORKSPACE_ROOT).as_posix()
        result = plan_rename(model_dir) if args.rename else plan_move(model_dir)

        if result.errors:
            error_dirs += 1
            for message in result.errors:
                print(f'错误:{rel}: {message}', file=sys.stderr)
            continue

        if not result.has_work:
            if result.other_images:
                processed += 1
                total_other += len(result.other_images)
                print(rel)
                for name in result.other_images:
                    print(f'    保留(非 preview 命名) {name}')
            else:
                unchanged += 1
            continue

        processed += 1
        total_ops += len(result.plan)
        total_conflicts += len(result.conflicts)
        total_other += len(result.other_images)

        prefix = '' if args.apply else '将'
        print(rel)
        for item in result.plan:
            dst_rel = item.dst.relative_to(model_dir).as_posix()
            print(f'    {prefix}{item.verb} {item.src.name} -> {dst_rel}')
        for name in result.conflicts:
            print(f'    跳过(目标已存在) {name}')
        for name in result.other_images:
            print(f'    保留(非 preview 命名) {name}')

        if args.apply and result.plan:
            applied = apply_plan(result.plan)
            print(f'    已执行 {applied} 个文件操作')

    print('-' * 60)
    print(f'处理目录: {processed}  未变更: {unchanged}  文件操作: {total_ops}  '
          f'冲突跳过: {total_conflicts}  保留的其他图片: {total_other}')

    if args.apply and total_ops > 0 and not args.no_regenerate:
        print('正在重跑 generate_model_readmes.py 更新 README 引用 ...')
        rc = run_generate_readmes()
        if rc != 0:
            print('错误:generate_model_readmes.py 返回非零,README 引用可能未更新', file=sys.stderr)
            return rc
    elif args.apply and total_ops > 0 and args.no_regenerate:
        print('提示:已跳过 README 重生成(--no-regenerate)。请手动运行 '
              'python .github/scripts/models_organize/03_generate&update_model_readmes.py 更新引用。')

    # 冲突文件会同时被顶层与 previews/ 收集,导致 README 重复引用,必须提示
    if total_conflicts > 0:
        print('警告:存在冲突文件未处理(见上),请手动处理以免 README 重复引用', file=sys.stderr)
        return 3
    if error_dirs > 0:
        print(f'错误:{error_dirs} 个目录因编号耗尽等原因未处理', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
