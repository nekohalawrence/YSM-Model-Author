#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型库整理工具（本仓库专用）——处理"已有库"的整理维护。

职责分工：organize_models.py 管入库（_Model-Inbox → Models/），本脚本管库内整理：
  0. 重复模型删除（--dedupe）：按 sha256 检测 Models/<作者>/ 下内容相同的 .ysm，
     保留一个（文件名与文件夹同名优先），--apply 删除。
  1. 重新分类（--reclassify）：扫描 Models/<编号>/<模型>/ 下 .ysm 的主作者，
     与目录编号比对；归属错误时报告，--apply 移动到正确作者。
  2. 合并重复作者（--merge-authors）：按"平台账号相同 或 规范化名字相等"找候选，
     逐对 y/n 确认后合并（移动模型目录、并名字、迁移 models_meta 键、重建索引）。
  3. 空壳报告（--report-empty）：无 .ysm 的模型文件夹（空壳）与无模型作者目录。
  4. 缺失报告（--report-missing / --report-no-category / --report-no-preview / --report-unknown）：
     统计无分类（作品前缀不在 character/*.json）与无预览图的模型，显示路径；可分开查看；
     --report-unknown 只统计文件夹名含 Unknown 的模型（待确认归属）。
  4. 全部功能默认 dry-run（只读报告），--apply 才写盘；合并作者必须逐对确认。

用法:
  python .github/scripts/cli.py audit                    # 全量审计报告
  python .github/scripts/cli.py audit --dedupe          # 重复模型检测（--apply 删除）
  python .github/scripts/cli.py audit --reclassify --apply   # 应用重新分类
  python .github/scripts/cli.py audit --merge-authors --apply # 合并重复作者（交互确认）
  python .github/scripts/cli.py audit --report-empty     # 空壳报告
  python .github/scripts/cli.py audit --report-missing   # 缺失汇总（无分类+无预览图+完整）
  python .github/scripts/cli.py audit --report-no-category  # 只看无分类（前缀不在 character/*.json）
  python .github/scripts/cli.py audit --report-no-preview   # 只看无预览图
  python .github/scripts/cli.py audit --report-unknown   # 只看文件夹名含 Unknown 的模型
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import console as lib_console
from lib import models as lib_models
from lib import paths as lib_paths
from lib import previews as lib_previews
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


def model_author_blocks(model_dir: Path) -> list[dict]:
    """解析模型目录下第一个 .ysm 的全部作者块（多作者识别用）。"""
    for f in sorted(model_dir.glob('*.ysm')) + sorted(model_dir.glob('*.YSM')):
        blocks = (lib_ysm.extract_metadata(f, quiet=True).get('author_blocks') or [])
        if blocks:
            return blocks
    return []


def count_ysm(directory: Path) -> int:
    """目录（含子目录）下的 .ysm 文件数。"""
    return sum(1 for f in directory.rglob('*')
               if f.is_file() and f.suffix.lower() == '.ysm')


def file_sha256(path: Path) -> str:
    """文件 sha256（读取失败返回空串）。"""
    h = hashlib.sha256()
    try:
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1 << 16), b''):
                h.update(chunk)
    except OSError:
        return ''
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 重复模型删除（--dedupe）
# ---------------------------------------------------------------------------
def cmd_dedupe(apply: bool) -> int:
    """检测并删除作者目录下内容重复的 .ysm（sha256 相同，保留一个）。

    保留规则：文件名与所属文件夹同名（规范命名）优先，否则路径排序第一个。
    默认 dry-run 预览；--apply 执行删除。
    """
    by_hash: dict[str, list[Path]] = {}
    for author in iter_author_dirs():
        for f in sorted(author.rglob('*.ysm')):
            if f.is_file():
                by_hash.setdefault(file_sha256(f), []).append(f)
    groups = {h: fs for h, fs in by_hash.items() if len(fs) > 1}
    if not groups:
        print('未发现重复模型文件（sha256 均唯一）。')
        return 0
    n_files = sum(len(fs) for fs in groups.values())
    print(f'发现 {len(groups)} 组内容重复（共 {n_files} 个文件，将保留 {len(groups)} 个）：')
    removed = 0
    for h, fs in sorted(groups.items(), key=lambda kv: kv[1][0].as_posix()):
        keep = next((f for f in fs if f.stem == f.parent.name), fs[0])
        print(f'\n  组: sha256={h[:12]}…（{len(fs)} 个相同）')
        for f in fs:
            if f == keep:
                print(f'    [保留] {f.relative_to(WORKSPACE_ROOT)}（{f.stat().st_size} 字节）')
            else:
                print(f'    [删除] {f.relative_to(WORKSPACE_ROOT)}（{f.stat().st_size} 字节）')
        if apply:
            for f in fs:
                if f != keep:
                    f.unlink()
                    removed += 1
    if apply:
        print(f'\n已删除 {removed} 个重复文件。')
    else:
        print('\n预览模式（dry-run），未删除。加 --apply 执行删除。')
    return removed


# ---------------------------------------------------------------------------
# 重新分类（--reclassify）
# ---------------------------------------------------------------------------
def scan_reclassify() -> list[dict]:
    """扫描归属差异与多作者复制缺失。

    单作者模型：主作者匹配编号 ≠ 当前目录编号 -> 应移动；
    多作者模型（多个 role 含"模型"的作者）：应复制到各作者目录（当前目录保留，不移动）。
    返回每条含 model_dir/cur/owner/owners/id_list/matched_ids/multi/note。
    """
    alias_to_id, _ = lib_readme.build_author_index(MODELS_DIR, WORKSPACE_ROOT / 'README.md')
    issues: list[dict] = []
    for author_dir in iter_author_dirs():
        for model_dir in iter_model_dirs(author_dir):
            blocks = model_author_blocks(model_dir)
            if not blocks:
                continue
            primary, model_blocks, _ = lib_ysm.classify_authors(blocks)
            if not primary:
                continue
            owners = [b['name'] for b in model_blocks]
            id_list = [lib_readme.find_author(n, alias_to_id)[0] for n in owners]
            matched_ids = sorted({i for i in id_list if i})
            primary_matched, note = lib_readme.find_author(primary['name'], alias_to_id)
            multi = len(model_blocks) > 1
            missing = [i for i in matched_ids
                       if i != author_dir.name and not (MODELS_DIR / i / model_dir.name).exists()]
            unmapped = [o for o, i in zip(owners, id_list) if not i]
            # 单作者归属错误，或多作者存在缺失副本/未匹配作者，才记录
            if (multi and (missing or unmapped)) or \
               (not multi and primary_matched and primary_matched != author_dir.name):
                issues.append({
                    'model_dir': model_dir,
                    'cur': author_dir.name,
                    'owner': primary['name'],
                    'owners': owners,
                    'matched': primary_matched,
                    'id_list': id_list,
                    'matched_ids': matched_ids,
                    'multi': multi,
                    'missing': missing,
                    'unmapped': unmapped,
                    'note': note,
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
    """重新分类：单作者归属错误移动；多作者模型复制缺失副本到各作者目录（当前保留）。"""
    issues = scan_reclassify()
    if not issues:
        print('重新分类: 未发现归属差异（所有模型归属正确且多作者副本完整）。')
        return 0

    # 分组：单作者归属错误 -> 移动；多作者 -> 复制缺失副本（当前目录保留）
    moves: list[dict] = []
    copies: list[dict] = []
    print(f'重新分类: 发现 {len(issues)} 个待处理:')
    for it in issues:
        rel = it['model_dir'].relative_to(WORKSPACE_ROOT)
        if it['multi']:
            missing, unmapped = it['missing'], it['unmapped']
            copies.append(it)
            line = f"  [复制] {rel}  作者: {' / '.join(it['owners'])}  → 复制到 "
            line += (', '.join(f'{i}' for i in missing) if missing else '(无缺失副本)')
            if unmapped:
                line += f"   [未匹配作者: {' / '.join(unmapped)}]"
            print(line)
        else:
            moves.append(it)
            print(f"  [移动] {rel}  (.ysm 主作者「{it['owner']}」匹配到 {it['matched']},"
                  f" 当前在 {it['cur']}; {it['note']})")
    if not apply:
        print('dry-run: 未执行;加 --apply 逐项确认后执行')
        return len(issues)

    # 1) 单作者归属错误：移动（迁移 models_meta 键——先记录再移动）
    meta_path = lib_paths.data_path('author-info', 'models_meta.json')
    meta = lib_paths.load_json(meta_path, {})
    key_map: dict[str, str] = {}
    for it in moves:
        old_key = f"{it['cur']}/{it['model_dir'].name}"
        new_key = f"{it['matched']}/{it['model_dir'].name}"
        if old_key in meta:
            key_map[old_key] = new_key
    moved = 0
    for i, it in enumerate(moves, 1):
        rel = it['model_dir'].relative_to(WORKSPACE_ROOT)
        ans = _ask(f"[{i}/{len(moves)}] 移动 {rel} 到 {it['matched']}？"
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

    # 2) 多作者模型：复制缺失副本到各作者编号目录（当前目录保留）
    copied = 0
    for i, it in enumerate(copies, 1):
        missing = it['missing']
        rel = it['model_dir'].relative_to(WORKSPACE_ROOT)
        ans = _ask(f"[复制{i}] 复制 {rel} 到作者 {', '.join(missing)}？"
                   f"（多作者模型，当前保留在 {it['cur']}） (y/n/q): ").lower()
        if ans in ('q', 'quit'):
            break
        if ans not in ('y', 'yes'):
            continue
        for aid in missing:
            dest = MODELS_DIR / aid / it['model_dir'].name
            try:
                shutil.copytree(str(it['model_dir']), str(dest))
                copied += 1
                print(f"  [复制] {rel} -> Models/{aid}/")
            except FileExistsError:
                print(f"  [跳过] 目标已存在: Models/{aid}/{it['model_dir'].name}")
    print(f'重新分类完成: 移动 {moved} 个，复制 {copied} 个')
    return moved + copied


# ---------------------------------------------------------------------------
# 合并重复作者（--merge-authors）
# ---------------------------------------------------------------------------
def normalize_platform_val(key: str, val: str) -> str:
    """平台值归一化（URL 去协议/尾部斜杠，便于对比）。"""
    v = val.strip().lower()
    v = re.sub(r'^https?://', '', v)
    return v.rstrip('/')


def _name_substr_related(norm_a: str, norm_b: str) -> bool:
    """两个已规范化作者名是否构成子串关系（较短者是较长者的子串）。

    门槛：较短者含中文 >=3 字、纯英文 >=4 字符——"奶油桃"⊂"奶油桃NaytoTime"
    可识别，而"饭"（1 字）、"水神"（2 字）这类短名不触发，避免大量误报。
    """
    if not norm_a or not norm_b or norm_a == norm_b:
        return False
    short, long_ = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)
    if len(short) < 3:
        return False
    if not re.search(r'[\u4e00-\u9fff]', short) and len(short) < 4:
        return False
    return short in long_


def find_merge_candidates() -> list[tuple[str, str, str]]:
    """找重复作者候选 (a, b, 原因)。依据：平台账号相同、规范化名字相等、名字子串。"""
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

    # 名字子串（较短名是较长名的子串，如 奶油桃 ⊂ 奶油桃NaytoTime）
    name_items: list[tuple[str, str]] = []
    for aid, entry in authors.items():
        for name in entry.get('name') or []:
            norm = lib_readme.normalize_alias(name)
            if norm:
                name_items.append((aid, norm))
    for i in range(len(name_items)):
        aid_i, norm_i = name_items[i]
        for j in range(i + 1, len(name_items)):
            aid_j, norm_j = name_items[j]
            if aid_i == aid_j:
                continue
            if _name_substr_related(norm_i, norm_j):
                short = norm_i if len(norm_i) <= len(norm_j) else norm_j
                add_pair(aid_i, aid_j, f"名字子串: {short}")

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
    meta_path = lib_paths.data_path('author-info', 'models_meta.json')
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
    print(f'合并作者: 发现 {len(candidates)} 个候选对（平台相同 / 名字相同 / 名字子串）:')
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
    for script, args, label in [('models_organize/04_generate&update_root_readme.py', ['--data'], '作者数据 authors.json'),
                                ('models_organize/04_generate&update_root_readme.py', ['--readme'], '根 README 作者表')]:
        p = WORKSPACE_ROOT / '.github' / 'scripts' / script
        if not p.is_file():
            print(f'  [警告] 未找到 {p}，跳过{label}重建')
            continue
        print(f'  重建{label}...')
        subprocess.run([sys.executable, str(p), *args], cwd=WORKSPACE_ROOT, check=False)


def _author_display(author_id: str) -> str:
    """作者编号 -> '首名 (编号)'。"""
    authors = lib_readme.load_authors_index().get('authors') or {}
    entry = authors.get(author_id) or {}
    names = entry.get('name') or []
    return f"{names[0] if names else '?'} ({author_id})"


# 宽松版平台行（复用 lib/readme.py 的 PLATFORM_ANY_LINE_RE：2-4 空格、冒号可选）
PLATFORM_LINE_RE = lib_readme.PLATFORM_ANY_LINE_RE


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
    """安全交互输入（复用 lib/console.py 统一实现，与 lib/kb 一致）。"""
    return lib_console.ask(prompt)


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
# 缺失报告：无分类 / 无预览图（可分开查看）
# ---------------------------------------------------------------------------
def iter_all_model_dirs() -> list[Path]:
    """所有模型目录：Models/<作者>/<模型>（两层）+ Blockbench-Models / Other-YSM-Models（一层）。"""
    dirs: list[Path] = []
    if MODELS_DIR.is_dir():
        for author in iter_author_dirs():
            dirs.extend(iter_model_dirs(author))
    for root in (WORKSPACE_ROOT / 'Blockbench-Models', WORKSPACE_ROOT / 'Other-YSM-Models'):
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and not d.name.startswith('.') and d.name.lower() != 'previews':
                    dirs.append(d)
    return dirs


def scan_missing() -> tuple[list[Path], list[Path], int]:
    """一次扫描所有模型目录：返回 (无分类列表, 无预览图列表, 总数)。

    作品集合直接取自 character/*.json 的顶层键（单一数据源，不再依赖
    category_map.json；合并后不再有独立的 works.json）。
    """
    cat_keys: set[str] = set()
    rdir = lib_paths.data_path('model-info', 'character')
    if rdir.is_dir():
        for f in rdir.glob('*.json'):
            content = lib_paths.load_json(f, {})
            # 新格式：作品键由 work.name 决定（读取不依赖文件名）
            work = content.get('work') if isinstance(content, dict) else None
            if isinstance(work, dict) and work.get('name'):
                cat_keys.add(str(work['name']).lower())
    no_cat: list[Path] = []
    no_preview: list[Path] = []
    total = 0
    for model_dir in iter_all_model_dirs():
        total += 1
        prefix = model_dir.name.split('_')[0].strip().lower()
        if prefix and prefix not in cat_keys:
            no_cat.append(model_dir)
        if not lib_previews.collect_preview_images(model_dir):
            no_preview.append(model_dir)
    return no_cat, no_preview, total


def report_no_category() -> int:
    """报告无分类（作品前缀不在 character/*.json）的模型，显示路径。返回数。"""
    no_cat, _, total = scan_missing()
    print(f'无分类报告（共 {total} 个模型目录）:')
    print(f'  无分类模型 {len(no_cat)} 个（作品前缀不在 character/*.json）:')
    for d in no_cat:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    return len(no_cat)


def report_unknown() -> int:
    """报告文件夹名含 'Unknown' 的模型（未确定作品归属），显示路径。返回数。"""
    unknown: list[Path] = []
    for model_dir in iter_all_model_dirs():
        if 'unknown' in model_dir.name.lower():
            unknown.append(model_dir)
    print(f'Unknown 报告（文件夹名含 Unknown 共 {len(unknown)} 个）:')
    for d in unknown:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    return len(unknown)


def report_no_preview() -> int:
    """报告无预览图的模型，显示路径。返回数。"""
    _, no_preview, total = scan_missing()
    print(f'无预览图报告（共 {total} 个模型目录）:')
    print(f'  无预览图模型 {len(no_preview)} 个:')
    for d in no_preview:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    return len(no_preview)


def report_missing() -> int:
    """汇总报告：无分类 + 无预览图 + 完整模型。"""
    no_cat, no_preview, total = scan_missing()
    no_cat_set = set(no_cat)
    no_preview_set = set(no_preview)
    ok = total - len(no_cat_set | no_preview_set)
    print(f'缺失报告（共 {total} 个模型目录）:')
    print(f'  无分类模型 {len(no_cat)} 个（作品前缀不在 character/*.json）:')
    for d in no_cat:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    print(f'  无预览图模型 {len(no_preview)} 个:')
    for d in no_preview:
        print(f'    {d.relative_to(WORKSPACE_ROOT)}')
    print(f'  既有分类又有预览图: {ok} 个')
    return len(no_cat) + len(no_preview)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reclassify', action='store_true', help='重新分类（扫 Models 校验作者归属）')
    parser.add_argument('--dedupe', action='store_true',
                        help='检测并删除作者目录下内容重复的模型（sha256 相同；--apply 执行删除）')
    parser.add_argument('--merge-authors', action='store_true', help='合并重复作者（逐对确认）')
    parser.add_argument('--report-empty', action='store_true', help='空壳报告（无 .ysm 的文件夹）')
    parser.add_argument('--report-missing', action='store_true',
                        help='缺失汇总（无分类 + 无预览图 + 完整，显示路径）')
    parser.add_argument('--report-no-category', action='store_true',
                        help='无分类报告（作品前缀不在 character/*.json，显示路径）')
    parser.add_argument('--report-no-preview', action='store_true',
                        help='无预览图报告（显示路径）')
    parser.add_argument('--report-unknown', action='store_true',
                        help='文件夹名含 Unknown 的模型（待确认归属，显示路径）')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认 dry-run 只报告）')
    args = parser.parse_args()

    if not MODELS_DIR.is_dir():
        print(f'错误: {MODELS_DIR} 目录不存在。')
        return 2

    if args.dedupe:
        return cmd_dedupe(args.apply)
    if args.reclassify:
        return reclassify(args.apply)
    if args.merge_authors:
        return merge_authors_flow(args.apply)
    if args.report_empty:
        return report_empty()
    if args.report_no_category:
        return report_no_category()
    if args.report_no_preview:
        return report_no_preview()
    if args.report_unknown:
        return report_unknown()
    if args.report_missing:
        return report_missing()

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
