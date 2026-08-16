#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型文件批量重命名工具（本仓库专用）。

从 02_rename_model_folders.py 拆出：02_rename_model_folders.py 只负责模型文件夹重命名，
本脚本负责模型文件（.ysm 及附属 .zip/.7z/.rar/.bbmodel 等）重命名。

命名规则:
    <文件夹名(去评级)>[变体][_v版本][_副本序号]<后缀>
    例: VOC_初音_Miku_兔子洞Ver1.1.ysm -> VOC_初音_Miku_swimsuit_v1.1.ysm

  1. 变体词经 .github/data/model-info/skin_tags.json 标准化表规范化（新->new、旧->old、
     泳装版->swimsuit）；未收录的变体词丢弃，不追加到文件名。
  2. 版本号（v2 / ver2 / 1.1 / v1.1 等）统一为 _v<版本>。
  3. 副本序号（(1)、（1）、_1、-1）统一为 _<数字>。

默认 dry-run 只预览；加 --apply 才真正重命名。

用法:
  python '.github/scripts/models_organize/02_rename_model_files.py'                       # 预览（默认 Models/）
  python '.github/scripts/models_organize/02_rename_model_files.py' --apply               # 执行
  python '.github/scripts/models_organize/02_rename_model_files.py' Models/0001 --apply   # 指定作者目录
  python '.github/scripts/models_organize/02_rename_model_files.py' 某.ysm                # 指定单个文件
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import models as lib_models
from lib import paths as lib_paths


# 允许重命名的模型文件扩展名（模型本体 + 常见附属压缩包/源文件）
ALLOWED_FILE_EXTS = {'.ysm', '.zip', '.7z', '.rar', '.tar', '.gz', '.bbmodel'}


_VARIANT_TAGS: dict[str, str] | None = None


def _variant_tags() -> dict[str, str]:
    """变体词 → 英文标准名映射（读新 skin_tags.json 标准化表）。"""
    global _VARIANT_TAGS
    if _VARIANT_TAGS is None:
        tags = lib_paths.load_json(
            lib_paths.data_path('model-info', 'skin_tags.json'), {})
        mapping: dict[str, str] = {}
        for key, t in tags.items():
            name = t.get('name') or {}
            en_std = name.get('en')
            if not en_std:
                continue  # 无英文标准名，不参与文件名规范化
            mapping[str(key).lower()] = str(en_std)
            mapping[str(en_std).lower()] = str(en_std)
            if name.get('zh'):
                mapping[str(name['zh'])] = str(en_std)
            for a in t.get('aliases') or []:
                mapping[str(a).lower()] = str(en_std)
        _VARIANT_TAGS = mapping
    return _VARIANT_TAGS


def _resolve_variant(word: str) -> str | None:
    """把文件名变体词规范化为英文标准名（查 skin_tags.json 新格式）。

    命中：word 匹配某标签的键/name/aliases → 返回其 name.en；
    去"版"后缀再匹配一次。未命中（如 RABBIT1、旧命名残留）返回 None。
    """
    mapping = _variant_tags()
    key = word.lower()
    if key in mapping:
        return mapping[key]
    if key.endswith('版') and key[:-1] in mapping:
        return mapping[key[:-1]]
    return None


