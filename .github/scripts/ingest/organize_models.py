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
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import models as lib_models
from lib import paths as lib_paths
from lib import readme as lib_readme

# 新作者 README 的默认 Role（与 format_author_readme.py 保持一致）
TARGET_ROLE = "#模型 #动作 #动画 | #Model #Motion #Animation"

# 作者 README 解析相关（复用 lib/readme.py 统一实现）
NAME_LINE_RE = lib_readme.NAME_LINE_RE
AUTHOR_SECTION_RE = lib_readme.AUTHOR_SECTION_RE
INDEX_ROW_RE = lib_readme.INDEX_ROW_RE
normalize_alias = lib_readme.normalize_alias
parse_author_name_value = lib_readme.parse_author_name_value
build_author_index = lib_readme.build_author_index

# 命名/评级/去重（复用 lib/models.py 统一实现）
GRADE_SUFFIX_RE = lib_models.GRADE_SUFFIX_RE
VERSION_SUFFIX_RE = lib_models.VERSION_SUFFIX_RE
has_cjk = lib_models.has_cjk
normalize_name_for_cmp = lib_models.normalize_name_for_cmp
clean_file_stem = lib_models.clean_file_stem
same_model = lib_models.same_model

# JSON/文本读写与路径（复用 lib/paths.py 统一实现）
load_json = lib_paths.load_json
read_text_utf8 = lib_paths.read_text_utf8
find_workspace_root = lib_paths.find_workspace_root

# 从 .ysm 提取元数据：兼容多版本
#   旧版(Property): <name> xxx / <authors> xxx（单行标签，值到行尾）
#   新版(Metadata 2.5+): <author> 块结构，作者名在缩进的 <name> 子标签里，可有多个作者块
#   早期无头版: JSON 键 "name"/"authors"
TOP_NAME_RE = re.compile(r'(?m)^<name>\s*([^\r\n<]+?)\s*$')            # 顶层模型名（行首无缩进）
AUTHORS_LINE_RE = re.compile(r'(?m)^<authors>\s*([^\r\n<]+?)\s*$')     # 旧版单行 authors
AUTHOR_BLOCK_RE = re.compile(r'<author>(.*?)(?=<author>|$)', re.DOTALL)  # 新版作者块
BLOCK_NAME_RE = re.compile(r'(?m)^\s*<name>\s*([^\r\n<]+?)\s*$')       # 块内缩进 <name>
BLOCK_ROLE_RE = re.compile(r'(?m)^\s*<role>\s*([^\r\n<]+?)\s*$')       # 块内缩进 <role>
BLOCK_CONTACT_RE = re.compile(r'(?m)^\s*<contact-\s*([^>]+?)\s*>\s*([^\r\n<]+?)\s*$')  # 块内 <contact-X> 平台
JSON_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]*)"')
JSON_AUTHORS_RE = re.compile(r'"(?:authors|author)"\s*:\s*"([^"]*)"')
EXPORT_SECTION_RE = re.compile(r'\[ ?Export ?\]')


# 作者字符串的分隔符（全/半角）
AUTHOR_SPLIT_RE = re.compile(r'[\s|｜,，、;/；]+')
# 拆"中文(English)"形式
PAREN_PAIR_RE = re.compile(r'^([^()（）]*)[(（]([^)）]*)[)）]$')

# Windows 文件名非法字符与尾点/尾空格
ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TRAILING_DOT_SPACE_RE = re.compile(r'[.\s]+$')

WINDOWS_RESERVED = {
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
}


