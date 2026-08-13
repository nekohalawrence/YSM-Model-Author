#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型库整理工具（本仓库专用）——处理"已有库"的整理维护。

职责分工：organize_models.py 管入库（_Model-Inbox → Models/），本脚本管库内整理：
  1. 重新分类（--reclassify）：扫描 Models/<编号>/<模型>/ 下 .ysm 的主作者，
     与目录编号比对；归属错误时报告，--apply 移动到正确作者。
  2. 合并重复作者（--merge-authors）：按"平台账号相同 或 规范化名字相等"找候选，
     逐对 y/n 确认后合并（移动模型目录、并名字、迁移 models_meta 键、重建索引）。
  3. 空壳报告（--report-empty）：无 .ysm 的模型文件夹（空壳）与无模型作者目录。
  4. 全部功能默认 dry-run（只读报告），--apply 才写盘；合并作者必须逐对确认。

用法:
  python .github/scripts/cli.py audit                    # 全量审计报告
  python .github/scripts/cli.py audit --reclassify --apply   # 应用重新分类
  python .github/scripts/cli.py audit --merge-authors --apply # 合并重复作者（交互确认）
  python .github/scripts/cli.py audit --report-empty     # 空壳报告
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import models as lib_models
from lib import paths as lib_paths
from lib import readme as lib_readme
from lib import ysm as lib_ysm

WORKSPACE_ROOT = lib_paths.WORKSPACE_ROOT
MODELS_DIR = WORKSPACE_ROOT / 'Models'


def is_author_dir(path: Path) -> bool:
    """4 位数字编号的作者目录。"""
    return path.is_dir() and re.fullmatch(r'\d{4}', path.name) is not None


def iter_author_dirs() -> list[Path]:
    return [d for d in sorted(MODELS_DIR.iterdir()) if is_author_dir(d)]


def iter_model_dirs(author_dir: Path):
    for d in sorted(author_dir.iterdir()):
        if d.is_dir() and not d.name.startswith('.') and d.name.lower() != 'previews':
            yield d


def model_owner(model_dir: Path) -> tuple[str | None, str]:
    """解析模型目录主作者名（复用 lib/ysm.py 统一实现）。"""
    return lib_ysm.model_owner(model_dir)


def count_ysm(directory: Path) -> int:
    """目录（含子目录）下的 .ysm 文件数。"""
    return sum(1 for f in directory.rglob('*')
               if f.is_file() and f.suffix.lower() == '.ysm')


# ---------------------------------------------------------------------------
# 重新分类（--reclassify）
# ---------------------------------------------------------------------------
def scan_reclassify() -> list[dict]:
    """扫描归属差异：模型 .ysm 主作者匹配到的作者编号 ≠ 当前目录编号。"""
    alias_to_id, _ = lib_readme.build_author_index(MODELS_DIR, WORKSPACE_ROOT / 'README.md')
    issues: list[dict] = []
    for author_dir in iter_author_dirs():
        for model_dir in iter_model_dirs(author_dir):
            owner_name, src_file = model_owner(model_dir)
            if not owner_name:
                continue
            matched, note = lib_readme.find_author(owner_name, alias_to_id)
            if matched and matched != author_dir.name:
                issues.append({
                    'model_dir': model_dir,
                    'cur': author_dir.name,
                    'owner': owner_name,
                    'matched': matched,
                    'note': note,
                    'src': src_file,
                })
    return issues


def move_model_dir(model_dir: Path, target_author: str) -> str:
    """把模型目录移到 Models/<target_author>/ 下；处理目标同名/同模型冲突。"""
    dest_author = MODELS_DIR / target_author
    dest = dest_author / model_dir.name
    if dest.exists():
        return f'[冲突] 目标已存在: {dest.relative_to(WORKSPACE_ROOT)}'
    # 目标作者下已有同模型（same_model）目录：提示不自动合并（避免误并不同版本）
    if dest_author.is_dir():
        for sub in dest_author.iterdir():
            if sub.is_dir() and sub.name != model_dir.name \
                    and lib_models.same_model(model_dir.name, sub.name):
                return f'[冲突] 目标作者下已有同模型: {sub.relative_to(WORKSPACE_ROOT)}'
    dest_author.mkdir(parents=True, exist_ok=True)
    shutil.move(str(model_dir), str(dest))
    return f'[移动] {model_dir.relative_to(WORKSPACE_ROOT)} -> {dest.relative_to(WORKSPACE_ROOT)}'


