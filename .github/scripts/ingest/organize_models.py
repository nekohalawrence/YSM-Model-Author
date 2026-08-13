#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型归档工具（本仓库专用）——按作者将待归档的 .ysm 移入 Models/ 或 Other-YSM-Models/。

作者识别数据源（按优先级）：
  1. Models/<编号>/README.md 的 ## Author 段第一个 - **Name**:（编号 = 目录名）
  2. 仓库根 README.md 的"作者索引"表格（仅当编号目录存在但缺 README 时补充）

归档规则：
  - 命中作者    -> Models/<编号>/<模型文件夹>/
  - 未命中作者  -> Other-YSM-Models/<模型文件夹>/
  - 未命中任何作者 -> 创建 Models/<max编号+1>/ + README.md（模仿现有作者 README 风格），再建模型文件夹
  - 同一模型的多个版本（如 神吞 / 神吞二阶段）自动合并进同一模型文件夹
  - 同批处理的同作者文件共享同一作者编号（运行时索引回流，避免重复建目录）
  - 移动时跟随同 stem 的附属文件（预览图 / 压缩包 / 说明文档）
  - 默认只归档；需要联动其他脚本时用 --with-* 显式叠加（也可用 pipeline.py 编排）

模型文件夹命名：
  - 取 ysm 内部 <name> 与文件名两个名称合并
  - 语言不一致时用 _ 隔开（中文在前，英文在后）；语言一致时取更完整（更长）的名称
  - 作者名支持 YSM 2.5+ 的 <author> 块结构（多作者按顺序列出，主作者在前）

用法:
  python .github/scripts/ingest/organize_models.py <文件或目录>... [选项]

选项:
  --apply               真正执行移动/创建（默认 dry-run，只打印计划）
  --root PATH           指定仓库根目录（默认自动检测 cwd/脚本位置）
  --with-authors-index  归档成功后重建作者数据 authors.json（build_authors_index.py）
  --with-rename         归档成功后运行 rename_model_folders.py --apply 格式化文件夹名
  --with-gen-readmes    归档成功后运行 generate_model_readmes.py 生成模型 README
  --with-readme-table   归档成功后运行 build_readme_authors.py 更新根 README 作者索引
  --verbose             打印匹配细节
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import models as lib_models
from lib import paths as lib_paths
from lib import readme as lib_readme
from lib import ysm as lib_ysm

# .ysm 解析/作者分类/平台映射（复用 lib/ysm.py；别名保留以兼容 verify_real_samples
# 等外部按模块名引用的调用方）
extract_metadata = lib_ysm.extract_metadata
classify_authors = lib_ysm.classify_authors
load_platform_map = lib_ysm.load_platform_map
map_platforms = lib_ysm.map_platforms

# 新作者 README 的生成与默认 Role（统一由 publish/format_author_readme.py 负责）
from publish.format_author_readme import TARGET_ROLE, format_author_name, render_author_readme

# 作者 README 解析相关（复用 lib/readme.py 统一实现；仅保留实际使用的绑定）
normalize_alias = lib_readme.normalize_alias
build_author_index = lib_readme.build_author_index
find_author = lib_readme.find_author

# 命名/评级/去重（复用 lib/models.py 统一实现）
has_cjk = lib_models.has_cjk
normalize_name_for_cmp = lib_models.normalize_name_for_cmp
clean_file_stem = lib_models.clean_file_stem
same_model = lib_models.same_model

# JSON/文本读写与路径（复用 lib/paths.py 统一实现）
find_workspace_root = lib_paths.find_workspace_root



# Windows 文件名非法字符与尾点/尾空格
ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TRAILING_DOT_SPACE_RE = re.compile(r'[.\s]+$')

WINDOWS_RESERVED = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}





# ---------------------------------------------------------------------------
# 平台信息与 models_meta 数据（外置于 .github/data/meta/）
# ---------------------------------------------------------------------------
def _meta_path(root: Path, fname: str) -> Path:
    """数据路径：优先跟随调用方 root（临时仓库/测试），否则用 lib 语义路径。"""
    if root and root != lib_paths.WORKSPACE_ROOT:
        return root / '.github' / 'data' / 'meta' / fname
    return lib_paths.data_path('meta', fname)





def load_models_meta(root: Path) -> dict:
    """读取 co-creator 元数据（.github/data/meta/models_meta.json）"""
    return lib_paths.load_json(_meta_path(root, 'models_meta.json'), {})