def parse_file_stem(file_stem: str, folder_name: str) -> tuple[str, str, str]:
    """智能解析文件名，分离为：变体名、版本号、副本序号（如 兔子洞Ver1.1 -> ("", "_v1.1", "")）。"""
    stem = file_stem
    # 1. 提取末尾的副本序号 (如 (1)、（1）、_1、-1)
    copy_tag = ""
    copy_match = re.search(r'[\s_-]*[\(（](\d+)[\)）]$|[\s_-]+(\d+)$', stem)
    if copy_match:
        num = copy_match.group(1) or copy_match.group(2)
        copy_tag = f"_{num}"
        stem = stem[:copy_match.start()].strip('-_ ')
    # 2. 提取版本号。双分支：优先"版本前缀+纯整数"（v2/ver2），其次"带小数点版本"
    #    （1.1/v2.1/Ver1.1，前缀 v/ver/version/r 可选）。
    #    纯整数分支要求数字前有 v/ver/version 前缀、且前缀前是分隔符/非词字符，
    #    避免误伤 RABBIT1、Fox1 这类编号尾数（数字紧贴字母、无版本前缀）。
    version_tag = ""
    version_match = re.search(
        r'(?:[\s_.-]+|(?<=[^\w]))(?:ver(?:sion)?|v)[\s_.-]*(\d+)(?![.\w])'
        r'|(?:(?:[\s_-]|(?<=[^\w]))*)(?:ver(?:sion)?|v|r)?[\s._-]*(\d+(?:\.\d+)+)',
        stem, re.IGNORECASE)
    if version_match:
        version_num = version_match.group(1) or version_match.group(2)
        version_tag = f"_v{version_num}"
        stem = (stem[:version_match.start()] + stem[version_match.end():]).strip('-_ ')
    # 3. 提取变体名称（对比 folder_name，过滤已有的关键词；冒号视为分隔符——旧命名残留）
    clean_stem = re.sub(r'[-—\s:：]+', '_', stem)
    folder_keywords = set(w.lower() for w in re.split(r'[-_\s]+', folder_name) if w)
    folder_keywords.update({'la', 'lb', 'lc', 'ld', 'ver', 'version'})
    file_words = [w for w in re.split(r'[-_\s]+', clean_stem) if w]
    candidate = [w for w in file_words if w.lower() not in folder_keywords]
    # 变体词通过标准化表（skin_tags.json）规范化：命中 -> 英文标准名
    # （新->new、旧->old、泳装版->swimsuit）；未命中（如 BA_月雪宫子：RABBIT1 的
    # RABBIT1、旧命名残留）-> 丢弃，不追加到文件名，避免 ..._Tsukiyuki-Miyako_RABBIT1
    # 这类未收录杂项混入命名。
    variant_words = [n for v in candidate if (n := _resolve_variant(v))]
    variant_tag = f"_{'_'.join(variant_words)}" if variant_words else ""
    return variant_tag, version_tag, copy_tag


def rename_files_cmd(target_path: Path, apply_changes: bool = False) -> int:
    """重命名模型文件：<文件夹名(去评级)>[变体][_v版本][_副本序号]<后缀>。

    dry-run 默认预览，--apply 才真正改名。
    """
    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        files = [p for p in target_path.rglob('*') if p.is_file()]
    else:
        print(f"错误: 路径不存在 -> {target_path}", file=sys.stderr)
        return 2

    renamed_count = 0
    skipped_count = 0
    print(f"{'='*20} "
          f"{'执行模式: 真实修改 (--apply)' if apply_changes else '执行模式: 预览模式 (Dry-Run)'}"
          f" {'='*20}\n")
    for file_path in sorted(files):
        if file_path.suffix.lower() not in ALLOWED_FILE_EXTS:
            continue
        folder_name = file_path.parent.name
        base_folder_name = lib_models.clean_folder_name(folder_name)
        original_name = file_path.name
        ext = file_path.suffix
        variant_tag, version_tag, copy_tag = parse_file_stem(file_path.stem, folder_name)
        new_stem = f"{base_folder_name}{variant_tag}{version_tag}{copy_tag}"
        new_stem = re.sub(r'_+', '_', new_stem).strip('_')
        new_name = f"{new_stem}{ext}"
        if original_name == new_name:
            skipped_count += 1
            continue
        new_file_path = file_path.parent / new_name
        # 同名冲突处理
        if apply_changes and new_file_path.exists():
            counter = 1
            while new_file_path.exists():
                new_file_path = file_path.parent / f"{new_stem}_{counter}{ext}"
                counter += 1
            new_name = new_file_path.name
        print(f"[匹配] 目录: {folder_name}/")
        print(f"  原名: {original_name}")
        print(f"  新名: {new_name}\n")
        if apply_changes:
            file_path.rename(new_file_path)
        renamed_count += 1
    print(f"{'='*50}")
    print(f"统计完成: 待修改/已修改 = {renamed_count}, 无需修改 = {skipped_count}")
    if not apply_changes and renamed_count > 0:
        print("\n提示: 当前为预览模式，磁盘文件未修改。如确认无误，请在命令末尾加上 --apply 执行！")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='*',
                        help='文件或目录（默认 Models/；目录递归收集模型文件）')
    parser.add_argument('--apply', action='store_true',
                        help='真正执行重命名（默认 dry-run 预览）')
    parser.add_argument('--root', metavar='PATH', default=None,
                        help='仓库根目录（默认自动检测）')
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else lib_paths.WORKSPACE_ROOT
    target = Path(args.paths[0]) if args.paths else (root / 'Models')
    return rename_files_cmd(target, apply_changes=args.apply)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