def reclassify(apply: bool) -> int:
    """重新分类：报告/移动归属错误的模型目录。返回差异数。"""
    issues = scan_reclassify()
    if not issues:
        print('重新分类: 未发现归属差异（所有模型 .ysm 主作者与目录编号一致）。')
        return 0
    print(f'重新分类: 发现 {len(issues)} 个归属差异:')
    for it in issues:
        rel = it['model_dir'].relative_to(WORKSPACE_ROOT)
        print(f"  {rel}  (.ysm 主作者「{it['owner']}」匹配到 {it['matched']},"
              f" 当前在 {it['cur']}; {it['note']})")
    if not apply:
        print('dry-run: 未移动;加 --apply 逐项确认后执行')
        return len(issues)

    # 迁移 models_meta 键（B/xxx -> A/xxx）——先记录再移动
    meta_path = lib_paths.data_path('meta', 'models_meta.json')
    meta = lib_paths.load_json(meta_path, {})
    key_map: dict[str, str] = {}
    for it in issues:
        old_key = f"{it['cur']}/{it['model_dir'].name}"
        new_key = f"{it['matched']}/{it['model_dir'].name}"
        if old_key in meta:
            key_map[old_key] = new_key
    moved = 0
    for i, it in enumerate(issues, 1):
        rel = it['model_dir'].relative_to(WORKSPACE_ROOT)
        ans = _ask(f"[{i}/{len(issues)}] 移动 {rel} 到 {it['matched']}？"
                   f"（主作者「{it['owner']}」, {it['note']}） (y/n/q): ").lower()
        if ans in ('q', 'quit'):
            break
        if ans not in ('y', 'yes'):
            continue
        msg = move_model_dir(it['model_dir'], it['matched'])
        print(f"  {msg}")
        if msg.startswith('[移动]'):
            moved += 1
    if key_map:
        for old_key, new_key in key_map.items():
            meta[new_key] = meta.pop(old_key)
        lib_paths.save_json(meta_path, meta)
        print(f"  models_meta 键迁移 {len(key_map)} 条")
    print(f'重新分类完成: 移动 {moved} 个模型目录')
    return moved


# ---------------------------------------------------------------------------
# 合并重复作者（--merge-authors）
# ---------------------------------------------------------------------------
def normalize_platform_val(key: str, val: str) -> str:
    """平台值归一化（URL 去协议/尾部斜杠，便于对比）。"""
    v = val.strip().lower()
    v = re.sub(r'^https?://', '', v)
    return v.rstrip('/')


def find_merge_candidates() -> list[tuple[str, str, str]]:
    """找重复作者候选 (a, b, 原因)。依据：平台账号相同 或 规范化名字相等。"""
    authors = lib_readme.load_authors_index().get('authors') or {}
    pairs: dict[tuple[str, str], str] = {}  # (小编号, 大编号) -> 原因

    def add_pair(x: str, y: str, reason: str) -> None:
        if x == y:
            return
        a, b = sorted([x, y])
        pairs.setdefault((a, b), reason)

    # 平台相同（QQ/Bilibili/YouTube 等账号一致）
    platform_map: dict[tuple, list[str]] = {}
    for aid, entry in authors.items():
        for key, val in (entry.get('platforms') or {}).items():
            if key.lower() not in ('qq', 'bilibili', 'youtube', 'twitter', 'discord'):
                continue
            platform_map.setdefault((key.lower(), normalize_platform_val(key, val)), []).append(aid)
    for ids in platform_map.values():
        if len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    add_pair(ids[i], ids[j], f"平台相同: {ids[i]}/{ids[j]}")

    # 规范化名字相等（全角/大小写/# 差异归一后相同）
    name_map: dict[str, list[str]] = {}
    for aid, entry in authors.items():
        for name in entry.get('name') or []:
            norm = lib_readme.normalize_alias(name)
            if norm:
                name_map.setdefault(norm, []).append(aid)
    for norm, ids in name_map.items():
        if len(ids) > 1:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    add_pair(ids[i], ids[j], f"名字相同: {norm}")

    return [(a, b, r) for (a, b), r in sorted(pairs.items())]