def save_models_meta(root: Path, meta: dict) -> None:
    """写 co-creator 元数据（幂等合并由调用方保证）"""
    lib_paths.save_json(_meta_path(root, 'models_meta.json'), meta)


# ---------------------------------------------------------------------------
# 模型文件夹命名
# ---------------------------------------------------------------------------
def build_model_folder_name(inner_name: str | None, file_stem: str) -> str:
    """合并内部 <name> 与文件名：语言不一致 -> '中文_英文'；语言一致 -> 取更完整的。
    单侧缺失时用另一侧；都缺失回退到文件主干。"""
    a = (inner_name or '').strip()
    b = clean_file_stem(file_stem)

    if not a:
        return b or 'unnamed_model'
    if not b:
        return a

    if normalize_name_for_cmp(a) == normalize_name_for_cmp(b):
        return a

    a_cjk, b_cjk = has_cjk(a), has_cjk(b)
    if a_cjk != b_cjk:
        return f'{a}_{b}' if a_cjk else f'{b}_{a}'

    # 语言一致：取更完整（更长）者；相同长度优先内部名
    if len(a) >= len(b):
        return a
    return b


def sanitize_folder_name(name: str) -> str:
    name = ILLEGAL_CHARS_RE.sub('_', name)
    name = TRAILING_DOT_SPACE_RE.sub('', name)
    name = name.strip()
    if not name:
        name = 'unnamed_model'
    if name.upper() in WINDOWS_RESERVED:
        name = '_' + name
    return name


# ---------------------------------------------------------------------------
# 重复检测
# ---------------------------------------------------------------------------
def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1 << 16), b''):
                h.update(chunk)
    except OSError:
        return ''
    return h.hexdigest()


def find_duplicate(target_author_dir: Path, folder_name: str,
                   input_sha: str) -> tuple[str | None, str]:
    """在目标作者目录下查找重复。返回 (原因, 说明)；None 表示无重复。
    优先内容(sha256)匹配，其次规范化同名文件夹。"""
    norm_folder = normalize_name_for_cmp(folder_name)

    if target_author_dir.is_dir():
        for sub in target_author_dir.iterdir():
            if sub.is_dir() and not sub.name.startswith('.'):
                if normalize_name_for_cmp(sub.name) == norm_folder:
                    # 空壳同名文件夹（无 .ysm 内容）：优先填充而非视为重复
                    if not any(f.suffix.lower() == '.ysm'
                               for f in sub.rglob('*') if f.is_file()):
                        continue
                    return 'folder', f"已存在同名模型文件夹 Models/{target_author_dir.name}/{sub.name}"
                for ysm in sub.rglob('*'):
                    if ysm.is_file() and ysm.suffix.lower() == '.ysm':
                        if file_sha256(ysm) == input_sha:
                            rel = ysm.relative_to(target_author_dir.parent)
                            return 'content', f"内容相同的文件已存在于 Models/{rel.as_posix()}"
    return None, ''


# ---------------------------------------------------------------------------
# 同一模型的多个版本 -> 合并到已有文件夹（复用 lib/models.py 的 same_model）
# ---------------------------------------------------------------------------
def find_same_model_folder(target_dir: Path, folder_name: str) -> Path | None:
    """在目标作者目录下找与 folder_name 属同一模型的已有文件夹（排除完全同名）。
    命中则返回该文件夹路径（同模型多版本合并）；否则 None。"""
    if not target_dir.is_dir():
        return None
    norm = normalize_name_for_cmp(folder_name)
    for sub in sorted(target_dir.iterdir()):
        if not (sub.is_dir() and not sub.name.startswith('.')):
            continue
        if normalize_name_for_cmp(sub.name) == norm:
            continue  # 完全同名由重复检测处理
        if same_model(folder_name, sub.name):
            return sub
    return None


# ---------------------------------------------------------------------------
# 附属文件跟随（预览图 / 压缩包 / 说明文档）
# ---------------------------------------------------------------------------
SIDECAR_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.zip', '.7z', '.rar', '.txt', '.json'}


