#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型归档工具（重构版）——按作者/作品将待归档的 .ysm 归位到仓库。

流程（6 层）：
  ① 数据层   收集输入 / 加载作者索引、角色库、作品键表
  ② 解析层   解析 .ysm → 模型元数据 + 作者块；登记/合并作者 → authors.json
  ③ 决策层   命名（先合并 → resolve_name3 格式化）/ 归类 / 去重 / 版本化 / 合并 / sidecar
  ④ 执行层   移动 / 复制 / 创建目录
  ⑤ 联动层   --with-* 调下游
  ⑥ 入口层   main 编排

规则：
  - 有作者 → 登记/合并 authors.json（新作者从 0000 起取空缺编号 + 升序 + 建目录；
    旧作者补缺合并：别名去重追加末尾 / 平台补缺失 http 键），主作者 move、其他模型作者 copy
  - 无作者 → 按作品归类到 Other-YSM-Models/<作品>/（未匹配 → Unknown）
  - 命名：resolve_folder_name —— 优先用文件内 <name>（无则文件名）作匹配主体，resolve_name3 匹配出
    作品则标准化（作品/角色，其余字段原位）；匹配不出则兜底用内部 <name> 命名（去装饰符号）。
    （产出 <作品>_<中文角色>[_皮肤]_<英文角色>[_皮肤]_<评级>）
  - 去重：sha256 内容相同跳过；同名文件夹按文件大小版本化；同模型多版本合并；附属文件跟随
  - 不写 co_creators.json（co-creator 作者丢弃）

用法:
  python .github/scripts/models_organize/01_organize_models.py <文件或目录>... [选项]

选项:
  --apply                真正执行（默认 dry-run）
  --root PATH            指定仓库根目录（默认自动检测 cwd/脚本位置）
  --with-gen-readmes     归档成功后生成模型 README
  --with-readme-table    归档成功后更新根 README 作者索引
  --verbose              打印匹配细节
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import models as lib_models
from lib import paths as lib_paths
from lib import readme as lib_readme
from lib import ysm as lib_ysm
from lib.author_readme import format_author_name
from lib.kb.cmds import build_indexes
from lib.kb.parse2 import resolve_name3, build_cn_alias
from lib.kb.storage import load_kb_json
from lib.kb.sync import build_work_index

# ---- lib 绑定 ----
extract_metadata = lib_ysm.extract_metadata
classify_authors = lib_ysm.classify_authors
normalize_alias = lib_readme.normalize_alias
build_author_index = lib_readme.build_author_index
find_author = lib_readme.find_author
match_author_id = lib_readme.match_author_id
find_workspace_root = lib_paths.find_workspace_root
has_cjk = lib_models.has_cjk
normalize_name_for_cmp = lib_models.normalize_name_for_cmp
clean_file_stem = lib_models.clean_file_stem
same_model = lib_models.same_model
detect_work_prefix = lib_models.detect_work_prefix

# Windows 文件名非法字符与尾点/尾空格
ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TRAILING_DOT_SPACE_RE = re.compile(r'[.\s]+$')
WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL',
                    *(f'COM{i}' for i in range(1, 10)),
                    *(f'LPT{i}' for i in range(1, 10))}
# 附属文件扩展名（跟随移动/复制）
SIDECAR_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif',
                '.zip', '.7z', '.rar', '.txt', '.json'}


# ===========================================================================
# ① 数据层
# ===========================================================================
def _work_map(root: Path) -> dict[str, str]:
    """加载作品键表：{作品键大写: 规范写法}（来自 character/*.json 文件名）。"""
    char_dir = lib_paths.CHARACTER_DIR
    if root and root != lib_paths.WORKSPACE_ROOT:
        char_dir = root / '.github' / 'data' / 'model-info' / 'character'
    if not char_dir.is_dir():
        return {}
    return {f.stem.upper(): f.stem for f in char_dir.glob('*.json')}


