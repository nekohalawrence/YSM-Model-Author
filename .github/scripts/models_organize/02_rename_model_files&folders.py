#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型文件夹批量重命名工具（本仓库专用）。

命名模板:
    <英文作品名>_<中文角色名>[_中文皮肤]_<英文角色名>[_英文皮肤]_<评定等级>
    评定等级: LA / LB / LC / LD（可选）

扫描范围（严格两层，更深一层绝不处理）:
    Models/<作者4位编号>/<模型名>      （作者 + 模型，两层）
    Other-YSM-Models/<模型名>          （一层）
previews/ 子目录及其 preview*.png 不会被当作目标；
父文件夹改名时 previews/ 自动跟随，预览图文件名保持不变。

规范化规则:
  1. 全小写英文 token 首字母大写（kipfel -> Kipfel，lenna -> Lenna）；
     已含大写的（Ryou-Yamada、McDonald）不动。
  2. 中文角色名与英文角色名之间的连字符改为下划线
     （山田凉-Ryou-Yamada -> 山田凉_Ryou-Yamada）。
  3. 不同字段之间统一用 _ 连接：中文皮肤（_太刀、_泳装、_原皮、_万圣节…）完整保留；
     英文名内部的姓氏-名字连字符（如 Togawa-Sakiko）是名字写法，不属于字段分隔，保留 -。
  4. 作品名前缀统一为规范缩写（含作品全称自动转缩写，如 Azur Lane -> AL）；
     无前缀时用对照数据库反查角色
     （.github/data/model-info/：character/<作品>.json = 作品元数据 + 角色，
     可直接用编辑器改；知识库由本脚本统一维护，实现位于 lib/kb/）。
     唯一命中才填作品名，否则 Unknown；多候选冲突也标 Unknown 并提示。
  5. 知识库为纯手工维护（无自动构建）：直接编辑 .github/data/model-info/ 下的
     character/<作品>.json；或用 --roles 交互式增删改查。手改后无需任何命令，
     脚本下次运行即生效。

默认 dry-run 只预览；加 --apply 才真正重命名。

用法（按功能分组）:

  预览与重命名:
    python '.github/scripts/models_organize/02_rename_model_files&folders.py'              # 预览
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --apply      # 执行重命名
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --path Models # 只处理单个根
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --rename-files --path Models/0001 --apply  # 重命名模型文件（合并自 rename_model_files.py）
  
  跨作品同名冲突（skip · conflict）:
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --apply
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --apply --skip-conflict
    --apply 时遇到匹配到多个作品的同名角色，逐项询问归属作品（选择后收录数据库
    并补前缀重命名，下次不再冲突）；加 --skip-conflict 则跳过选择、不处理
    （保持原文件夹名，防止无人值守时卡住）。
  
  交互学习（--learn 时，独立于 --apply）:
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --learn [--apply]
    未收录（Unknown）且有可辨识角色名的文件夹，会逐项询问"作品缩写"，
    确认后收录进数据库并自动补全重命名：
    跨作品同名（conflict）的会先展示候选作品（0=GF 1=GF2），输入编号或
    缩写即可确定归属——本质是在给文件夹补上"作品前缀"（推荐命名规范：所有
    文件夹名都以 <作品缩写>_ 开头，如 GF_夏安_XiaAn，可彻底避免同名冲突）。

  预览显示过滤（控制台与报告一致；默认只显示已修改 fix）:
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --show ok               # 只显示已规范
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --show fix,ok            # 显示已修改 + 已规范
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --show-kb --show-fix     # 显示知识库补全修复 / 已修改（快捷开关可组合）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --show-skip              # 只显示跳过（含问题）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --show-all               # 显示全部条目
  
  分类体系（3 个主状态 + 问题级计数）:
    ok    已规范：无任何问题、无改动
    fix   已修改：本次有改动（知识库补全作品名/中英文名、格式修正、别名归一），
          显示修改内容；若有遗留问题一并显示
    skip  跳过：除 ok 外未改动的条目（副本后缀 / 空名 / 纯数字，或有遗留问题但未改名），
          预览时显示其对应问题
    问题级计数：统计非 ok 条目的问题（fix 遗留 + skip 未处理），每类单独计数；
    跳过条目按问题分组显示：一条目含多个问题时会同时出现在对应的多个分组中
    （如 同时含 other + en-name -> 两个分组都能看到），便于逐类处理。

  知识库维护（操作 × 对象；不带对象则交互询问，快捷名保留兼容）:
    操作: --add(添加) --del(删除) --list(列出) --check(检查) --merge(合并)
          --set-default(设默认名) --rename(重命名键,仅作品) --suggest(建议,仅角色)
    对象: --role(角色) / --work(作品)，与操作组合（如 --merge --work 合并作品）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --roles           # 角色综合菜单（推荐）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --add --role      # 添加角色
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --add --work      # 添加作品（快捷 --add-work）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --del --work      # 删除作品（连同角色）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --list --work     # 列出作品
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --check --work    # 作品检查
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --merge --work    # 合并作品（名称/角色名重叠提候选）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --merge           # 不带对象→交互询问 角色/作品
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --set-default --role  # 设角色默认名（快捷 --set-default-role）
    python '.github/scripts/models_organize/02_rename_model_files&folders.py' --rename --work   # 重命名作品键（快捷 --rename-work OLD NEW）
    根 README 模型分类区块：04_generate&update_root_readme.py --build-category-map


维护说明：
- 直接编辑 .github/data/model-info/ 下的 json 文件即可增删改（手改即时生效）
- 也可以命令行：02_rename_model_files&folders.py --add 加角色 / --del 删 / --list 看
- --apply 重命名时，若目标名已存在（同名冲突）自动加 -数字 副本序号
  （如 VOC_初音_Chuyin 与已有 VOC_初音_Miku 冲突 -> 重命名为 VOC_初音_Miku-1，
  副本序号放在评级前，幂等；已是最小副本时保持不动）
