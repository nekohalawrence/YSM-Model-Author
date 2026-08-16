#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性导入：把「YSM自动分类整理工具」的 关键词库（ysm-作者IP关键词.xml）并入本库。

XML 结构（type="IP" 规则 = 作品）：
    <rule type="IP" name="作品名" keywords="角色名|作品名|英文名" />
目标：把每个 IP 的角色/识别关键词，作为该作品缺失的角色别名导入
      character/<作品>.json（source=manual，note 标记来源），让 resolve_name 能识别。

映射：社区 IP 名 -> 本库作品键（未映射的 IP 列出，不自动导入）。
作者（type="作者"）规则暂不导入（本库作者识别走 README Name，另案处理）。

用法:
  python .github/scripts/temp/import_yamf_keywords.py                 # dry-run 预览
  python .github/scripts/temp/import_yamf_keywords.py --apply         # 真正写入
  python .github/scripts/cli.py import-kb [--apply]
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import paths as lib_paths
from lib.kb.storage import load_kb_json, save_kb_json

# 社区 IP 名 -> 本库作品键（社区用中文全名，本库用缩写键）
IP_KEY_MAP = {
    '奴隶少女希尔薇': 'TF', '碧蓝航线': 'AL', '奥特曼': 'UT', '原神': 'GI',
    '闪耀星骑士': 'TSK', 'EVA': 'NGE', '东方Project': 'Touhou', '碧蓝幻想': 'Granblue',
    '蔚蓝档案': 'BA', '绝区零': 'ZZZ', '崩坏：星穹铁道': 'HSR', '崩坏3': 'HI3',
    '明日方舟': 'AK', '赛马娘': 'UmaMusume', 'VOCALOID/虚拟歌手': 'VOC', '火影忍者': 'NAR',
    '为美好的世界献上祝福': 'KonoSuba', '魔女之旅': 'MNT', '孤独摇滚！': 'BtR',
    '更衣人偶坠入爱河': 'Kisekoi', '约会大作战': 'DAL', '鸣潮': 'WW', '终末地': 'AKE',
    '少女前线': 'GF', '胜利女神：妮姬': 'Nikke',
}

DEFAULT_XML = Path(r'D:\OtherSoftware\YSM自动分类整理工具\ysm-作者IP关键词.xml')


def _norm_cn(s: str) -> str:
    return s.replace(' ', '').replace('\u3000', '').strip()


def _norm_en(s: str) -> str:
    return s.strip().lower()


def collect_existing(roles: list[dict], works: dict) -> dict[str, set[str]]:
    """作品键 -> 已有别名集合（含作品元数据名 + 角色 zh/en，归一化）。"""
    got: dict[str, set[str]] = {}
    for key, entry in (works or {}).items():
        if isinstance(entry, dict):
            for f in ('en', 'zh', 'ja'):
                names = entry.get(f) or []
                if isinstance(names, str):
                    names = [names]
                for x in names:
                    if x:
                        got.setdefault(str(key), set()).add(_norm_cn(str(x)))
        elif isinstance(entry, list):
            for x in entry:
                if x:
                    got.setdefault(str(key), set()).add(_norm_cn(str(x)))
        got.setdefault(str(key), set()).add(_norm_cn(str(key)))
    for r in roles:
        work = r.get('work', '')
        for f, norm in (('zh', _norm_cn), ('en', _norm_en)):
            v = r.get(f) or []
            lst = v if isinstance(v, list) else ([v] if v else [])
            for x in lst:
                got.setdefault(work, set()).add(norm(x))
    return got


def import_keywords(xml_path: Path, apply: bool) -> int:
    """把 XML 的 IP 关键词并入 character；dry-run 默认。返回拟新增数。"""
    data = load_kb_json(lib_paths.MODEL_INFO_DIR)
    roles = data.get('roles') or []
    existing = collect_existing(roles, data.get('works') or {})

    tree = ET.parse(xml_path)
    root = tree.getroot()
    plan: dict[str, list[str]] = {}     # 作品键 -> 拟新增关键词
    unmapped: list[tuple[str, int]] = []  # (IP 名, 关键词数)

    for rule in root.findall('rule'):
        if rule.get('type') != 'IP':
            continue
        ip_name = rule.get('name', '').strip()
        kws = [k.strip() for k in (rule.get('keywords') or '').split('|') if k.strip()]
        key = IP_KEY_MAP.get(ip_name)
        if not key:
            unmapped.append((ip_name, len(kws)))
            continue
        if key not in (data.get('works') or {}):
            unmapped.append((ip_name, len(kws)))
            continue
        for kw in kws:
            norm = _norm_en(kw) if not _norm_cn(kw) or kw.isascii() else _norm_cn(kw)
            have = existing.get(key, set())
            if norm in have:
                continue
            plan.setdefault(key, []).append(kw)

    total = sum(len(v) for v in plan.values())
    print(f'关键词库导入（{xml_path.name}，catalog={root.get("catalogVersion", "?")}）:')
    print(f'  拟新增角色别名 {total} 条，涉及 {len(plan)} 个作品:')
    for key in sorted(plan):
        print(f'    [{key}] +{len(plan[key])}: {", ".join(plan[key][:12])}'
              + (' ...' if len(plan[key]) > 12 else ''))
    if unmapped:
        print(f'  未映射的 IP（未导入，可手工处理）:')
        for ip, n in unmapped:
            print(f'    {ip}（{n} 个关键词）')

    if not apply:
        print('\ndry-run: 未写入。确认无误后加 --apply 执行。')
        return total

    # 写入：每个新关键词作为一个 manual 角色条目（zh=关键词，en 空）
    added = 0
    for key, kws in plan.items():
        for kw in kws:
            roles.append({'work': key, 'zh': [kw], 'en': [],
                          'source': 'manual', 'note': 'import yamf-kb'})
            added += 1
    data['roles'] = roles
    save_kb_json(lib_paths.MODEL_INFO_DIR, data)
    print(f'已写入 {added} 条角色别名到 character/。')
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('xml', nargs='?', default=str(DEFAULT_XML),
                        help='ysm-作者IP关键词.xml 路径')
    parser.add_argument('--apply', action='store_true', help='真正写入（默认 dry-run）')
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.is_file():
        print(f'错误: 找不到 XML: {xml_path}', file=sys.stderr)
        return 2
    import_keywords(xml_path, args.apply)
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