def load_role_kb(root: Path):
    """加载角色知识库索引（resolve_name3 命名格式化用）。

    返回 (roles, en_to_cn, cn_to_en, cn_alias)；与 02_rename_model_folders.py 一致。
    """
    kb_path = lib_paths.MODEL_INFO_DIR
    if root and root != lib_paths.WORKSPACE_ROOT:
        kb_path = root / '.github' / 'data' / 'model-info'
    data = load_kb_json(kb_path)
    build_work_index(data)
    roles = list(data.get('roles') or [])
    _cn_idx, _en_idx, en_to_cn, cn_to_en = build_indexes(roles)
    cn_alias = build_cn_alias(roles)
    return roles, en_to_cn, cn_to_en, cn_alias


def collect_ysm_files(inputs: list[Path]) -> list[Path]:
    """收集输入的 .ysm 文件（目录递归 *.ysm/*.YSM，按规范化路径去重）。"""
    files: list[Path] = []
    for inp in inputs:
        if inp.is_file() and inp.suffix.lower() == '.ysm':
            files.append(inp)
        elif inp.is_dir():
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


# ===========================================================================
# ② 解析层（含作者登记/合并 → authors.json）
# ===========================================================================
def next_free_author_id(models_dir: Path) -> str:
    """返回 Models 下第一个空缺的 4 位编号（从 0000 起，补齐历史空洞）。"""
    existing = {int(d.name) for d in models_dir.iterdir()
                if d.is_dir() and re.fullmatch(r'\d{4}', d.name)}
    i = 0
    while i in existing:
        i += 1
    return f'{i:04d}'


def merge_author_entry(entry: dict, block: dict) -> bool:
    """补缺合并：别名归一化去重追加末尾；平台只补缺失的 http 键。返回是否有变化。"""
    changed = False
    known = {normalize_alias(n) for n in entry.get('name', [])}
    for alias in format_author_name(block.get('name') or '').split('|'):
        alias = alias.strip()
        if alias and normalize_alias(alias) not in known:
            entry.setdefault('name', []).append(alias)
            known.add(normalize_alias(alias))
            changed = True
    platforms = entry.setdefault('platforms', {})
    for key, value in (block.get('contacts') or {}).items():
        if key not in platforms and isinstance(value, str) and value.startswith('http'):
            platforms[key] = value
            changed = True
    return changed


def register_or_merge_author(root: Path, models_dir: Path, author_id: str,
                             block: dict) -> bool:
    """把作者块登记或补缺合并进 authors.json；新作者建目录。返回是否有变化。

    - 已存在：补缺合并（merge_author_entry），有变化才写盘（幂等）
    - 新作者：写入完整条目 + 整体按键升序重排 + 创建 Models/<编号>/
    """
    path = lib_paths.data_path('author-info', 'authors.json')
    data = lib_paths.load_json(path, {})
    authors = data.setdefault('authors', {})
    if author_id in authors:
        changed = merge_author_entry(authors[author_id], block)
    else:
        names = [t.strip() for t in format_author_name(block.get('name') or '').split('|')
                 if t.strip()]
        authors[author_id] = {
            'name': names,
            'readme': f'Models/{author_id}/README.md',
            'platforms': dict(block.get('contacts') or {}),
        }
        (models_dir / author_id).mkdir(parents=True, exist_ok=True)
        changed = True
    if changed:
        authors = dict(sorted(authors.items(), key=lambda kv: int(kv[0])))
        data['authors'] = authors
        lib_paths.save_json(path, data)
    return changed


def resolve_and_register_author(block: dict, alias_to_id: dict, runtime_index: dict,
                                root: Path, models_dir: Path, apply: bool,
                                verbose: bool = False) -> tuple[str, bool]:
    """匹配/分配作者编号并登记 authors.json；返回 (author_id, is_new)。

    命中已有 → 旧作者（apply 时补缺合并）；未命中 → 新作者（补洞编号 + 登记 + 建目录）。
    """
    author_id, _ = match_author_id(block['name'], alias_to_id, runtime_index, verbose)
    if author_id:
        if apply:
            register_or_merge_author(root, models_dir, author_id, block)
        return author_id, False
    new_id = next_free_author_id(models_dir)
    key = normalize_alias(block['name'])
    if key:
        runtime_index.setdefault(key, new_id)
    if apply:
        register_or_merge_author(root, models_dir, new_id, block)
        print(f"  新建作者目录 {new_id}（{block['name']}）")
    else:
        print(f"  [计划] 新建作者 {new_id}（{block['name']}）")
    return new_id, True