- 数据库为多文件结构：character/<作品>.json（作品元数据 + 角色，合并格式，
  避免单文件过大）、merge_skips.json（--merge 跳过记录）
- 知识库为纯手工维护：条目 = {"work","zh","en"}（可选 note），无 source 键，
  无自动构建（--build-kb 已删除）
- 皮肤词表外部化：.github/data/model-info/skin_tags.json（通用 common + 作品专属键），
  角色条目不再存 skin 键；皮肤由 --roles 或交互学习维护进皮肤表
- 角色条目的 cn/en 可以是字符串或数组：数组第一个为规范名（补全默认用它），
  其余为别名（如 "zh": ["昔涟", "大昔涟", "小昔涟"]）
- works 的值支持三种写法：平铺数组、空 []、按语言分类的对象
  （如 "AK": {"zh": ["明日方舟"], "en": ["Arknights", "Arknight"]}，
   cn/en/ja 等语言键可自由增删）
- character/*.json 为作品数据权威源（不再从 README.md 同步，亦无独立
  works.json）：交互添加新作品用 --add-work；分类（category 字段，字符串=
  单一分类 / 数组=多分类，如 ["Anime","Manga","Novel"]）；根 README 的
  "模型分类"区块由 04_generate&update_root_readme.py --build-category-map
  从 character/*.json 现算更新（不落盘 category_map.json）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import models as lib_models
from lib import paths as lib_paths
from lib.kb.cmds import (
    add_manual_entries, add_skin_tag, ask, build_indexes,
    check_works_cmd, del_entries, del_works_cmd, get_target_dirs, list_db,
    list_works_cmd, load_skin_tags, merge_works_cmd, roles_cmd, run_check,
    run_merge, run_suggest, save_skin_tags, set_default_work_cmd,
    sync_variant_to_skin_tags,
)
from lib.kb.category import (
    CATEGORIES, build_category_map, update_readme_works_section,
)
from lib.kb.parse import (
    resolve_name,
)
from lib.kb.storage import (
    _safe_name, load_kb_json, migrate_from_sqlite, save_kb_json,
)
from lib.kb.sync import (
    build_work_index,
)

REPO_ROOT = lib_paths.WORKSPACE_ROOT
KB_DEFAULT = lib_paths.MODEL_INFO_DIR
DEFAULT_ROOTS = [REPO_ROOT / "Models", REPO_ROOT / "Other-YSM-Models"]


# 知识库角色条目为纯手工维护（无自动构建）：直接读 .github/data/model-info/ 的
# character/<作品>.json，不再从文件夹名自动重建（--build-kb 已删除）。
# 增删改用交互命令 --roles（推荐）或 --add/--del/--list。


# ---------------------------------------------------------------------------
# 模型文件重命名（合并自 rename_model_files.py）
# ---------------------------------------------------------------------------
ALLOWED_FILE_EXTS = {'.ysm', '.zip', '.7z', '.rar', '.tar', '.gz', '.bbmodel'}


_VARIANT_TAGS: dict[str, str] | None = None


def _variant_tags() -> dict[str, str]:
    """变体对照表：文件名变体词 -> 英文规范名（.github/data/model-info/variant_tags.json）。"""
    global _VARIANT_TAGS
    if _VARIANT_TAGS is None:
        _VARIANT_TAGS = lib_paths.load_json(
            lib_paths.data_path('model-info', 'variant_tags.json'), {})
    return _VARIANT_TAGS


def _resolve_variant(word: str) -> str | None:
    """把文件名变体词规范化为英文（查 variant_tags.json，结构 {英文名: {cn/en 列表}}）。

    命中顺序：word==键 -> 命中某条目的 cn/en 别名列表 -> 去"版"后缀匹配 cn。
    未命中（如 RABBIT1、旧命名残留）返回 None，调用方丢弃该变体，不追加到文件名。
    """
    tags = _variant_tags()
    key = word.lower()
    for canonical, langs in tags.items():
        if key == canonical:
            return canonical
        cn_list = [c for c in (langs.get('zh') or []) if c]
        en_list = [e for e in (langs.get('en') or []) if e]
        if word in cn_list or word in en_list or key in cn_list or key in en_list:
            return canonical
        if key.endswith('版') and key[:-1] in cn_list:
            return canonical
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
    # 变体词通过对照表（variant_tags.json）规范化：命中 -> 英文规范名
    # （新->new、旧->old、泳装版->swimsuit）；未命中（如 BA_月雪宫子：RABBIT1 的
    # RABBIT1、旧命名残留）-> 丢弃，不追加到文件名，避免 ..._Tsukiyuki-Miyako_RABBIT1
    # 这类未收录杂项混入命名。
    variant_words = [n for v in candidate if (n := _resolve_variant(v))]
    variant_tag = f"_{'_'.join(variant_words)}" if variant_words else ""
    return variant_tag, version_tag, copy_tag


def rename_files_cmd(target_path: Path, apply_changes: bool = False) -> int:
    """重命名模型文件：<文件夹名(去评级)>[变体][_v版本][_副本序号]<后缀>。

    合并自 rename_model_files.py：dry-run 默认预览，--apply 才真正改名。
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


def _save_works_and_category(kb_path: Path, data: dict) -> None:
    """保存 character/*.json（合并格式）+ 更新根 README 模型分类区块（不落盘 category_map.json）。"""
    save_kb_json(kb_path, data)
    cat_map = build_category_map(data)
    print(f"已保存作品知识库: {kb_path / 'character'}")
    total = sum(len(v) for v in cat_map.values())
    print(f"分类（从 character/*.json 现算）: {total} 个作品分布在 {len(cat_map)} 个大类")
    changed, action = update_readme_works_section(REPO_ROOT / "README.md", data)
    if changed:
        print(f"根 README 模型分类区块已{action}")


def add_work_interactive(kb_path: Path) -> int:
    """交互式添加新作品（character/*.json 权威源，自动重建分类与 README 区块）。"""
    data = load_kb_json(kb_path)
    works = data.setdefault("works", {})
    print("交互式添加新作品：逐项输入，回车跳过；输入 q 结束。")
    print(f"大类: {', '.join(CATEGORIES)}")
    added = 0
    while True:
        print("-" * 40)
        key = ask("作品键 (必填，唯一，如 BA/AK/OC): ")
        if key.lower() in ("q", "quit"):
            break
        key = key.strip()
        if not key:
            print("作品键不能为空，本条跳过。")
            continue
        if key in works:
            print(f"作品 '{key}' 已存在，跳过（添加角色请用 --add）。")
            continue
        en = ask("英文名 (逗号分隔，至少一个): ")
        if en.lower() in ("q", "quit"):
            break
        en_list = [x.strip() for x in en.split(",") if x.strip()]
        if not en_list:
            print("英文名至少填一个，本条跳过。")
            continue
        cn = ask("中文名 (逗号分隔，可空): ")
        if cn.lower() in ("q", "quit"):
            break
        cn_list = [x.strip() for x in cn.split(",") if x.strip()]
        ja = ask("日文名 (逗号分隔，可空): ")
        if ja.lower() in ("q", "quit"):
            break
        ja_list = [x.strip() for x in ja.split(",") if x.strip()]
        cat = ask(f"大类 ({'/'.join(CATEGORIES)}，默认 Other): ")
        if cat.lower() in ("q", "quit"):
            break
        cat = cat.strip().capitalize() if cat.strip() else "Other"
        if cat not in CATEGORIES:
            print(f"未知大类 '{cat}'，本条跳过。")
            continue
        entry: dict = {"en": en_list}
        if cn_list:
            entry["zh"] = cn_list
        if ja_list:
            entry["ja"] = ja_list
        entry["category"] = cat
        works[key] = entry
        save_kb_json(kb_path, data)  # 每条约保存（防中断丢失）
        added += 1
        print(f"已添加作品: {key} | {', '.join(en_list)} | {cat}")
    if added:
        _save_works_and_category(kb_path, data)
    print(f"共添加 {added} 个作品。")
    return 0


def _pick_default_name(field_label: str, current, ask_fn) -> tuple[list | None, str | None]:
    """交互选择/输入默认名：展示已有名称（编号）供选择，或输入新名称。

    返回 (新数组, 选中的名称)；跳过（Enter）返回 (原数组, None)；取消（q）返回 (None, None)。
    新输入的名称加入数组并设为默认名（首项），原名称自动降为别名。
    """
    names = [n for n in (current if isinstance(current, list) else [current]) if n]
    if names:
        print(f"  当前 {field_label}（数组首项=默认名）: {' / '.join(names)}")
        for i, n in enumerate(names, 1):
            print(f"    [{i}] {n}")
    else:
        print(f"  当前 {field_label}（空）")
    val = ask_fn(f"  选编号=设为默认名，或输入新{field_label}（将加入数组并设为默认名；"
                 f"Enter=不改，q=退出）: ").strip()
    if val.lower() in ("q", "quit"):
        return None, None
    if val.isdigit() and names and 1 <= int(val) <= len(names):
        chosen = names[int(val) - 1]
    elif val:
        chosen = val
    else:
        return names, None
    new_names = [chosen] + [n for n in names if n != chosen]
    return new_names, chosen


def set_default_role_cmd(kb_path: Path) -> int:
    """交互式设定角色默认中英文名：搜索角色 -> 选择 -> 选已有名称或添加新名称。

    默认名 = cn/en 数组首项；改后重命名自动把该角色统一为默认名
    （由 resolve_name 的"标准化"实现，如 Chuyin -> Miku）。
    新输入的名称会加入数组（成为该角色名称之一），原名称自动降为别名。
    """
    data = load_kb_json(kb_path)
    roles = data.get("roles") or []
    if not roles:
        print("知识库为空，请先使用 --roles / --add 添加角色。")
        return 0
    print("设定角色默认名：搜索角色 -> 选择 -> 选已有名称或输入新名称（新名称自动加入别名）。")
    while True:
        print("-" * 50)
        kw = ask("搜索角色（中文/英文/作品关键词，q=退出）: ")
        if kw.lower() in ("q", "quit"):
            break
        if not kw:
            print("请输入搜索关键词。")
            continue
        hits = [r for r in roles
                if kw.lower() in str(r.get("zh", "")).lower()
                or kw.lower() in str(r.get("en", "")).lower()
                or kw.lower() in str(r.get("work", "")).lower()]
        if not hits:
            print("未找到匹配条目。")
            continue
        print(f"命中 {len(hits)} 条：")
        for i, r in enumerate(hits, 1):
            cn_s = " / ".join(r.get("zh") or []) or "-"
            en_s = " / ".join(r.get("en") or []) or "-"
            print(f"  [{i}] {r.get('work', ''):<12} | cn: {cn_s} | en: {en_s}")
        sel = ask("选择编号（Enter=跳过）: ")
        if sel.lower() in ("q", "quit"):
            break
        if not sel.isdigit() or not (1 <= int(sel) <= len(hits)):
            print("编号无效，跳过。")
            continue
        r = hits[int(sel) - 1]
        new_cn, cn_chosen = _pick_default_name("中文名", r.get("zh") or [], ask)
        if new_cn is None:
            break
        new_en, en_chosen = _pick_default_name("英文名", r.get("en") or [], ask)
        if new_en is None:
            break
        if cn_chosen is None and en_chosen is None:
            print("中文名和英文名都未修改，本条跳过。")
            continue
        r["zh"] = new_cn
        r["en"] = new_en
        save_kb_json(kb_path, data)
        print(f"已设定默认名: {r.get('work')} | cn 默认={cn_chosen or '不变'}"
              f" | en 默认={en_chosen or '不变'}"
              f"（数组: {r.get('zh')} / {r.get('en')}）")
    print("提示：默认名是 cn/en 数组首项，重命名会把这些角色统一为默认名。")
    return 0


def rename_work_cmd(kb_path: Path, old_key: str, new_key: str,
                    apply_changes: bool = False) -> int:
    """安全重命名作品键：old_key -> new_key，联动更新文件、键、角色 work、皮肤表键。

    默认 dry-run 只预览；加 --apply 才真正写盘。merge_skips 中的旧记录
    会自然失效并被 prune 清理（不迁移，避免误替换名称里的同文字段）。
    """
    old_key = old_key.strip()
    new_key = new_key.strip()
    if old_key == new_key:
        print("旧键与新键相同，无需修改。")
        return 0
    data = load_kb_json(kb_path)
    works = data.get("works") or {}
    roles = data.get("roles") or []
    if old_key not in works:
        print(f"错误: 作品键 {old_key!r} 不存在于知识库。")
        return 1
    if new_key in works:
        print(f"错误: 目标作品键 {new_key!r} 已存在，无法重命名（请先处理冲突）。")
        return 1
    role_hits = [r for r in roles if str(r.get("work", "")) == old_key]
    skin_tags = load_skin_tags()
    skin_hit = old_key in skin_tags
    print(f"[{'执行' if apply_changes else '预览'}] 重命名作品键: {old_key} -> {new_key}")
    print(f"  - 文件: {_safe_name(old_key)}.json -> {_safe_name(new_key)}.json")
    print(f"  - 作品元数据: 1 个")
    print(f"  - 角色: {len(role_hits)} 个（work 同步）")
    print(f"  - 皮肤表键: {'有（迁移到新键）' if skin_hit else '无'}")
    print(f"  - merge_skips: 不迁移（旧记录自然失效并清理）")
    if not apply_changes:
        print("dry-run 预览：未写盘。确认无误请加 --apply 执行。")
        return 0
    works[new_key] = works.pop(old_key)
    for r in roles:
        if str(r.get("work", "")) == old_key:
            r["work"] = new_key
    if skin_hit:
        skin_tags[new_key] = skin_tags.pop(old_key)
        save_skin_tags(skin_tags)
    save_kb_json(kb_path, data)
    print(f"已完成重命名作品键: {old_key} -> {new_key}")
    return 0


def _pick_object(ask_fn, op_label: str) -> str | None:
    """不带对象参数时交互询问处理对象；返回 'role'/'work'/None(取消)。"""
    ans = ask_fn(f"{op_label}对象：1) 角色  2) 作品（Enter=取消, q=退出）: ").strip()
    if ans.lower() in ("q", "quit"):
        return None
    if ans == "1" or ans.lower() in ("role", "r"):
        return "role"
    if ans == "2" or ans.lower() in ("work", "w"):
        return "work"
    print("无效选择，取消。")
    return None


def rename_work_interactive(kb_path: Path, apply_changes: bool = False) -> int:
    """交互式重命名作品键：列出作品 -> 选旧键 -> 输入新键 -> 走 rename_work_cmd。"""
    data = load_kb_json(kb_path)
    works = data.get("works") or {}
    if not works:
        print("知识库暂无作品。")
        return 1
    print("重命名作品键：选择要改名的作品，再输入新键。")
    items = sorted(works.items())
    counts = {}
    for r in (data.get("roles") or []):
        counts[str(r.get("work", ""))] = counts.get(str(r.get("work", "")), 0) + 1
    for i, (wk, meta) in enumerate(items, 1):
        en_s = " / ".join(meta.get("en") or []) or "-"
        print(f"  [{i}] {wk:<16} | {en_s} | 角色 {counts.get(wk, 0)}")
    sel = ask("选择要重命名的作品编号（Enter=取消, q=退出）: ").strip()
    if sel.lower() in ("q", "quit") or not sel.isdigit() or not (1 <= int(sel) <= len(items)):
        print("已取消。")
        return 0
    old_key = items[int(sel) - 1][0]
    new_key = ask(f"新作品键（当前 {old_key!r}，Enter=取消, q=退出）: ").strip()
    if not new_key or new_key.lower() in ("q", "quit"):
        print("已取消。")
        return 0
    return rename_work_cmd(kb_path, old_key, new_key, apply_changes=apply_changes)


def run_kb_op(kb_path: Path, op: str, obj: str, args) -> int:
    """按 (操作, 对象) 分派到具体命令函数；返回退出码。

    op 为 add/del/list/check/merge/set-default/rename/suggest；obj 为 role/work。
    """
    if op == "add":
        if obj == "role":
            add_manual_entries(kb_path)
        else:
            add_work_interactive(kb_path)
        return 0
    if op == "del":
        if obj == "role":
            del_entries(kb_path)
        else:
            del_works_cmd(kb_path)
        return 0
    if op == "list":
        if obj == "role":
            list_db(kb_path)
        else:
            list_works_cmd(kb_path)
        return 0
    if op == "check":
        if obj == "role":
            run_check(kb_path)
        else:
            check_works_cmd(kb_path)
        return 0
    if op == "merge":
        if obj == "role":
            run_merge(kb_path)
        else:
            merge_works_cmd(kb_path)
        return 0
    if op == "set-default":
        if obj == "role":
            set_default_role_cmd(kb_path)
        else:
            set_default_work_cmd(kb_path)
        return 0
    if op == "rename":
        if obj != "work":
            print("--rename 仅支持作品（角色改名请用 --set-default --role）。",
                  file=sys.stderr)
            return 1
        if args.rename_work:
            old_key, new_key = args.rename_work
            return rename_work_cmd(kb_path, old_key, new_key,
                                   apply_changes=args.apply)
        return rename_work_interactive(kb_path, apply_changes=args.apply)
    if op == "suggest":
        run_suggest(kb_path)
        return 0
    print(f"未知操作: {op}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# 主流程（重命名 + 知识库维护 + 交互学习；统一入口）
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    g_run = parser.add_argument_group("预览与重命名")
    g_run.add_argument("--path", metavar="DIR", default=None,
                       help="只处理单个根目录（默认 Models + Other-YSM-Models）")
    g_run.add_argument("--apply", action="store_true",
                       help="真正执行重命名（默认 dry-run 预览）")
    g_run.add_argument("--learn", action="store_true",
                       help="交互学习：逐项询问 Unknown 文件夹的作品缩写并收录数据库（可配合 --apply 收录后重命名）")
    g_run.add_argument("--skip-conflict", action="store_true",
                       help="跨作品同名冲突（skip·conflict）时不询问归属、跳过不处理（保持原文件夹名）")
    g_run.add_argument("--rename-files", action="store_true",
                       help="重命名模型文件（目标用 --path，默认 Models/；合并自 rename_model_files.py）")
    g_run.add_argument("--kb", metavar="DIR", default=str(KB_DEFAULT),
                       help=f"对照数据库目录（默认 {KB_DEFAULT}）")
    g_run.add_argument("--report", metavar="FILE", default="",
                       help="报告输出路径（默认写入系统临时目录）")

    g_obj = parser.add_argument_group("对象选择（与知识库维护操作组合；不带则交互询问）")
    g_obj.add_argument("--role", action="store_true", help="对象=角色")
    g_obj.add_argument("--work", action="store_true", help="对象=作品")

    g_db = parser.add_argument_group("知识库维护（操作 × 对象；快捷名保留兼容）")
    g_db.add_argument("--roles", action="store_true",
                      help="角色综合菜单：增删改查 + 皮肤/别名（推荐入口）")
    g_db.add_argument("--add", action="store_true", help="添加（角色/作品；不带对象则询问）")
    g_db.add_argument("--del", action="store_true", dest="delete", help="删除（角色/作品）")
    g_db.add_argument("--check", action="store_true", help="检查（角色/作品）")
    g_db.add_argument("--suggest", action="store_true", help="疑似匹配建议（仅角色）")
    g_db.add_argument("--merge", action="store_true", help="合并（角色/作品）")
    g_db.add_argument("--list", action="store_true", help="列出（角色/作品）")
    g_db.add_argument("--set-default", action="store_true", dest="set_default",
                      help="设定默认名（角色=cn/en 首项；作品=en/cn/ja 首项）")
    g_db.add_argument("--rename", action="store_true", dest="rename",
                      help="重命名键（仅作品；角色改名请用 --set-default --role）")
    g_db.add_argument("--add-work", action="store_true", dest="add_work",
                      help="[快捷] 添加作品（= --add --work）")
    g_db.add_argument("--set-default-role", action="store_true", dest="set_default_role",
                      help="[快捷] 设定角色默认名（= --set-default --role）")
    g_db.add_argument("--rename-work", nargs=2, metavar=("OLD_KEY", "NEW_KEY"), default=None,
                      help="[快捷] 重命名作品键（= --rename --work，直接给新旧键）")

    g_show = parser.add_argument_group("预览显示过滤")
    g_show.add_argument("--show", metavar="STATUS[,STATUS...]", action="append", default=None,
                        help="精确指定显示哪些状态的条目，可多次或逗号分隔"
                        "（ok/fix/skip）；指定后不再自动包含 fix")
    g_show.add_argument("--show-kb", action="store_true", help="显示知识库补全修复条目（fix）")
    g_show.add_argument("--show-fix", action="store_true", help="显示已修改条目（fix）")
    g_show.add_argument("--show-skip", action="store_true", help="显示跳过条目（skip，含问题）")
    g_show.add_argument("--show-ok", action="store_true", help="显示已规范条目（ok）")
    g_show.add_argument("--show-all", action="store_true",
                        help="显示全部条目（等价于 --show ok,fix,skip）")
    args = parser.parse_args()

    kb_path = Path(args.kb)
    if not kb_path.is_absolute():
        kb_path = REPO_ROOT / kb_path

    # 文件重命名（合并自 rename_model_files.py）：--rename-files [--path PATH] [--apply]
    if args.rename_files:
        path = Path(args.path) if args.path else (REPO_ROOT / "Models")
        return rename_files_cmd(path, apply_changes=args.apply)

    # 知识库维护命令（操作 × 对象；快捷名归一为通用操作 + 对象）
    if args.roles:
        roles_cmd(kb_path)
        return 0
    # 快捷别名归一：对象固定的参数 -> 通用操作 + 对象
    if args.add_work:
        args.add = True
        args.work = True
    if args.set_default_role:
        args.set_default = True
        args.role = True
    if args.rename_work:
        args.rename = True
        args.work = True
    op = None
    if args.add:
        op = "add"
    elif args.delete:
        op = "del"
    elif args.check:
        op = "check"
    elif args.suggest:
        op = "suggest"
    elif args.merge:
        op = "merge"
    elif args.list:
        op = "list"
    elif args.set_default:
        op = "set-default"
    elif args.rename:
        op = "rename"
    if op is not None:
        if args.role and args.work:
            print("错误: --role 与 --work 不能同时使用。", file=sys.stderr)
            return 2
        obj = "role" if args.role else ("work" if args.work else None)
        if obj is None and op != "suggest":
            # suggest 仅角色，免询问；其余不带对象时交互询问
            obj = _pick_object(ask, op)
            if obj is None:
                return 0
        return run_kb_op(kb_path, op, obj or "role", args)

    dirs = get_target_dirs(args.path)
    if not dirs:
        print("未找到任何目标文件夹。", file=sys.stderr)
        return 2
    print(f"共找到 {len(dirs)} 个待处理文件夹（--path 限定范围）")

    # 变体表（variant_tags.json）的变体词自动并入皮肤表 common：
    # 避免如 VOC_初音_兔子洞 因皮肤未识别、残留在 cn 里而被标准化覆盖丢失。
    sync_variant_to_skin_tags()

    # 候选皮肤自动收录：解析时识别出"角色名 + 未知中文段"结构的皮肤词
    # （如 泠鸢_登门喜鹊 的「登门喜鹊」，前提 泠鸢 是 OC 已收录角色），
    # 自动加入 skin_tags.json 对应作品（幂等，下次运行即识别为皮肤）。
    def collect_candidate_skins() -> None:
        skin_tags = load_skin_tags()
        added = 0
        for r in results:
            for s in (r.get("candidate_skins") or []):
                if add_skin_tag(skin_tags, r.get("work") or "", s):
                    added += 1
        if added:
            save_skin_tags(skin_tags)
            print(f"已自动收录 {added} 个候选皮肤到 skin_tags.json（角色名后的未知中文段）")

    data = load_kb_json(kb_path)
    if not data.get("roles"):
        # 首次：从旧 SQLite 库迁移历史条目（旧 alias 已并入 roles，忽略第二返回值）
        m, _ = migrate_from_sqlite(kb_path, kb_path / "ysm_kb.db" if kb_path.is_dir()
                                   else kb_path.with_suffix(".db"))
        if m:
            data["roles"] = list(m)

    # works 以 character/*.json 为权威源（不再从 README.md 同步）
    build_work_index(data)

    roles = list(data.get("roles") or [])
    print(f"知识库: {len(roles)} 条")

    cn_idx, en_idx, en_to_cn, cn_to_en = build_indexes(roles)

    results = []
    for d in dirs:
        res = resolve_name(d.name, cn_idx, en_idx, en_to_cn, cn_to_en)
        res["path"] = d
        results.append(res)

    # 候选皮肤自动收录（角色名后的未知中文段识别为皮肤，幂等写入 skin_tags.json）
    collect_candidate_skins()

    # 磁盘上已有的 -数字 副本文件夹（同名冲突自动生成，如 xxx-1_LB）不再参与重命名：
    # 识别副本后缀并标 SKIP，避免每次 --apply 都尝试去重并报"已是唯一副本，保持"。
    # 副本模式 = 结尾 `-数字`（评级可选），且 new 已去掉该副本号。
    _copy_suffix_re = re.compile(r'-\d+(?:_(?:LA|LB|LC|LD))?$', re.IGNORECASE)
    for r in results:
        if r["status"] == "SKIP":
            continue
        if _copy_suffix_re.search(r["original"]) and not _copy_suffix_re.search(r["new"]):
            r["status"] = "SKIP"
            r["notes"] = "已有副本后缀(-N)，跳过"

    # 报告（分类体系 2026-08-15：3 主状态 + 问题级计数）
    #   ok    已规范：无任何问题、无改动
    #   fix   已修改：本次有改动（补全/标准化/别名归一/格式修正）；若有遗留问题一并显示
    #   skip  跳过：除 ok 外未改动的条目（副本/空名/纯数字，或有遗留问题但未改名），
    #         预览时显示其对应问题
    ALL_TAGS = ("ok", "fix", "skip")
    TAG_LABELS = {"ok": "已规范", "fix": "已修改", "skip": "跳过"}
    # 问题级计数：统计非 ok 条目（fix 遗留 + skip 未处理）的问题，每类单独计数。
    PROBLEM_ORDER = ("conflict", "works", "cn-name", "en-name", "other")
    PROBLEM_LABELS = {"works": "缺作品", "cn-name": "缺中文名", "en-name": "缺英文名",
                      "conflict": "跨作品同名", "other": "其他歧义"}
    counts = {t: 0 for t in ALL_TAGS}
    problem_counts = {p: 0 for p in PROBLEM_ORDER}

    def classify(r: dict) -> tuple[str, list[str]]:
        """按改动与否分类：返回 (主状态, 问题列表)。

        主状态 3 类：
          ok    无问题、无改动（已规范）；
          fix   本次有改动（new != original）-> 显示修改内容，遗留问题一并显示；
          skip  除 ok 外未改动的条目（副本/空名/纯数字，或有遗留问题但未改名），
                预览时显示其对应问题。
        """
        if r["status"] == "SKIP":
            return "skip", []
        probs = list(r.get("problems") or [])
        if r["new"] != r["original"]:
            # 本次有改动：无论有无遗留问题都显示（说明修改了什么）
            return "fix", probs
        if probs:
            # 未改动但有遗留问题 -> 跳过（预览时显示问题）
            return "skip", probs
        return "ok", []

    def fix_note(r: dict) -> str:
        """fix 条目修复了什么（用于分组显示）：知识库补全 / 别名归一 / 格式修正。"""
        notes = r.get("notes") or ""
        if r.get("filled"):
            return "知识库补全"
        if "work alias normalized" in notes:
            return "别名归一"
        return "格式修正"

    # 显示过滤：默认只显示"已修改"(fix) 的条目；--show/--show-* 精确指定，--show-all 全显示
    if args.show_all:
        visible = set(ALL_TAGS)
    else:
        # 默认只显示已修改；指定任一 --show/--show-* 即精确指定（不含默认 fix）
        explicit = bool(args.show or args.show_kb or args.show_fix
                        or args.show_skip or args.show_ok)
        visible = set() if explicit else {"fix"}
        for s in (args.show or []):
            for part in s.split(","):
                part = part.strip().lower()
                if part in ALL_TAGS:
                    visible.add(part)
        if args.show_kb or args.show_fix:
            visible.add("fix")
        if args.show_skip:
            visible.add("skip")
        if args.show_ok:
            visible.add("ok")

    grouped: dict[str, list[str]] = {t: [] for t in ALL_TAGS}
    problem_groups: dict[str, list[str]] = {}  # 仅 skip，按问题类型分组（预览时可见问题）
    fix_groups: dict[str, list[str]] = {}      # 仅 fix，按修复类型分组
    for r in results:
        rel = r["path"].relative_to(REPO_ROOT).as_posix()
        tag, probs = classify(r)
        counts[tag] += 1
        # 问题计数：统计非 ok 条目的问题（fix 遗留 + skip 未处理）
        if tag != "ok":
            for p in probs:
                if p in problem_counts:
                    problem_counts[p] += 1
        # 行内容：跳过条目显示"跳过 + 问题"；其余显示修改结果
        if tag == "skip":
            line = f"[{tag}] {rel}  (跳过"
            if r["notes"]:
                line += " -- " + r["notes"]
            if probs:
                prob_str = ", ".join(PROBLEM_LABELS.get(p, p) for p in probs)
                line += f" -- 问题: {prob_str}"
            line += ")"
        else:
            line = f"[{tag}] {rel}  =>  {r['new']}"
            if r["notes"]:
                line += "   <-- " + r["notes"]
            if r.get("filled"):
                line += "   [补全: " + r["filled"] + "]"
            if probs:
                prob_str = ", ".join(PROBLEM_LABELS.get(p, p) for p in probs)
                line += f"   [遗留问题: {prob_str}]"
        if tag in visible:
            grouped[tag].append(line)
            if tag == "skip":
                # 跳过条目按问题类型分组（一条目多问题：每个问题都归到对应分组，
                # 如 同时含 other + en-name -> 两个分组都显示）
                for p in probs:
                    if p in problem_groups or p in PROBLEM_LABELS:
                        problem_groups.setdefault(p, []).append(line)
            elif tag == "fix":
                # fix 按"修复了什么"分组（知识库补全 / 别名归一 / 格式修正）
                fix_groups.setdefault(fix_note(r), []).append(line)

    report_lines: list[str] = []
    for t in ALL_TAGS:
        if t == "fix" and fix_groups and "fix" in visible:
            # fix 按修复类型显示（数量多的在前），说明修复了什么
            for kind in sorted(fix_groups, key=lambda k: -len(fix_groups[k])):
                lines = fix_groups[kind]
                head = f"== fix · {kind}（{len(lines)} 条） =="
                print(head)
                report_lines.append(head)
                for line in lines:
                    print(line)
                    report_lines.append(line)
            continue
        if t == "skip" and problem_groups and "skip" in visible:
            # skip 按问题类型显示（数量多的在前），预览时可见对应问题
            for prob in sorted(problem_groups, key=lambda k: -len(problem_groups[k])):
                lines = problem_groups[prob]
                head = f"== skip · {PROBLEM_LABELS.get(prob, prob)}（{len(lines)} 条） =="
                print(head)
                report_lines.append(head)
                for line in lines:
                    print(line)
                    report_lines.append(line)
            continue
        lines = grouped[t]
        if not lines or t not in visible:
            continue
        if len(visible) > 1:
            head = f"== {t} {TAG_LABELS[t]}（{len(lines)} 条） =="
            print(head)
            report_lines.append(head)
        for line in lines:
            print(line)
            report_lines.append(line)

    print()
    print(f"汇总: ok={counts['ok']}  已修改={counts['fix']}  跳过={counts['skip']}")
    if any(problem_counts.values()):
        prob_str = "  ".join(f"{PROBLEM_LABELS[p]}={problem_counts[p]}"
                             for p in PROBLEM_ORDER if problem_counts[p])
        print(f"问题计数: {prob_str}")

    if args.report:
        report_path = Path(args.report)
    else:
        import tempfile
        from datetime import datetime
        report_path = Path(tempfile.gettempdir()) / (
            f"ysm-rename-report-{datetime.now():%Y%m%d-%H%M%S}.txt")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    label = "完整报告" if args.show_all else "报告(当前过滤)"
    print(f"{label}: {report_path}（{len(report_lines)} 行）")

    # 交互学习（--learn 独立触发，可配合 --apply 收录后重命名）：未收录（Unknown）且
    # 有可辨识角色名的文件夹，逐项询问"作品缩写"，确认后收录进数据库（角色表 + 皮肤表）。
    if args.learn:
        pending = [r for r in results
                   if r["status"] != "SKIP" and r["work"] == "Unknown"
                   and (r["zh"] or r["en"])]
        additions: list[dict] = []
        if pending:
            print(f"发现 {len(pending)} 个未收录条目（询问是否加入数据库）：")
            for i, r in enumerate(pending, 1):
                rel = r["path"].relative_to(REPO_ROOT).as_posix()
                role = r["zh"] or r["en"]
                print(f"  [{i}/{len(pending)}] {rel}  角色: {role}")
                cand = r.get("conflict_works") or []
                if cand:
                    opts = "  ".join(f"{j}={w}" for j, w in enumerate(cand))
                    print(f"    同名角色存在于多个作品: {opts}")
                    work = ask("    选择编号或输入作品缩写（Enter=跳过, q=退出）: ").strip()
                else:
                    work = ask("    作品缩写（如 BA/GF2；Enter=跳过不收录, q=退出）: ").strip()
                if work.lower() in ("q", "quit"):
                    break
                if not work:
                    continue
                # 编号选择 -> 对应的候选作品（C：为该文件夹补上作品前缀）
                if work.isdigit() and cand:
                    idx = int(work)
                    if 0 <= idx < len(cand):
                        work = cand[idx]
                    else:
                        print("    编号无效，跳过")
                        continue
                additions.append({"work": work.upper(),
                                  "zh": [r["zh"]] if r["zh"] else [],
                                  "en": [r["en"]] if r["en"] else [],
                                  "cn_skin": r.get("cn_skin") or "",
                                  "en_skin": r.get("en_skin") or ""})
            if additions:
                added_entries: list[dict] = []
                skin_tags = load_skin_tags()
                for a in additions:
                    entry = {
                        "work": a["work"], "zh": a["zh"], "en": a["en"],
                    }
                    data.setdefault("roles", []).append(entry)
                    added_entries.append(entry)
                    # 皮肤写入 skin_tags.json 对应作品（角色条目不再存 skin 键）
                    if a.get("cn_skin") or a.get("en_skin"):
                        add_skin_tag(skin_tags, a["work"],
                                     a.get("cn_skin") or "", a.get("en_skin") or "")
                save_kb_json(kb_path, data)
                save_skin_tags(skin_tags)
                print(f"已收录 {len(additions)} 条到数据库: {kb_path}")
                # 重建索引并重新解析（新收录条目参与匹配；刚收录条目强制单作品归属，
                # 解决跨作品同名歧义）
                build_work_index(data)
                roles = list(data.get("roles") or [])
                cn_idx, en_idx, en_to_cn, cn_to_en = build_indexes(
                    roles, priority_roles=added_entries)
                pending_paths = {p["path"] for p in pending}
                for r in results:
                    if r["path"] in pending_paths:
                        res = resolve_name(r["path"].name, cn_idx, en_idx,
                                           en_to_cn, cn_to_en)
                        r.update(res)

    if args.apply:
        # 跨作品同名冲突（skip-kb）：--apply 时逐项询问归属作品（选择后收录数据库
        # 并重新解析，补上作品前缀重命名）；--skip-conflict 则跳过选择、不处理。
        # 未选择归属的冲突条目保持原文件夹名（标 SKIP，避免误写 Unknown_ 前缀）。
        if not args.skip_conflict:
            conflicts = [r for r in results
                         if r["status"] != "SKIP" and r.get("conflict")
                         and (r["zh"] or r["en"])]
            if conflicts:
                print(f"发现 {len(conflicts)} 个跨作品同名条目（选择归属作品，Enter=跳过不处理）：")
                additions: list[dict] = []
                for i, r in enumerate(conflicts, 1):
                    rel = r["path"].relative_to(REPO_ROOT).as_posix()
                    role = r["zh"] or r["en"]
                    cand = r.get("conflict_works") or []
                    print(f"  [{i}/{len(conflicts)}] {rel}  角色: {role}")
                    opts = "  ".join(f"{j}={w}" for j, w in enumerate(cand))
                    print(f"    同名角色存在于多个作品: {opts}")
                    work = ask("    选择编号或输入作品缩写（Enter=跳过不处理, q=退出）: ").strip()
                    if work.lower() in ("q", "quit"):
                        break
                    if not work:
                        continue
                    if work.isdigit() and cand:
                        idx = int(work)
                        if 0 <= idx < len(cand):
                            work = cand[idx]
                        else:
                            print("    编号无效，跳过")
                            continue
                    additions.append({"work": work.upper(),
                                      "zh": [r["zh"]] if r["zh"] else [],
                                      "en": [r["en"]] if r["en"] else []})
                if additions:
                    added_entries: list[dict] = []
                    for a in additions:
                        entry = {"work": a["work"], "zh": a["zh"], "en": a["en"]}
                        data.setdefault("roles", []).append(entry)
                        added_entries.append(entry)
                    save_kb_json(kb_path, data)
                    print(f"已收录 {len(added_entries)} 个冲突归属到数据库: {kb_path}")
                    build_work_index(data)
                    roles = list(data.get("roles") or [])
                    cn_idx, en_idx, en_to_cn, cn_to_en = build_indexes(
                        roles, priority_roles=added_entries)
                    conflict_paths = {p["path"] for p in conflicts}
                    for r in results:
                        if r["path"] in conflict_paths:
                            res = resolve_name(r["path"].name, cn_idx, en_idx,
                                               en_to_cn, cn_to_en)
                            r.update(res)
        # 仍未解决归属的冲突条目（--skip-conflict 或用户跳过）：标 SKIP，不重命名
        unresolved = [r for r in results
                      if r["status"] != "SKIP" and r.get("conflict")]
        if unresolved:
            if args.skip_conflict:
                print(f"--skip-conflict: 跳过 {len(unresolved)} 个跨作品同名冲突条目，不处理")
            for r in unresolved:
                r["status"] = "SKIP"
                r["notes"] = "跨作品同名冲突未选择，跳过"

        done = failed = skipped = 0
        for r in results:
            if r["status"] == "SKIP" or r["new"] == r["original"]:
                continue
            target = r["path"].with_name(r["new"])
            # Windows 大小写不敏感：目标"已存在"可能是同一文件夹仅大小写不同
            # （如 Avemujica -> AveMujica），此时应执行大小写修正而非跳过。
            same_case_insensitive = (target.name != r["path"].name
                                     and os.path.normcase(str(target))
                                     == os.path.normcase(str(r["path"])))
            if target.exists() and not same_case_insensitive:
                # 目标已存在：不跳过，加 -数字 后缀唯一化（副本序号放在评级前，
                # 如 VOC_初音_Miku_LA 冲突 -> VOC_初音_Miku-1_LA）。
                # 当前名已是 -数字 副本（candidate 即自身）时保持不动，避免无限递增。
                m_grade = re.search(r"_(LA|LB|LC|LD)$", r["new"])
                base_new = r["new"][:m_grade.start()] if m_grade else r["new"]
                grade_sfx = m_grade.group(0) if m_grade else ""
                renamed_to: Path | None = None
                n = 1
                while True:
                    cand = r["path"].with_name(f"{base_new}-{n}{grade_sfx}")
                    if cand == r["path"]:
                        break
                    if not cand.exists():
                        renamed_to = cand
                        break
                    n += 1
                if renamed_to is None:
                    # 已是最小副本（candidate 即自身），无需改名
                    skipped += 1
                    print(f"[warn] 已是唯一副本，保持: {r['path'].name}"
                          f"（目标 {r['new']} 冲突）", file=sys.stderr)
                    continue
                target = renamed_to
                print(f"[副本] 目标 {r['new']} 已存在，重命名为: {target.name}")
            try:
                if same_case_insensitive:
                    # 仅大小写修正：先改到临时名再改到目标（避免 Windows 同名冲突）
                    tmp = r["path"].with_name(r["path"].name + ".casefix_tmp")
                    os.rename(r["path"], tmp)
                    os.rename(tmp, target)
                else:
                    os.rename(r["path"], target)
                done += 1
            except OSError as e:
                failed += 1
                print(f"[warn] 重命名失败: {r['original']} -> {r['new']}: {e}", file=sys.stderr)
        print(f"已执行: 重命名 {done} 个，冲突跳过 {skipped} 个，失败 {failed} 个")
    else:
        print("dry-run 预览模式，未改动任何文件。加 --apply 执行重命名。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
