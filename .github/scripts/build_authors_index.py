#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成集中作者数据 .github/data/meta/authors.json，供各脚本统一读取，
避免 organize_models / format_author_readme / build_readme_authors /
generate_model_readmes 各自扫描作者 README。

数据来源：Models/<编号>/README.md 的 Author 段（名称、别名、平台账号），
根 README.md 作者索引补缺（编号目录无 README 时）。

用法：
  python build_authors_index.py            # 写回 authors.json
  python build_authors_index.py --check    # 只检查，有差异时退出码 1
"""
import sys

from lib import paths as lib_paths
from lib import readme as lib_readme


def build_authors_data() -> dict:
    """扫描 Models 与根 README，构建集中作者数据。"""
    return lib_readme.build_authors_data(
        lib_paths.WORKSPACE_ROOT / 'Models',
        lib_paths.WORKSPACE_ROOT / 'README.md',
    )


def main() -> int:
    check_only = any(a in ('--check', '--dry-run') for a in sys.argv[1:])
    target = lib_paths.data_path('meta', 'authors.json')

    data = build_authors_data()
    authors = data['authors']
    if check_only:
        existing = lib_paths.load_json(target, None) or {}
        # generated 时间戳每次运行都变，只比较作者数据本体
        changed = existing.get('authors') != authors
        print(f"{len(authors)} 位作者，平台字段 {sum(bool(a['platforms']) for a in authors.values())} 个")
        if changed:
            print(f"Would write: {lib_paths.get_safe_relpath(target)}")
        else:
            print("No change needed")
        return 1 if changed else 0

    lib_paths.save_json(target, data)
    platform_count = sum(bool(a['platforms']) for a in authors.values())
    print(f"Written {len(authors)} authors -> {lib_paths.get_safe_relpath(target)}"
          f"（含平台信息 {platform_count} 位）")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