# ===========================================================================
# ③ 决策层
# ===========================================================================
# 内部 <name> 的装饰符号（✟☪★☆ 等）在兜底命名时直接删除，只保留
# 中文/假名/英文/数字/常用分隔符——兜底直接用作者写的 name 作为文件夹名。
_DECOR_KEEP_RE = re.compile(r"[^\w\u4e00-\u9fff\u3040-\u30ff\-_·.\s()（）]")


def _clean_inner_name(name: str) -> str:
    """清理内部 name 的装饰符号，保留中文/假名/英文/数字/分隔符。"""
    return _DECOR_KEEP_RE.sub('', name).strip()


def resolve_folder_name(inner_name: str | None, file_stem: str, kb) -> tuple[str, str]:
    """按命名规则决定文件夹名与作品（2026-08-19，替代 build_model_folder_name + format_folder_name）。

    规则：
      1. 匹配主体优先用文件内 <name>（作者自写更可靠），无 name 才用文件名；两者都做
         符号→_、英文小写 格式化后进入 resolve_name3 匹配（resolve_name3 内部 format_name）。
      2. resolve_name3 匹配出作品（work 非 Unknown）→ 用其标准化结果：作品标准化 + 该作品下
         角色命中则角色也标准化、其余字段原位（有作品无角色则只作品标准化）。
      3. 未匹配出作品（无作品 / 角色多归属冲突 / 完全失败）→ 兜底：用内部 name 原样命名
         （仅清理装饰符号与 Windows 非法字符）；无内部 name 才用文件名。
    """
    a = (inner_name or '').strip()
    b = clean_file_stem(file_stem)
    if not a and not b:
        return 'unnamed_model', ''
    candidate = a if a else b  # 主候选：优先内部 name
    backup = b if (a and b and normalize_name_for_cmp(a) != normalize_name_for_cmp(b)) else ''

    def _match(name: str) -> tuple[str, str] | None:
        res = resolve_name3(name, *kb)
        work = res.get('work') or ''
        if work and work != 'Unknown':
            # 统一清理装饰符号（resolve_name3 的 format_name 不识别 ✟☪★☆ 等）
            return sanitize_folder_name(_clean_inner_name(res.get('new') or name)), work
        return None

    got = _match(candidate)
    if got:
        return got
    if backup:
        got = _match(backup)
        if got:
            return got
    # 兜底：内部 name 原样（去装饰符号 + 清理非法字符）；无 name 用文件名
    fallback = _clean_inner_name(a) if a else sanitize_folder_name(b or 'unnamed_model')
    return sanitize_folder_name(fallback or 'unnamed_model'), ''


def sanitize_folder_name(name: str) -> str:
    """清理 Windows 非法字符、保留名、尾点/尾空格。"""
    name = ILLEGAL_CHARS_RE.sub('_', name)
    name = TRAILING_DOT_SPACE_RE.sub('', name)
    name = name.strip()
    if not name:
        name = 'unnamed_model'
    if name.upper() in WINDOWS_RESERVED:
        name = '_' + name
    return name


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
                   input_sha: str, input_size: int = 0) -> tuple[str | None, str]:
    """在目标作者目录下查找重复。返回 (原因, 说明)；None 表示无重复。

    优先内容(sha256)匹配，其次规范化同名文件夹；先按文件大小预筛。
    """
    norm_folder = normalize_name_for_cmp(folder_name)
    if target_author_dir.is_dir():
        for sub in target_author_dir.iterdir():
            if sub.is_dir() and not sub.name.startswith('.'):
                if normalize_name_for_cmp(sub.name) == norm_folder:
                    if not any(f.suffix.lower() == '.ysm'
                               for f in sub.rglob('*') if f.is_file()):
                        continue  # 空壳同名文件夹：优先填充而非视为重复
                    return ('folder',
                            f"已存在同名模型文件夹 Models/{target_author_dir.name}/{sub.name}")
                for ysm in sub.rglob('*'):
                    if (ysm.is_file() and ysm.suffix.lower() == '.ysm'
                            and (input_size == 0 or ysm.stat().st_size == input_size)):
                        if file_sha256(ysm) == input_sha:
                            rel = ysm.relative_to(target_author_dir.parent)
                            return 'content', f"内容相同的文件已存在于 Models/{rel.as_posix()}"
    return None, ''


