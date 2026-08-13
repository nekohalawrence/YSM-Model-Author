# -*- coding: utf-8 -*-
""".ysm 元数据解析、作者分类与平台映射；organize_models（归档）与
generate_model_readmes（模型 README 的 co-creator 识别）共用。

导出：
  extract_metadata(path)    从 .ysm 文本头提取 {name, authors, author_blocks}
  classify_authors(blocks)  作者块分类 -> (primary, model_blocks, co_creators)
  load_platform_map(root)   读平台映射数据文件（支持 --root 跟随）
  map_platforms(contacts)   作者块 contacts -> README 模板字段分组
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as lib_paths  # noqa: E402

# ---------------------------------------------------------------------------
# .ysm 元数据提取正则：兼容多版本
#   旧版(Property): <name> xxx / <authors> xxx（单行标签，值到行尾）
#   新版(Metadata 2.5+): <author> 块结构，作者名在缩进的 <name> 子标签里，可有多个作者块
#   早期无头版: JSON 键 "name"/"authors"
# ---------------------------------------------------------------------------
TOP_NAME_RE = re.compile(r'(?m)^<name>\s*([^\r\n<]+?)\s*$')            # 顶层模型名（行首无缩进）
AUTHORS_LINE_RE = re.compile(r'(?m)^<authors>\s*([^\r\n<]+?)\s*$')     # 旧版单行 authors
AUTHOR_BLOCK_RE = re.compile(r'<author>(.*?)(?=<author>|$)', re.DOTALL)  # 新版作者块
BLOCK_NAME_RE = re.compile(r'(?m)^\s*<name>\s*([^\r\n<]+?)\s*$')       # 块内缩进 <name>
BLOCK_ROLE_RE = re.compile(r'(?m)^\s*<role>\s*([^\r\n<]+?)\s*$')       # 块内缩进 <role>
BLOCK_CONTACT_RE = re.compile(r'(?m)^\s*<contact-\s*([^>]+?)\s*>\s*([^\r\n<]+?)\s*$')  # 块内 <contact-X> 平台
JSON_NAME_RE = re.compile(r'"name"\s*:\s*"([^"]*)"')
JSON_AUTHORS_RE = re.compile(r'"(?:authors|author)"\s*:\s*"([^"]*)"')
EXPORT_SECTION_RE = re.compile(r'\[ ?Export ?\]')


def _meta_path(root: Path | None, fname: str) -> Path:
    """数据路径：优先跟随调用方 root（临时仓库/测试），否则用 lib 语义路径。"""
    if root and root != lib_paths.WORKSPACE_ROOT:
        return root / '.github' / 'data' / 'meta' / fname
    return lib_paths.data_path('meta', fname)


def extract_metadata(path: Path, quiet: bool = False) -> dict:
    """返回 {'name', 'authors', 'author_blocks'}；读取失败返回空 dict 并打印警告。

    author_blocks: [{'name', 'role', 'contacts': {平台键: 值}}, ...]（新版块结构，
    按出现顺序；旧版单行 authors 退化为单个块）。只解析 [Export] 段之前，避免
    加密二进制区出现巧合标签字节。quiet=True 时不打印警告（批量扫描场景，如
    模型 README 的 co-creator 兑底识别，避免无头旧版文件刷屏）。
    """
    try:
        raw = path.read_bytes()
    except OSError as e:
        if not quiet:
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
        if not quiet:
            print(f"  [警告] 未能从文件中提取到 <name>/<authors> 元数据（可能是无头旧版或损坏文件）")
    return meta


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
# 平台信息：contacts -> README 模板字段（SocialPlatform/SupportPlatform/...）
# ---------------------------------------------------------------------------
def load_platform_map(root: Path | None = None) -> dict[str, str]:
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