def collect_sidecars(src_dir: Path, stem: str, src_path: Path) -> list[Path]:
    """收集与 .ysm 同 stem 的附属文件；源目录仅一个 ysm 时额外跟随 preview*。"""
    sidecars: list[Path] = []
    for f in sorted(src_dir.glob(stem + '.*')):
        if f == src_path or f.suffix.lower() not in SIDECAR_EXTS:
            continue
        sidecars.append(f)
    ysm_count = sum(1 for f in src_dir.glob('*') if f.suffix.lower() == '.ysm')
    if ysm_count <= 1:
        for f in sorted(src_dir.glob('preview*')):
            if f.is_file() and f not in sidecars:
                sidecars.append(f)
    return sidecars


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def collect_ysm_files(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for inp in inputs:
        if inp.is_file() and inp.suffix.lower() == '.ysm':
            files.append(inp)
        elif inp.is_dir():
            # Windows 文件系统大小写不敏感：两个 pattern 会重复命中，需按规范化路径去重
            found = list(inp.rglob('*.ysm')) + list(inp.rglob('*.YSM'))
            files.extend(f for f in found if f.is_file())
        else:
            print(f"[错误] 输入不存在或非 .ysm 文件: {inp}")
    seen: set[str] = set()
    unique: list[Path] = []
    for f in files:
        key = os.path.normcase(str(f.resolve()))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return sorted(unique, key=lambda p: str(p))


def next_author_id(models_dir: Path) -> str:
    ids = [int(d.name) for d in models_dir.iterdir()
           if d.is_dir() and re.fullmatch(r'\d{4}', d.name)]
    return f'{max(ids) + 1 if ids else 1:04d}'


def update_root_readme(root: Path) -> None:
    script = root / '.github' / 'scripts' / 'publish' / 'build_readme_authors.py'
    if not script.is_file():
        print(f"  [警告] 未找到 {script}，跳过根 README 索引更新")
        return
    print("  更新根 README 作者索引...")
    subprocess.run([sys.executable, str(script)], cwd=root, check=False)


def build_authors_index(root: Path) -> None:
    """重建集中作者数据 authors.json（新作者归档后供后续脚本统一读取）。"""
    script = root / '.github' / 'scripts' / 'publish' / 'build_authors_index.py'
    if not script.is_file():
        print(f"  [警告] 未找到 {script}，跳过作者数据重建")
        return
    print("  重建集中作者数据 authors.json...")
    subprocess.run([sys.executable, str(script)], cwd=root, check=False)


def run_rename_model_folders(root: Path) -> None:
    script = root / '.github' / 'scripts' / 'naming' / 'rename_model_folders.py'
    if not script.is_file():
        print(f"  [警告] 未找到 {script}，跳过文件夹名称格式化")
        return
    print("  运行 rename_model_folders.py 格式化模型文件夹名称...")
    subprocess.run([sys.executable, str(script), '--apply'], cwd=root, check=False)


def run_generate_model_readmes(root: Path) -> None:
    script = root / '.github' / 'scripts' / 'publish' / 'generate_model_readmes.py'
    if not script.is_file():
        print(f"  [警告] 未找到 {script}，跳过模型 README 生成")
        return
    print("  运行 generate_model_readmes.py 生成模型 README...")
    subprocess.run([sys.executable, str(script)], cwd=root, check=False)


def archive_one(path: Path, target_dir: Path, folder_name: str, mode: str,
                apply: bool, root: Path, verbose: bool) -> str | None:
    """把单个 .ysm 归档到目标作者目录。返回 'moved'/'copied'/'skipped'；dry-run 返回 None。

    处理重复检测、同模型多版本合并、sidecar 跟随。mode='move'（主作者）或 'copy'。
    """
    dup_reason, dup_note = find_duplicate(target_dir, folder_name, file_sha256(path))
    if dup_reason:
        print(f"  [跳过] {dup_note}")
        return 'skipped'

    dest_dir = find_same_model_folder(target_dir, folder_name)
    if dest_dir is not None:
        print(f"  合并进已有模型文件夹: {dest_dir.relative_to(root)}")
    else:
        dest_dir = target_dir / folder_name

    sidecars = collect_sidecars(path.parent, path.stem, path)
    verb = '复制' if mode == 'copy' else '移动'
    if not apply:
        print(f"  [计划] {verb} -> {dest_dir.relative_to(root)}/{path.name}")
        if sidecars:
            print(f"  [计划] 跟随{verb}附属文件: {', '.join(s.name for s in sidecars)}")
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if dest.exists():
        print(f"  [跳过] 目标文件已存在: {dest.relative_to(root)}")
        return 'skipped'
    files = [path] + sidecars
    if sidecars:
        print(f"  跟随{verb}附属文件: {', '.join(s.name for s in sidecars)}")
    for f in files:
        d = dest_dir / f.name
        if mode == 'copy':
            shutil.copy2(str(f), str(d))
        else:
            shutil.move(str(f), str(d))
    print(f"  已{verb} -> {dest_dir.relative_to(root)}/（{len(files)} 个文件）")
    return 'copied' if mode == 'copy' else 'moved'


def upsert_author_index(root: Path, author_id: str, block: dict) -> None:
    """把新作者增量写入集中作者数据 authors.json（不重建全部）；已存在则跳过。

    新作者归档时即时登记，后续脚本（audit 合并、README 生成）无需先跑
    build_authors_index 也能看到该作者。
    """
    path = lib_paths.data_path('meta', 'authors.json')
    data = lib_paths.load_json(path, {})
    authors = data.setdefault('authors', {})
    if author_id in authors:
        return
    name_tags = format_author_name(block['name'])  # '#鸡姬 | #raw_chicken'
    names = [t.strip() for t in name_tags.split('|') if t.strip()]
    authors[author_id] = {
        'name': names,
        'readme': f'Models/{author_id}/README.md',
        'role': TARGET_ROLE,
        'platforms': dict(block.get('contacts') or {}),
    }
    lib_paths.save_json(path, data)
    print(f"  已登记到 authors.json: {author_id} {names}")


def resolve_author_id(block: dict, alias_to_id: dict, runtime_index: dict,
                      root: Path, apply: bool, verbose: bool,
                      result: dict) -> str:
    """把作者块匹配/分配到作者编号；新作者时创建目录与 README 并注册运行时索引。"""
    author_id, note = find_author(block['name'], {**alias_to_id, **runtime_index}, verbose)
    if author_id:
        return author_id
    new_id = next_author_id(root / 'Models')
    key = normalize_alias(block['name'])
    if key:
        runtime_index.setdefault(key, new_id)
    result['new_author'] = True
    target_dir = root / 'Models' / new_id
    if apply:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / 'README.md').write_bytes(
            render_author_readme(new_id, block['name']).encode('utf-8'))
        upsert_author_index(root, new_id, block)
        print(f"  新建作者目录 {new_id} 并生成 README.md（{block['name']}）")
    else:
        print(f"  [计划] 新建作者目录 {new_id} 并生成 README.md（{block['name']}）")
    return new_id