def versionize_same_name(folder_dir: Path, folder_name: str,
                         input_path: Path, input_size: int) -> list[tuple[Path, str]]:
    """同名文件夹内不同内容 -> 按文件大小统一版本化命名（大=新 vN，小=旧 v1）。"""
    if not folder_dir.is_dir():
        return []
    ysms = [p for p in folder_dir.glob('*')
            if p.is_file() and p.suffix.lower() == '.ysm']
    items: list[tuple[Path, int]] = [(input_path, input_size)]
    for p in ysms:
        try:
            items.append((p, p.stat().st_size))
        except OSError:
            return []
    if len(items) < 2:
        return []
    items.sort(key=lambda x: (x[1], x[0].as_posix()))
    return [(p, f"{folder_name}_v{i}.ysm") for i, (p, _) in enumerate(items, 1)]


def find_same_model_folder(target_dir: Path, folder_name: str, kb=None,
                           probes=()) -> Path | None:
    """在目标作者目录下找与 folder_name 属同一模型的已有文件夹（排除完全同名）。

    同模型判定优先用角色知识库：对新模型的可解析候选（内部 name / 文件名 / 兜底文件夹名）
    和已有文件夹各跑 resolve_name3，若"作品 + 中文角色"相同则视为同一模型（容忍别名，
    如 本子魔法使 ≡ 本子魔法师）。知识库判不出才回退字面子串 same_model。

    排除纯 Unknown 文件夹（Other-YSM 的兜底目录）：'Unknown' 是任意
    'Unknown_xxx' 的子串，会被 same_model 误判为同模型。
    """
    if not target_dir.is_dir():
        return None
    norm = normalize_name_for_cmp(folder_name)
    # 新模型可解析出的角色键集合（作品, 中文角色规范化）
    new_keys: set[tuple[str, str]] = set()
    for probe in probes:
        if not probe or not kb:
            continue
        res = resolve_name3(probe, *kb)
        work = res.get('work') or ''
        zh = (res.get('zh') or '').strip()
        if work and work != 'Unknown' and zh:
            new_keys.add((work, normalize_name_for_cmp(zh)))
    for sub in sorted(target_dir.iterdir()):
        if not (sub.is_dir() and not sub.name.startswith('.')):
            continue
        sub_norm = normalize_name_for_cmp(sub.name)
        if sub_norm == 'unknown':
            continue  # 纯 Unknown 兜底文件夹：不参与同模型合并
        if sub_norm == norm:
            continue
        # 角色知识库判定：作品+中文角色相同 → 同模型（多版本合并）
        if new_keys and kb:
            res_sub = resolve_name3(sub.name, *kb)
            work_sub = res_sub.get('work') or ''
            zh_sub = (res_sub.get('zh') or '').strip()
            if work_sub and work_sub != 'Unknown' and zh_sub:
                if (work_sub, normalize_name_for_cmp(zh_sub)) in new_keys:
                    return sub
        # 兜底：字面子串
        if same_model(folder_name, sub.name):
            return sub
    return None


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