# ---------------------------------------------------------------------------
# .ysm 元数据提取（兼容多版本：YSGP 文本头 / 早期 JSON 明文）
# ---------------------------------------------------------------------------
def extract_metadata(path: Path) -> dict:
    """返回 {'name', 'authors', 'author_blocks'}；读取失败返回空 dict 并打印警告。

    author_blocks: [{'name', 'role', 'contacts': {平台键: 值}}, ...]（新版块结构，
    按出现顺序；旧版单行 authors 退化为单个块）。只解析 [Export] 段之前，避免
    加密二进制区出现巧合标签字节。
    """
    try:
        raw = path.read_bytes()
    except OSError as e:
        print(f"  [错误] 无法读取: {e}")
        return {}

    text = raw.decode('utf-8', errors='ignore')
    export_m = EXPORT_SECTION_RE.search(text)
    head = text[:export_m.start()] if export_m else text

    fields: dict[str, str] = {}

    m = TOP_NAME_RE.search(head)
    if m:
        fields['name'] = m.group(1).strip()

    author_blocks: list[dict] = []
    m = AUTHORS_LINE_RE.search(head)
    if m:
        # 旧版单行 authors：退化为单个块（无 role/contacts）
        fields['authors'] = m.group(1).strip()
        author_blocks.append({'name': fields['authors'], 'role': '', 'contacts': {}})
    else:
        # 新版块结构：每个 <author> 块内缩进的 <name>/<role>/<contact-X>
        for block in AUTHOR_BLOCK_RE.findall(head):
            m_name = BLOCK_NAME_RE.search(block)
            if not m_name:
                continue
            name = m_name.group(1).strip()
            m_role = BLOCK_ROLE_RE.search(block)
            role = m_role.group(1).strip() if m_role else ''
            contacts: dict[str, str] = {}
            for m_c in BLOCK_CONTACT_RE.finditer(block):
                key = m_c.group(1).strip()
                val = m_c.group(2).strip()
                if key and val:
                    contacts.setdefault(key, val)
            author_blocks.append({'name': name, 'role': role, 'contacts': contacts})
        if author_blocks:
            fields['authors'] = ' | '.join(b['name'] for b in author_blocks)

    # 早期无头版本（JSON 明文）
    if 'name' not in fields:
        m = JSON_NAME_RE.search(head)
        if m:
            fields['name'] = m.group(1)
    if 'authors' not in fields:
        m = JSON_AUTHORS_RE.search(head)
        if m:
            fields['authors'] = m.group(1)
            author_blocks.append({'name': fields['authors'], 'role': '', 'contacts': {}})

    meta = {'name': fields.get('name'), 'authors': fields.get('authors'),
            'author_blocks': author_blocks}
    if not meta['name'] and not meta['authors']:
        print(f"  [警告] 未能从文件中提取到 <name>/<authors> 元数据（可能是无头旧版或损坏文件）")
    return meta


# ---------------------------------------------------------------------------
# 作者匹配
# ---------------------------------------------------------------------------
def split_authors(authors_str: str) -> list[str]:
    """把 authors 原始串拆成候选别名。'鸡姬(raw_chicken)' -> ['鸡姬', 'raw_chicken']；
    'A | B' -> ['A', 'B']。"""
    candidates: list[str] = []
    for seg in AUTHOR_SPLIT_RE.split(authors_str):
        seg = seg.strip()
        if not seg:
            continue
        m = PAREN_PAIR_RE.match(seg)
        if m:
            outer, inner = m.group(1).strip(), m.group(2).strip()
            if outer and inner:
                candidates.extend([outer, inner])
            else:
                candidates.append(outer or inner)
        else:
            candidates.append(seg)
    return candidates


def _can_substr_match(key: str) -> bool:
    """子串匹配门槛：>=4 字符，或含中文且 >=2 字符（中文作者名常见 2-3 字）。"""
    if len(key) >= 4:
        return True
    return len(key) >= 2 and re.search(r'[\u4e00-\u9fff]', key) is not None


def find_author(authors_str: str, alias_to_id: dict[str, str],
                verbose: bool = False) -> tuple[str | None, str]:
    """返回 (作者编号 或 None, 说明)。

    按候选顺序逐个匹配（主作者在前）：先看完全匹配，再看子串匹配；
    第一个有匹配的候选即返回，避免多作者时被次要作者"抢走"归属。
    """
    candidates = split_authors(authors_str)
    if verbose:
        print(f"  候选别名: {candidates}")

    for cand in candidates:
        key = normalize_alias(cand)
        if not key:
            continue
        if key in alias_to_id:
            return alias_to_id[key], f"完全匹配: {cand}"
        if _can_substr_match(key):
            best: tuple[int, str, str] | None = None  # (匹配别名长度, 编号, 别名)
            for alias, author_id in alias_to_id.items():
                if not _can_substr_match(alias):
                    continue
                if key in alias or alias in key:
                    if best is None or len(alias) > best[0]:
                        best = (len(alias), author_id, alias)
            if best:
                return best[1], f"子串匹配: {best[2]}"

    return None, "未命中任何已收录作者"