def _merge_name_values(existing: str, drop_name: str) -> str:
    """合并两个 Name 值（' | ' 分隔），按规范化别名去重，保留原始顺序。

    防止合并时把 keep 已有的别名（如「炽湮」）重复并入。"""
    parts = [p.strip() for p in f'{existing} | {drop_name}'.split('|') if p.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        norm = lib_readme.normalize_alias(p)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(p)
    return ' | '.join(out)


def merge_authors(keep: str, drop: str, reason: str) -> str:
    """把 drop 作者合并进 keep：移动模型、并入名字、迁移 models_meta、删除空目录。"""
    keep_dir, drop_dir = MODELS_DIR / keep, MODELS_DIR / drop
    results: list[str] = []

    # 1. 移动模型目录
    if drop_dir.is_dir():
        for model_dir in sorted(drop_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            msg = move_model_dir(model_dir, keep)
            results.append(msg)
        # 2. 并入名字（drop 作者 README 的 Name 值 -> keep README 的 Name 行）
        keep_readme = keep_dir / 'README.md'
        if keep_readme.is_file():
            content = keep_readme.read_text(encoding='utf-8', errors='ignore')
            drop_readme = drop_dir / 'README.md'
            if drop_readme.is_file():
                drop_text = drop_readme.read_text(encoding='utf-8', errors='ignore')
                drop_name = lib_readme.parse_author_name_value(drop_text)
                if drop_name:
                    m = re.search(r'^(?P<indent>\s*-\s*\*\*(?:Name|作者名称)\*\*\s*[:：]\s*)(?P<val>.*)$',
                                  content, re.MULTILINE | re.IGNORECASE)
                    if m:
                        merged = _merge_name_values(m.group('val').strip(), drop_name)
                        content = content[:m.start()] + m.group('indent') + merged + content[m.end():]
                        keep_readme.write_text(content, encoding='utf-8')
                        results.append(f'[名字] {keep}/README.md 并入「{drop_name}」(去重)')
                # 并入平台行（drop Author 段的平台容器行 + 子行；keep 已有键跳过）
                added = _merge_platform_lines(content, drop_text, keep_readme)
                if added:
                    results.append(f'[平台] {keep}/README.md 并入 {added} 条平台行')
        # 3. 删除只剩 README（或空）的被合并作者目录；仍有其他文件则保留并警告
        remaining = [p for p in drop_dir.rglob('*') if p.is_file()]
        if not remaining or (len(remaining) == 1 and remaining[0].name.lower() == 'readme.md'):
            shutil.rmtree(str(drop_dir))
            results.append(f'[删除] 作者目录 Models/{drop}')
        else:
            results.append(f'[保留] Models/{drop} 仍有文件（未删除，需人工处理）')

    # 4. 迁移 models_meta 键 drop/xxx -> keep/xxx
    meta_path = lib_paths.data_path('meta', 'models_meta.json')
    meta = lib_paths.load_json(meta_path, {})
    migrated = 0
    for key in [k for k in meta if k.startswith(f'{drop}/')]:
        meta[f'{keep}/{key.split("/", 1)[1]}'] = meta.pop(key)
        migrated += 1
    if migrated:
        lib_paths.save_json(meta_path, meta)
        results.append(f'[models_meta] 迁移 {migrated} 条键')

    return f"合并 {drop} -> {keep}（{reason}）\n  " + '\n  '.join(results)


def merge_authors_flow(apply: bool) -> int:
    """合并重复作者：候选逐对确认。返回合并对数。"""
    candidates = find_merge_candidates()
    if not candidates:
        print('合并作者: 未发现重复作者候选。')
        return 0
    print(f'合并作者: 发现 {len(candidates)} 个候选对（平台相同 / 名字相同）:')
    merged = 0
    seen_drop: set[str] = set()
    for i, (a, b, reason) in enumerate(candidates, 1):
        if a in seen_drop or b in seen_drop:
            continue  # 已作为被合并方处理
        a_name = _author_display(a)
        b_name = _author_display(b)
        ans = _ask(f"[{i}/{len(candidates)}] 合并 {b}({b_name}) -> {a}({a_name})？"
                   f"（{reason}） (y=合并, s=反向, n=跳过, q=退出): ").lower()
        if ans in ('q', 'quit'):
            break
        if ans in ('s', 'swap'):
            a, b = b, a
        elif ans not in ('y', 'yes'):
            continue
        if not apply:
            print(f'  [计划] {merge_authors(a, b, reason)}')
            continue
        print('  ' + merge_authors(a, b, reason))
        merged += 1
        seen_drop.add(b)
    if merged and apply:
        _rebuild_indexes()
    print(f'合并作者: 共 {merged} 对已合并' if apply else 'dry-run: 未执行')
    return merged


def _rebuild_indexes() -> None:
    """合并后重建集中作者数据与根 README 作者表（drop 作者目录已删，索引需同步）。"""
    for script, label in [('publish/build_authors_index.py', '作者数据 authors.json'),
                          ('publish/build_readme_authors.py', '根 README 作者表')]:
        p = WORKSPACE_ROOT / '.github' / 'scripts' / script
        if not p.is_file():
            print(f'  [警告] 未找到 {p}，跳过{label}重建')
            continue
        print(f'  重建{label}...')
        subprocess.run([sys.executable, str(p)], cwd=WORKSPACE_ROOT, check=False)


def _author_display(author_id: str) -> str:
    """作者编号 -> '首名 (编号)'。"""
    authors = lib_readme.load_authors_index().get('authors') or {}
    entry = authors.get(author_id) or {}
    names = entry.get('name') or []
    return f"{names[0] if names else '?'} ({author_id})"


# 平台行：2 空格容器行（- **SocialPlatform**: #Bilibili）与 4 空格子行（- **Bilibili**: [..](..)）
PLATFORM_LINE_RE = re.compile(r'^\s{2,4}-\s*\*\*([^*]+)\*\*\s*[:：]?\s*(.*)$')


def _merge_platform_lines(keep_content: str, drop_content: str, keep_readme: Path) -> int:
    """把 drop README Author 段的平台行（分类容器行 + 平台子行）并入 keep README。

    按平台子行键去重（keep 已存在的平台不再并入）；返回并入行数。
    """
    def author_scope(text: str) -> list[str]:
        m = lib_readme.AUTHOR_SECTION_RE.search(text)
        return (m.group(1) if m else text).splitlines()

    keep_lines = author_scope(keep_content)
    drop_lines = author_scope(drop_content)
    have = {m.group(1).strip().lower()
            for m in PLATFORM_LINE_RE.finditer('\n'.join(keep_lines)) if m.group(2).strip()}

    new_lines: list[str] = []
    pending_container: str | None = None
    for line in drop_lines:
        if not line.strip():
            continue
        m = PLATFORM_LINE_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        indent = line[:len(line) - len(line.lstrip())]
        is_sub = len(indent.expandtabs(4)) >= 4
        if is_sub:
            if key.lower() in have or not m.group(2).strip():
                continue  # keep 已有该平台或无值：跳过
            if pending_container:
                new_lines.append(pending_container)  # 先输出所属分类容器行
                pending_container = None
            new_lines.append(line.rstrip())
            have.add(key.lower())
        else:
            pending_container = line.rstrip()  # 容器行：等有效子行出现再输出

    if not new_lines:
        return 0
    insert_at = len(keep_content)
    m = lib_readme.AUTHOR_SECTION_RE.search(keep_content)
    if m:
        insert_at = m.start(1) + len(m.group(1).rstrip())
    merged = keep_content[:insert_at] + '\n' + '\n'.join(new_lines) + keep_content[insert_at:]
    keep_readme.write_text(merged, encoding='utf-8')
    return len(new_lines)


def _ask(prompt: str) -> str:
    """安全交互输入（与 kb_tool 一致：Ctrl+C/EOF 视为退出）。"""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return 'q'


# ---------------------------------------------------------------------------
# 空壳报告（--report-empty）
# ---------------------------------------------------------------------------
def report_empty() -> int:
    """报告无 .ysm 的模型文件夹（空壳）与无模型作者目录。返回空壳数。"""
    empty_models: list[Path] = []
    empty_authors: list[Path] = []
    for author_dir in iter_author_dirs():
        models = list(iter_model_dirs(author_dir))
        if not models:
            empty_authors.append(author_dir)
            continue
        for model_dir in models:
            if count_ysm(model_dir) == 0:
                empty_models.append(model_dir)
    print(f'空壳报告:')
    print(f'  无模型作者目录 {len(empty_authors)} 个:')
    for d in empty_authors:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    print(f'  无 .ysm 的模型文件夹 {len(empty_models)} 个:')
    for d in empty_models:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    return len(empty_models) + len(empty_authors)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reclassify', action='store_true', help='重新分类（扫 Models 校验作者归属）')
    parser.add_argument('--merge-authors', action='store_true', help='合并重复作者（逐对确认）')
    parser.add_argument('--report-empty', action='store_true', help='空壳报告（无 .ysm 的文件夹）')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认 dry-run 只报告）')
    args = parser.parse_args()

    if not MODELS_DIR.is_dir():
        print(f'错误: {MODELS_DIR} 目录不存在。')
        return 2

    if args.reclassify:
        return reclassify(args.apply)
    if args.merge_authors:
        return merge_authors_flow(args.apply)
    if args.report_empty:
        return report_empty()

    # 默认：全量审计报告（只读）
    print('== 全量审计（只读）==')
    issues = scan_reclassify()
    print(f'重新分类差异: {len(issues)} 个')
    for it in issues[:20]:
        rel = it['model_dir'].relative_to(WORKSPACE_ROOT)
        print(f"  {rel}  主作者「{it['owner']}」-> {it['matched']}（当前 {it['cur']}）")
    if len(issues) > 20:
        print(f'  ...（其余 {len(issues) - 20} 条略）')
    candidates = find_merge_candidates()
    print(f'重复作者候选: {len(candidates)} 对')
    for a, b, reason in candidates:
        print(f'  {a} ↔ {b}  {reason}')
    print('\n用法提示: --reclassify / --merge-authors / --report-empty 配合 --apply 执行')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