# ===========================================================================
# ④ 执行层
# ===========================================================================
def archive_one(path: Path, target_dir: Path, folder_name: str, mode: str,
                apply: bool, root: Path, verbose: bool,
                kb=None, probes=()) -> str | None:
    """把单个 .ysm 归档到目标作者目录。返回 'moved'/'copied'/'skipped'；dry-run 返回 None。

    处理重复检测、同模型多版本合并、sidecar 跟随。mode='move'（主作者）或 'copy'。
    kb/probes：供 find_same_model_folder 用角色知识库判定同模型（多版本合并到已有文件夹）。
    """
    input_sha = file_sha256(path)
    input_size = path.stat().st_size if path.is_file() else 0
    dup_reason, dup_note = find_duplicate(target_dir, folder_name, input_sha, input_size)
    if dup_reason == 'content':
        print(f"  [跳过] {dup_note}")
        return 'skipped'
    version_plan: list[tuple[Path, str]] = []
    if dup_reason == 'folder':
        version_plan = versionize_same_name(target_dir / folder_name, folder_name,
                                            path, input_size)
        if not version_plan:
            print(f"  [跳过] {dup_note}")
            return 'skipped'

    dest_dir = find_same_model_folder(target_dir, folder_name, kb=kb, probes=probes)
    if dest_dir is not None:
        print(f"  合并进已有模型文件夹: {dest_dir.relative_to(root)}")
    else:
        dest_dir = target_dir / folder_name

    sidecars = collect_sidecars(path.parent, path.stem, path)
    verb = '复制' if mode == 'copy' else '移动'
    input_name = path.name
    if version_plan:
        input_name = next(n for s, n in version_plan if s == path)
        print("  同名不同内容 -> 按大小版本化（文件大=新版本 vN，小=旧版本 v1）:")
        for s, n in version_plan:
            if s != path:
                print(f"    [重命名] {s.name} -> {n}（{s.stat().st_size} 字节）")
        print(f"    {verb} -> {input_name}（{input_size} 字节）")
    if not apply:
        print(f"  [计划] {verb} -> {dest_dir.relative_to(root)}/{input_name}")
        if sidecars:
            print(f"  [计划] 跟随{verb}附属文件: {', '.join(s.name for s in sidecars)}")
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    for s, n in version_plan:
        if s != path:
            s.rename(dest_dir / n)
    dest = dest_dir / input_name
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


# ===========================================================================
# ⑤ 联动层
# ===========================================================================
def _run_script(root: Path, rel: str, args: list[str], label: str) -> None:
    script = root / '.github' / 'scripts' / rel
    if not script.is_file():
        print(f"  [警告] 未找到 {script}，跳过{label}")
        return
    print(f"  {label}...")
    subprocess.run([sys.executable, str(script), *args], cwd=root, check=False)


def run_generate_model_readmes(root: Path) -> None:
    """归档成功后生成模型 README。"""
    _run_script(root, 'models_organize/03_generate_model_readmes.py', [],
                '生成模型 README')


def update_root_readme(root: Path) -> None:
    """归档成功后更新根 README 作者索引。"""
    _run_script(root, 'models_organize/03_generate_root_readme.py', ['--author'],
                '更新根 README 作者索引')


