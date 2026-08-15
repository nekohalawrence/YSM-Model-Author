#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根 README 展示生成工具：集中作者数据（authors.json）+ 根 README 作者表 + 作品分类区块。

由原 build_authors_index.py（数据生产者）、build_readme_authors.py（根表渲染）合并，
并收纳 02 的 --build-category-map（作品分类区块）：作者/作品的集中数据与根 README
展示区块统一在此，供 cli / pipeline / organize / audit 调用。

用法：
  python 04_generate&update_root_readme.py                 # --data + --readme 全做
  python 04_generate&update_root_readme.py --data          # 只生成 authors.json
  python 04_generate&update_root_readme.py --readme        # 只更新根 README / README-EN 作者表
  python 04_generate&update_root_readme.py --build-category-map  # 更新根 README 模型分类区块（从 character/*.json 现算）
  python 04_generate&update_root_readme.py --data --check  # 只检查 authors.json 差异（不写盘）
"""
import argparse
import re
import sys
from pathlib import Path

# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as lib_paths  # noqa: E402
from lib import readme as lib_readme  # noqa: E402
from lib.kb.category import (  # noqa: E402
    build_category_map, update_readme_works_section,
)
from lib.kb.storage import load_kb_json  # noqa: E402

WORKSPACE_ROOT = lib_paths.WORKSPACE_ROOT
MODELS_DIR = WORKSPACE_ROOT / 'Models'
DATA_TARGET = lib_paths.data_path('author-info', 'authors.json')
FOLDER_RE = re.compile(r'^(\d{4})$')


# ---------------------------------------------------------------------------
# --data：生成集中作者数据 authors.json（原 build_authors_index.py）
# ---------------------------------------------------------------------------
def build_authors_data() -> dict:
    """扫描 Models 与根 README，构建集中作者数据。"""
    return lib_readme.build_authors_data(MODELS_DIR, WORKSPACE_ROOT / 'README.md')


def write_authors_data(check_only: bool = False) -> int:
    """生成/检查 authors.json；check 只比较作者本体（generated 时间戳每次变）。"""
    data = build_authors_data()
    authors = data['authors']
    platform_count = sum(bool(a['platforms']) for a in authors.values())
    if check_only:
        existing = lib_paths.load_json(DATA_TARGET, None) or {}
        changed = existing.get('authors') != authors
        print(f'{len(authors)} 位作者，平台字段 {platform_count} 个')
        if changed:
            print(f'Would write: {lib_paths.get_safe_relpath(DATA_TARGET)}')
        else:
            print('No change needed')
        return 1 if changed else 0
    lib_paths.save_json(DATA_TARGET, data)
    print(f'Written {len(authors)} authors -> {lib_paths.get_safe_relpath(DATA_TARGET)}'
          f'（含平台信息 {platform_count} 位）')
    return 0


# ---------------------------------------------------------------------------
# --readme：重建根 README 作者表（原 build_readme_authors.py）
# ---------------------------------------------------------------------------
def build_readme_rows() -> list[tuple[str, str, int, str]]:
    """收集作者行（编号, 名称, 模型数, 链接）。作者名优先 authors.json，缺失回退 README。"""
    authors_index = lib_readme.load_authors_index().get('authors') or {}
    rows: list[tuple[str, str, int, str]] = []
    for folder in sorted(p.name for p in MODELS_DIR.iterdir() if p.is_dir()):
        if not FOLDER_RE.match(folder):
            continue
        author_dir = MODELS_DIR / folder
        readme_file = next((author_dir / f for f in ['README.md', 'readme.md', 'Readme.md']
                            if (author_dir / f).is_file()), None)
        link = f'.../../Models/{folder}'

        # 集中数据优先；未收录或缺失时回退读 README（name 为数组，取规范名）
        entry = authors_index.get(folder) or {}
        names = entry.get('name') or []
        if isinstance(names, str):
            names = lib_readme.split_author_names(names)
        author_name = names[0] if names else ''
        if not author_name and readme_file:
            author_name = lib_readme.parse_author_name_value(
                readme_file.read_text(encoding='utf-8', errors='ignore'))
        if not author_name:
            author_name = '暂无'

        model_count = sum(1 for sub in author_dir.iterdir()
                          if sub.is_dir() and not sub.name.startswith('.'))
        rows.append((folder, author_name, model_count, link))
    return rows


def build_readme_table(rows: list[tuple[str, str, int, str]], is_en: bool) -> str:
    """渲染作者表（中/英表头；空表给占位行）。"""
    if is_en:
        header, empty_row = '| ID | Author Name | Total Models |', '| - | None | 0 |'
    else:
        header, empty_row = '| 编号 | 作者名称 | 收录数量 |', '| - | 暂无 | 0 |'
    separator = '| --- | --- | ---: |'

    lines = [header, separator]
    for folder, author_name, model_count, link in rows:
        safe = author_name.replace('|', '\\|')
        label = 'None' if (is_en and safe == '暂无') else safe
        lines.append(f'| {folder} | [{label}]({link}) | {model_count} |')
    return '\n'.join(lines) if rows else f'{header}\n{separator}\n{empty_row}'


def update_root_readme(rows: list[tuple[str, str, int, str]], path: Path, is_en: bool) -> bool:
    """在 AUTHORS_LIST 标记区间内替换作者表；无变化返回 False。"""
    content = path.read_text(encoding='utf-8')
    start, end = lib_readme.AUTHORS_LIST_START, lib_readme.AUTHORS_LIST_END
    if start not in content or end not in content:
        print(f'Error: Markers not found in {path}')
        return False

    before = content.split(start, 1)[0] + start + '\n'
    after = '\n' + end + content.split(end, 1)[1]
    updated = before + build_readme_table(rows, is_en) + after

    if updated != content:
        path.write_text(updated, encoding='utf-8')
        print(f'Updated {path} with {len(rows)} rows.')
        return True
    print(f'No changes in {path}')
    return False


def write_root_readmes() -> int:
    """重建根 README 与 README-EN 的作者表。"""
    readme_path = WORKSPACE_ROOT / 'README.md'
    readme_en_path = WORKSPACE_ROOT / 'README-EN.md'
    if not MODELS_DIR.is_dir():
        print(f'Error: {MODELS_DIR} directory not found.')
        return 2
    if not readme_en_path.is_file():
        print(f'Error: {readme_en_path} not found.')
        return 2
    rows = build_readme_rows()
    update_root_readme(rows, readme_path, False)
    update_root_readme(rows, readme_en_path, True)
    return 0


def build_category_map_cmd() -> int:
    """从 character/*.json 现算分类 + 更新根 README 模型分类区块（不落盘 category_map.json）。

    收纳自 02 脚本：作品分类是根 README 展示区块，与作者表同属"根 README 生成"。
    仅更新 README 区块，不重写知识库数据（数据不变）。
    """
    data = load_kb_json(lib_paths.MODEL_INFO_DIR)
    cat_map = build_category_map(data)
    un = [k for k, v in (data.get("works") or {}).items()
          if not (isinstance(v, dict) and v.get("category"))]
    total = sum(len(v) for v in cat_map.values())
    print(f"分类（从 character/*.json 现算）: {total} 个作品分布在 {len(cat_map)} 个大类")
    changed, action = update_readme_works_section(
        WORKSPACE_ROOT / "README.md", data)
    if changed:
        print(f"根 README 模型分类区块已{action}")
    if un:
        print(f"提示：{len(un)} 个作品未标注 category，已归为 Other："
              f"{', '.join(sorted(un))}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', action='store_true', help='生成集中作者数据 authors.json')
    parser.add_argument('--readme', action='store_true', help='重建根 README 作者表')
    parser.add_argument('--build-category-map', action='store_true',
                        help='更新根 README 模型分类区块（从 character/*.json 现算）')
    parser.add_argument('--check', action='store_true', help='只检查 --data 差异（不写盘）')
    args = parser.parse_args()

    # 作品分类区块：独立功能，优先处理
    if args.build_category_map:
        return build_category_map_cmd()

    # 默认两件都做；显式指定某一项时只做该项
    do_data = args.data or not args.readme
    do_readme = args.readme or not args.data

    code = 0
    if do_data:
        code = write_authors_data(args.check) or code
    if do_readme:
        if args.check:
            print('--check 仅对 --data 生效，跳过根表更新')
        else:
            code = write_root_readmes() or code
    return code


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