# ---------------------------------------------------------------------------
# 多作者分类：主作者 = 第一个 role 含"模型"的作者；无则第一个作者
# ---------------------------------------------------------------------------
def classify_authors(author_blocks: list[dict]) -> tuple[dict | None, list[dict], list[dict]]:
    """返回 (primary, model_blocks, co_creator_blocks)。

    primary: 第一个 role 含"模型"的块；没有任何块含"模型"时取第一个块。
    model_blocks: 所有 role 含"模型"的块（含 primary，可能多个 -> 复制到各作者目录）。
    co_creator_blocks: 其余块（非"模型"角色，仅记录不归档）。
    """
    if not author_blocks:
        return None, [], []
    primary: dict | None = None
    model_blocks: list[dict] = []
    for b in author_blocks:
        if '模型' in (b.get('role') or ''):
            if primary is None:
                primary = b
            model_blocks.append(b)
    if primary is None:
        primary = author_blocks[0]
        model_blocks = [primary]
    co_creators = [b for b in author_blocks if b not in model_blocks]
    return primary, model_blocks, co_creators


# ---------------------------------------------------------------------------
# 平台信息与 models_meta 数据（外置于 .github/data/meta/）
# ---------------------------------------------------------------------------
def _meta_path(root: Path, fname: str) -> Path:
    """数据路径：优先跟随调用方 root（临时仓库/测试），否则用 lib 语义路径。"""
    if root and root != lib_paths.WORKSPACE_ROOT:
        return root / '.github' / 'data' / 'meta' / fname
    return lib_paths.data_path('meta', fname)


def load_platform_map(root: Path) -> dict[str, str]:
    """平台键(小写) -> README 字段 的映射，数据文件可手工修改。"""
    data = lib_paths.load_json(_meta_path(root, 'platform_map.json'), {})
    return {str(k).lower(): str(v) for k, v in data.items()}


def map_platforms(contacts: dict[str, str], platform_map: dict[str, str]) -> dict[str, list[str]]:
    """把 ysm 的 <contact-X> 映射为 README 模板字段（SocialPlatform/SupportPlatform/
    OtherPlatform/GroupChat -> [值列表]）；未映射的平台归入 OtherPlatform。"""
    mapped: dict[str, list[str]] = {}
    for key, val in contacts.items():
        field = platform_map.get(key.strip().lower())
        if not field:
            field = 'OtherPlatform'
        mapped.setdefault(field, [])
        line = f'{key.strip()}: {val}' if key.strip() else val
        if line not in mapped[field]:
            mapped[field].append(line)
    return mapped


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
# 新作者 README 生成（模仿现有作者 README 风格）
# ---------------------------------------------------------------------------
def format_author_name(authors_str: str) -> str:
    """'鸡姬(raw_chicken)' -> '#鸡姬 | #raw_chicken'（保留原始顺序，每个别名加 #）"""
    tags: list[str] = []
    for cand in split_authors(authors_str):
        tag = cand.strip()
        if tag and not tag.startswith('#') and not tag.startswith('＃'):
            tag = '#' + tag
        if tag and tag not in tags:
            tags.append(tag)
    return ' | '.join(tags)


def render_author_readme(author_id: str, authors_str: str) -> str:
    name_line = format_author_name(authors_str) or '暂无'
    return (
        f'# {author_id}\n'
        '\n'
        '## Author\n'
        '\n'
        f'- **Name**: {name_line}\n'
        f'  - **Role**: {TARGET_ROLE}\n'
    )


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
