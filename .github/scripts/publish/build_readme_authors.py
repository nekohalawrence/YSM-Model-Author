#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重建根 README / README-EN 的作者索引表（AUTHORS_LIST 标记区间）。

作者名称优先取自集中数据 authors.json（build_authors_index 生成），未收录时
回退解析作者 README；复用 lib/readme.py 的统一解析与 AUTHORS_LIST 标记常量。
"""
import re
import sys
from pathlib import Path

# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as lib_paths  # noqa: E402
from lib import readme as lib_readme  # noqa: E402

readme_path = lib_paths.WORKSPACE_ROOT / 'README.md'
readme_en_path = lib_paths.WORKSPACE_ROOT / 'README-EN.md'
models_dir = lib_paths.WORKSPACE_ROOT / 'Models'

FOLDER_RE = re.compile(r'^(\d{4})$')


def build_rows() -> list[tuple[str, str, int, str]]:
    """收集作者行（编号, 名称, 模型数, 链接）。作者名优先 authors.json，缺失回退 README。"""
    authors_index = lib_readme.load_authors_index().get('authors') or {}
    rows: list[tuple[str, str, int, str]] = []
    for folder in sorted(p.name for p in models_dir.iterdir() if p.is_dir()):
        if not FOLDER_RE.match(folder):
            continue
        author_dir = models_dir / folder
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


def build_table(rows: list[tuple[str, str, int, str]], is_en: bool) -> str:
    """渲染作者表（中/英表头；空表给占位行）。"""
    if is_en:
        header = '| ID | Author Name | Total Models |'
        empty_row = '| - | None | 0 |'
    else:
        header = '| 编号 | 作者名称 | 收录数量 |'
        empty_row = '| - | 暂无 | 0 |'
    separator = '| --- | --- | ---: |'

    lines = [header, separator]
    for folder, author_name, model_count, link in rows:
        safe = author_name.replace('|', '\\|')
        if is_en and safe == '暂无':
            label = 'None'
        else:
            label = safe
        lines.append(f'| {folder} | [{label}]({link}) | {model_count} |')
    return '\n'.join(lines) if rows else f'{header}\n{separator}\n{empty_row}'


def update_readme(rows: list[tuple[str, str, int, str]], path: Path, is_en: bool) -> bool:
    """在 AUTHORS_LIST 标记区间内替换作者表；无变化返回 False。"""
    content = path.read_text(encoding='utf-8')
    start, end = lib_readme.AUTHORS_LIST_START, lib_readme.AUTHORS_LIST_END
    if start not in content or end not in content:
        print(f'Error: Markers not found in {path}')
        return False

    before = content.split(start, 1)[0] + start + '\n'
    after = '\n' + end + content.split(end, 1)[1]
    updated = before + build_table(rows, is_en) + after

    if updated != content:
        path.write_text(updated, encoding='utf-8')
        print(f'Updated {path} with {len(rows)} rows.')
        return True
    print(f'No changes in {path}')
    return False


def main() -> int:
    if not models_dir.is_dir():
        print(f'Error: {models_dir} directory not found.')
        return 2
    if not readme_en_path.is_file():
        print(f'Error: {readme_en_path} not found.')
        return 2
    rows = build_rows()
    update_readme(rows, readme_path, False)
    update_readme(rows, readme_en_path, True)
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