# ===========================================================================
# ⑥ 入口层
# ===========================================================================
def process_file(path: Path, root: Path, alias_to_id: dict, runtime_index: dict,
                 kb, work_map: dict, apply: bool, verbose: bool) -> dict:
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    print(f"\n== {rel} ==")
    result = {'action': 'skipped', 'reason': '', 'new_author': False}

    meta = extract_metadata(path)
    if not meta:
        result['reason'] = '文件读取失败'
        return result
    inner_name = meta.get('name') or ''
    blocks = meta.get('author_blocks') or []
    models_dir = root / 'Models'

    if not blocks:
        # 无作者：命名 + 按作品归类
        folder_name, work = resolve_folder_name(inner_name, path.stem, kb)
        sub = work or detect_work_prefix(folder_name, work_map) or 'Unknown'
        target_dir = root / 'Other-YSM-Models' / sub
        print(f"  未识别到作者，按作品分类 -> Other-YSM-Models/{sub}")
        print(f"  模型文件夹名: {folder_name}")
        probes = (inner_name, path.stem, folder_name)
        status = archive_one(path, target_dir, folder_name, 'move', apply, root, verbose,
                             kb=kb, probes=probes)
        if status in ('moved', 'copied'):
            result['action'] = status
        elif status == 'skipped':
            result['reason'] = '重复或冲突'
        return result

    # 有作者：分类（co-creator 丢弃），逐个登记/合并 authors.json
    primary, model_blocks, _ = classify_authors(blocks)
    print(f"  作者列表: " + ', '.join(f"{b['name']}" for b in blocks))
    print(f"  主作者(分类): {primary['name']}；归档目标 {len(model_blocks)} 个")

    targets: list[tuple[str, str, dict]] = []
    for block in model_blocks:
        aid, is_new = resolve_and_register_author(block, alias_to_id, runtime_index,
                                                  root, models_dir, apply, verbose)
        mode = 'move' if block is primary else 'copy'
        targets.append((aid, mode, block))
        if is_new:
            result['new_author'] = True
    # 同编号去重：move 优先
    dedup: dict[str, tuple[str, dict]] = {}
    for aid, mode, block in targets:
        if aid not in dedup or (mode == 'move' and dedup[aid][0] != 'move'):
            dedup[aid] = (mode, block)

    folder_name, _ = resolve_folder_name(inner_name, path.stem, kb)
    print(f"  模型文件夹名: {folder_name}")

    probes = (inner_name, path.stem, folder_name)
    statuses = []
    # 先复制目标后移动主作者，保证 copy 时源文件（含 sidecar）仍存在
    for aid, (mode, block) in dedup.items():
        if mode == 'copy':
            statuses.append(archive_one(path, models_dir / aid, folder_name,
                                        'copy', apply, root, verbose,
                                        kb=kb, probes=probes))
    for aid, (mode, block) in dedup.items():
        if mode == 'move':
            statuses.append(archive_one(path, models_dir / aid, folder_name,
                                        'move', apply, root, verbose,
                                        kb=kb, probes=probes))

    if any(s in ('moved', 'copied') for s in statuses):
        result['action'] = 'moved' if 'moved' in statuses else 'copied'
    elif any(s == 'skipped' for s in statuses):
        result['reason'] = '重复或冲突'
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('inputs', nargs='+', help='.ysm 文件或目录（目录递归收集 *.ysm）')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认 dry-run）')
    parser.add_argument('--root', metavar='PATH', default=None, help='仓库根目录（默认自动检测）')
    parser.add_argument('--with-gen-readmes', action='store_true',
                        help='归档成功后生成模型 README')
    parser.add_argument('--with-readme-table', action='store_true',
                        help='归档成功后更新根 README 作者索引')
    parser.add_argument('--verbose', action='store_true', help='打印匹配细节')
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else find_workspace_root()
    models_dir = root / 'Models'
    if not models_dir.is_dir():
        print(f"错误: {models_dir} 目录不存在（可用 --root 指定仓库根目录）")
        return 2

    alias_to_id, id_to_name = build_author_index(models_dir, root / 'README.md')
    print(f"作者索引: {len(alias_to_id)} 个别名 / {len(id_to_name)} 位作者")
    kb = load_role_kb(root)
    work_map = _work_map(root)
    print(f"角色库: {len(kb[0])} 条  作品键表: {len(work_map)} 个")

    files = collect_ysm_files([Path(x) for x in args.inputs])
    if not files:
        print("没有可处理的 .ysm 文件。")
        return 1

    mode = "执行" if args.apply else "预览（dry-run，加 --apply 执行）"
    print(f"模式: {mode} | 共 {len(files)} 个文件")

    moved = new_authors = skipped = 0
    moved_any = False
    runtime_index: dict[str, str] = {}
    for f in files:
        res = process_file(f, root, alias_to_id, runtime_index, kb, work_map,
                           args.apply, args.verbose)
        if res['action'] in ('moved', 'copied'):
            moved += 1
            moved_any = True
        elif res['reason']:
            skipped += 1
        if res['new_author']:
            new_authors += 1

    if args.apply and moved_any:
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