def process_file(path: Path, root: Path, alias_to_id: dict[str, str],
                 runtime_index: dict[str, str], platform_map: dict[str, str],
                 apply: bool, verbose: bool) -> dict:
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    print(f"\n== {rel} ==")
    result = {'action': 'skipped', 'reason': '', 'new_author': False}

    meta = extract_metadata(path)
    if not meta:
        result['reason'] = '文件读取失败'
        return result
    inner_name = meta.get('name') or ''
    blocks = meta.get('author_blocks') or []

    if not blocks:
        print(f"  未识别到作者，将放入 Other-YSM-Models")
        target_dir = root / 'Other-YSM-Models'
        folder_name = sanitize_folder_name(build_model_folder_name(inner_name, path.stem))
        print(f"  模型文件夹名: {folder_name}")
        status = archive_one(path, target_dir, folder_name, 'move', apply, root, verbose)
        if status in ('moved', 'copied'):
            result['action'] = status
        elif status == 'skipped':
            result['reason'] = '重复或冲突'
        return result

    # 多作者分类：主作者（role 含"模型"，无则第一个）移动；其他 model 作者复制；其余记录为 co-creator
    primary, model_blocks, co_creators = classify_authors(blocks)
    print(f"  作者列表: " + ', '.join(
        f"{b['name']}({'模型' if '模型' in (b.get('role') or '') else b.get('role') or '无角色'})"
        for b in blocks))
    print(f"  主作者(分类): {primary['name']}；归档目标 {len(model_blocks)} 个，co-creator {len(co_creators)} 个")

    # 解析每个归档作者的编号（新作者建目录；主作者 mode=move，其余 mode=copy）
    targets: list[tuple[str, str, dict]] = []  # (author_id, mode, block)
    for block in model_blocks:
        aid = resolve_author_id(block, alias_to_id, runtime_index, root, apply, verbose, result)
        mode = 'move' if block is primary else 'copy'
        targets.append((aid, mode, block))
    # 同编号去重：move 优先
    dedup: dict[str, tuple[str, dict]] = {}
    for aid, mode, block in targets:
        if aid not in dedup or (mode == 'move' and dedup[aid][0] != 'move'):
            dedup[aid] = (mode, block)

    folder_name = sanitize_folder_name(build_model_folder_name(inner_name, path.stem))
    print(f"  模型文件夹名: {folder_name}")

    statuses = []
    # 先复制目标后移动主作者，保证 copy 时源文件（含 sidecar）仍存在
    for aid, (mode, block) in dedup.items():
        if mode == 'copy':
            statuses.append(archive_one(path, root / 'Models' / aid, folder_name,
                                        'copy', apply, root, verbose))
    for aid, (mode, block) in dedup.items():
        if mode == 'move':
            statuses.append(archive_one(path, root / 'Models' / aid, folder_name,
                                        'move', apply, root, verbose))

    if any(s in ('moved', 'copied') for s in statuses):
        result['action'] = 'moved' if 'moved' in statuses else 'copied'
    elif any(s == 'skipped' for s in statuses):
        result['reason'] = '重复或冲突'

    # co-creator 与平台信息写入 models_meta（幂等，仅 apply 且确有归档时）
    if apply and any(s in ('moved', 'copied') for s in statuses):
        meta_data = load_models_meta(root)
        changed = False
        for aid, (mode, block) in dedup.items():
            co = [b for b in blocks if b is not block]
            if not co:
                continue
            entry = {'co_creators': [
                {'name': b['name'], 'role': b.get('role', ''),
                 'platforms': map_platforms(b.get('contacts') or {}, platform_map)}
                for b in co]}
            key = f'{aid}/{folder_name}'
            if meta_data.get(key) != entry:
                meta_data[key] = entry
                changed = True
        if changed:
            save_models_meta(root, meta_data)
            print(f"  已更新 models_meta.json（{sum(1 for k, v in meta_data.items() if v.get('co_creators'))} 条 co-creator 记录）")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('inputs', nargs='+', help='.ysm 文件或目录（目录递归收集 *.ysm）')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认 dry-run）')
    parser.add_argument('--root', metavar='PATH', default=None, help='仓库根目录（默认自动检测）')
    parser.add_argument('--with-authors-index', action='store_true',
                        help='归档成功后重建集中作者数据 authors.json（build_authors_index.py）')
    parser.add_argument('--with-rename', action='store_true',
                        help='归档成功后运行 rename_model_folders.py --apply 格式化文件夹名')
    parser.add_argument('--with-gen-readmes', action='store_true',
                        help='归档成功后运行 generate_model_readmes.py 生成模型 README')
    parser.add_argument('--with-readme-table', action='store_true',
                        help='归档成功后运行 build_readme_authors.py 更新根 README 作者索引')
    parser.add_argument('--verbose', action='store_true', help='打印匹配细节')
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else find_workspace_root()
    models_dir = root / 'Models'
    if not models_dir.is_dir():
        print(f"错误: {models_dir} 目录不存在（可用 --root 指定仓库根目录）")
        return 2

    alias_to_id, id_to_name = build_author_index(models_dir, root / 'README.md')
    print(f"作者索引: {len(alias_to_id)} 个别名 / {len(id_to_name)} 位作者")
    platform_map = load_platform_map(root)

    files = collect_ysm_files([Path(x) for x in args.inputs])
    if not files:
        print("没有可处理的 .ysm 文件。")
        return 1

    mode = "执行" if args.apply else "预览（dry-run，加 --apply 执行）"
    print(f"模式: {mode} | 共 {len(files)} 个文件")

    moved = new_authors = skipped = 0
    moved_any = False
    runtime_index: dict[str, str] = {}  # 本次运行新建的作者（同批同作者文件复用同一编号）
    for f in files:
        res = process_file(f, root, alias_to_id, runtime_index, platform_map,
                           args.apply, args.verbose)
        if res['action'] in ('moved', 'copied'):
            moved += 1
            moved_any = True
        elif res['reason']:
            skipped += 1
        if res['new_author']:
            new_authors += 1

    # 可选联动：默认只归档，用 --with-* 显式叠加其他脚本（顺序固定）
    # 重建作者数据 → 格式化文件夹名 → 生成模型 README → 更新根 README 索引
    if args.apply and moved_any:
        if args.with_authors_index:
            build_authors_index(root)
        if args.with_rename:
            run_rename_model_folders(root)
        if args.with_gen_readmes:
            run_generate_model_readmes(root)
        if args.with_readme_table:
            update_root_readme(root)

    print("\n" + "=" * 50)
    print(f"完成: 移动 {moved}，跳过 {skipped}，新建作者 {new_authors}（{mode}）")
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
