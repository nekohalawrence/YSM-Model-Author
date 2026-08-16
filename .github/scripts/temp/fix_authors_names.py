#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 authors.json 中错误的作者名称（一次性数据修复）。

问题类型与处理：
  1. URL/描述垃圾：name 含 http/www/bilibili/◆ 等（如 0110 被 URL 污染）→
     从 `◆模型&动作：作者名（URL` 中提取真实作者名，丢弃 URL 片段项。
  2. 拼接名：一个字符串含多个名字（空格分隔且含多个 #，如 '#天弓干亦 #筅袔'）→
     拆分为独立数组项。
  3. 空壳作者（name=['暂无'] 且无 readme）→ 删除条目。
  （不处理重复别名——大小写/变体别名可能有意义，保留原样；0110 已手工处理，跳过。）

用法:
  python .github/scripts/temp/fix_authors_names.py            # dry-run 预览
  python .github/scripts/temp/fix_authors_names.py --apply    # 真正写回
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

AUTHORS_JSON = Path('.github/data/author-info/authors.json')
_GB = re.compile(r'[：:]([^（(]+)（')


def norm(s: str) -> str:
    """名称规范化：去 #/＃/空白/下划线/连字符/括号，转小写（用于查重）。"""
    return re.sub(r'[\s#＃_\-·（）()]', '', s).lower()


def is_url_garbage(n: str) -> bool:
    """是否 URL 片段垃圾项。"""
    low = n.lower()
    return ('http' in low or 'www.' in low or 'bilibili' in low
            or 'space.' in low or '44218' in low)


def fix_names(names: list[str]) -> list[str]:
    """修复一个作者的 name 列表；返回清洗后的列表。"""
    out: list[str] = []
    for n in names:
        if '◆' in n:
            # 描述性垃圾：从「◆xx：作者名（URL」提取作者名
            m = _GB.search(n)
            out.append('#' + (m.group(1).strip() if m else '未知'))
            continue
        if is_url_garbage(n):
            continue  # 纯 URL 片段，丢弃
        if ' ' in n and n.count('#') > 1:
            # 多名字拼接：按空格拆分
            out.extend(x.strip() for x in n.split() if x.strip())
        else:
            out.append(n)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='真正写回（默认 dry-run）')
    args = parser.parse_args()

    data = json.loads(AUTHORS_JSON.read_text(encoding='utf-8'))
    authors = data.get('authors') or {}
    plan: dict[str, tuple[list, list]] = {}
    to_delete: list[str] = []
    for aid in sorted(authors):
        if aid == '0110':
            print(f'[跳过] {aid}: 用户已手动修复，不处理')
            continue
        a = authors[aid]
        names = list(a.get('name') or [])
        if len(names) == 1 and names[0] in ('暂无', '') and not a.get('readme'):
            to_delete.append(aid)
            print(f'[空壳删除] {aid}: name={names} readme 为空')
            continue
        fixed = fix_names(names)
        if fixed != names:
            plan[aid] = (names, fixed)

    print(f'待修复作者 {len(plan)} 个，待删除空壳 {len(to_delete)} 个：')
    for aid, (old, new) in plan.items():
        print(f'  {aid}:')
        print(f'    旧: {old}')
        print(f'    新: {new}')

    if not plan and not to_delete:
        print('无需修复。')
        return 0
    if not args.apply:
        print(f'\ndry-run：未写回。确认无误后加 --apply 执行。')
        return 0

    for aid, (_, new) in plan.items():
        authors[aid]['name'] = new
    for aid in to_delete:
        del authors[aid]
        print(f'已删除空壳作者条目: {aid}')
    data['generated'] = __import__('datetime').datetime.now().isoformat()
    AUTHORS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n已修复 {len(plan)} 位作者、删除 {len(to_delete)} 个空壳: {AUTHORS_JSON}')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
