#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型文件夹批量重命名工具（本仓库专用）。

命名模板:
    <英文作品名>_<中文角色名>[-中文皮肤]_<英文角色名>[-英文皮肤]_<评定等级>
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
  3. 中文皮肤（-太刀、-泳装、-原皮、-万圣节…）完整保留。
  4. 作品名前缀统一为规范缩写（含作品全称自动转缩写，如 Azur Lane -> AL）；
     无前缀时用对照数据库反查角色
     （.github/data/knowledge/：works.json + aliases.json + roles/<作品>.json，
     可直接用编辑器改；知识库由 kb_tool.py 统一维护）。
     唯一命中才填作品名，否则 Unknown；多候选冲突也标 Unknown 并提示。
  5. 知识库中 source="manual" 的手工条目在重建时保留，且优先于自动条目。
     手工修改：直接编辑 .github/data/knowledge/ 下的 json 文件
     （roles/<作品>.json 等）。手改后无需任何命令，脚本下次运行即生效。

默认 dry-run 只预览；加 --apply 才真正重命名。

用法（按功能分组）:

  预览与重命名:
    python .github/scripts/naming/rename_model_folders.py              # 预览（默认只显示人工确认条目）
    python .github/scripts/naming/rename_model_folders.py --apply      # 执行重命名
    python .github/scripts/naming/rename_model_folders.py --path Models # 只处理单个根
    python .github/scripts/naming/rename_model_folders.py --no-sync    # 关闭 README works 同步

  知识库维护（由 kb_tool.py 提供）:
    python .github/scripts/naming/kb_tool.py --build-kb   # 重建并保存对照数据库
    python .github/scripts/naming/kb_tool.py --add        # 交互式添加手工对照条目
    python .github/scripts/naming/kb_tool.py --alias      # 登记别名/变体（大昔涟 -> 昔涟）
    python .github/scripts/naming/kb_tool.py --del        # 删除条目（搜索 -> 选 id）
    python .github/scripts/naming/kb_tool.py --check      # 数据质量检查
    python .github/scripts/naming/kb_tool.py --suggest    # 疑似匹配建议（确认后写别名）
    python .github/scripts/naming/kb_tool.py --merge      # 合并重复角色条目（交互确认）
    python .github/scripts/naming/kb_tool.py --list       # 查看数据库全部条目

  预览显示过滤（控制台与报告一致；默认只显示人工确认 MANUAL）:
    python .github/scripts/naming/rename_model_folders.py --show KB          # 只显示知识库补作品
    python .github/scripts/naming/rename_model_folders.py --show KB,FIX      # 只显示 KB 和 FIX
    python .github/scripts/naming/rename_model_folders.py --show-kb --show-fix   # 同上（快捷开关可组合）
    python .github/scripts/naming/rename_model_folders.py --show-all         # 显示全部条目

维护说明：
- 直接编辑 .github/data/knowledge/ 下的 json 文件即可增删改（手改即时生效）
- 也可以命令行：kb_tool.py --add 加角色 / --alias 加别名 / --del 删 / --list 看
- 数据库为多文件结构：works.json（作品表）、aliases.json（别名）、
  roles/<作品>.json（按作品分文件存放角色，避免单文件过大）
- source="manual" 的条目不会被 --build-kb 覆盖；auto 条目由文件夹自动重建
- 手改 auto 条目的别名（cn/en 数组）也会生效：运行时自动与实时构建条目合并；
  但注意 --build-kb 重建时 auto 条目以文件夹为准（合并别名会保留在 JSON 中）
- 角色条目的 cn/en 可以是字符串或数组：数组第一个为规范名（补全默认用它），
  其余为别名（如 "cn": ["昔涟", "大昔涟", "小昔涟"]）；改 auto 条目为数组时
  请把 source 改为 "manual" 以免被重建覆盖
- works 的值支持三种写法：平铺数组、空 []、按语言分类的对象
  （如 "AK": {"cn": ["明日方舟"], "en": ["Arknights", "Arknight"]}，
   cn/en/ja 等语言键可自由增删；分类对象在 --build-kb 时不会被覆盖）
- 每次运行自动从 README.md 同步 works（README 为作品名称权威源）：
  每行格式 "英文名[,别名...] | 中文名[,别名...] | 日文名"，
  英文名列表最后一项作为作品键（即作品默认缩写）；改 README 后重跑即生效，
  加 --no-sync 可关闭同步
- 角色条目自动合并别名（仅同一作品内）：同中文名不同英文名、或英文名有
  交集的昵称/别称，会合并成 cn/en 数组（如 阿米娅 amiya/amyia、
  后藤一里/波奇酱）；数组第一个为出现最多、最长的规范名；跨作品不合并。
  合并后的 auto 条目重建时自动重新合并，无需手工维护
- 别名/变体（别称、大小修饰、多英文名）也可放 aliases 数组，如 大昔涟 -> 昔涟
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from kb_tool import (
    KB_DEFAULT, REPO_ROOT,
    build_indexes, build_kb, build_work_index,
    get_target_dirs, load_kb_json, migrate_from_sqlite,
    resolve_name, role_key, sync_works_from_readme,
)

DEFAULT_ROOTS = [REPO_ROOT / "Models", REPO_ROOT / "Other-YSM-Models"]


# ---------------------------------------------------------------------------
# 主流程（重命名；知识库维护命令请用 kb_tool.py）
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    g_run = parser.add_argument_group("预览与重命名")
    g_run.add_argument("--path", metavar="DIR", default=None,
                       help="只处理单个根目录（默认 Models + Other-YSM-Models）")
    g_run.add_argument("--apply", action="store_true",
                       help="真正执行重命名（默认 dry-run 预览）")
    g_run.add_argument("--no-sync", action="store_true",
                       help="不从 README.md 同步 works（默认自动同步）")
    g_run.add_argument("--kb", metavar="DIR", default=str(KB_DEFAULT),
                       help=f"对照数据库目录（默认 {KB_DEFAULT}）")
    g_run.add_argument("--report", metavar="FILE", default="",
                       help="报告输出路径（默认写入系统临时目录）")

    g_db = parser.add_argument_group("知识库维护（快捷调用 kb_tool.py 同款命令）")
    g_db.add_argument("--build-kb", action="store_true", help="重建并保存对照数据库")
    g_db.add_argument("--add", action="store_true",
                      help="交互式添加手工对照条目（中文名/英文名/作品）")
    g_db.add_argument("--alias", action="store_true",
                      help="交互式登记别名/变体（大昔涟 -> 昔涟 等）")
    g_db.add_argument("--del", action="store_true", dest="delete",
                      help="交互式删除数据库条目（搜索 -> 选 id）")
    g_db.add_argument("--check", action="store_true",
                      help="数据质量检查（同名冲突、空字段、重复、别名悬空）")
    g_db.add_argument("--suggest", action="store_true",
                      help="疑似匹配建议：扫描 Unknown 文件夹，候选确认后写入别名")
    g_db.add_argument("--list", action="store_true", help="列出数据库中的全部条目")

    g_show = parser.add_argument_group("预览显示过滤")
    g_show.add_argument("--show", metavar="STATUS[,STATUS...]", action="append", default=None,
                        help="精确指定显示哪些状态的条目，可多次或逗号分隔"
                        "（OK/FIX/KB/UNK/MANUAL/SKIP）；指定后不再自动包含 MANUAL")
    g_show.add_argument("--show-kb", action="store_true", help="显示知识库补作品条目（KB）")
    g_show.add_argument("--show-fix", action="store_true", help="显示自动修正条目（FIX）")
    g_show.add_argument("--show-unk", action="store_true", help="显示标为 Unknown 的条目（UNK）")
    g_show.add_argument("--show-skip", action="store_true", help="显示跳过条目（SKIP）")
    g_show.add_argument("--show-ok", action="store_true", help="显示无变化条目（OK）")
    g_show.add_argument("--show-all", action="store_true",
                        help="显示全部条目（等价于 --show OK,FIX,KB,UNK,MANUAL,SKIP）")
    g_show.add_argument("--only-manual", action="store_true",
                        help="只显示人工确认条目（默认行为，保留兼容）")
    args = parser.parse_args()

    kb_path = Path(args.kb)
    if not kb_path.is_absolute():
        kb_path = REPO_ROOT / kb_path

    # 知识库维护命令直接复用 kb_tool.py 的实现（从 kb_tool import 的顶层函数）
    if args.add or args.alias or args.delete or args.check or args.suggest or args.list:
        from kb_tool import (add_alias_entries, add_manual_entries,
                             del_entries, list_db, run_check, run_suggest)
        if args.add:
            add_manual_entries(kb_path)
        elif args.alias:
            add_alias_entries(kb_path)
        elif args.delete:
            del_entries(kb_path)
        elif args.check:
            run_check(kb_path)
        elif args.suggest:
            run_suggest(kb_path)
        elif args.list:
            list_db(kb_path)
        return 0

    dirs = get_target_dirs(args.path)
    if not dirs:
        print("未找到任何目标文件夹。", file=sys.stderr)
        return 2
    # 知识库始终基于全仓库（不受 --path 影响），重命名目标才受范围限制
    kb_names = [d.name for d in get_target_dirs(None)]
    print(f"共找到 {len(dirs)} 个待处理文件夹（--path 限定范围）"
          f"，知识库基于全仓库 {len(kb_names)} 个文件夹")

    data = load_kb_json(kb_path)
    manual_roles = [r for r in (data.get("roles") or []) if r.get("source") == "manual"]
    if not data.get("roles") and not data.get("aliases"):
        # 首次：从旧 SQLite 库迁移手工条目
        m, a = migrate_from_sqlite(kb_path, kb_path / "ysm_kb.db" if kb_path.is_dir()
                                   else kb_path.with_suffix(".db"))
        manual_roles = m or manual_roles
        if a:
            data["aliases"] = a

    # 从 README 同步 works（README 为作品名称权威源，实时更新）
    if not args.no_sync:
        added, updated = sync_works_from_readme(data, REPO_ROOT / "README.md")
        if added or updated:
            print(f"已从 README.md 同步 works：新增 {added} 个，更新 {updated} 个")
    build_work_index(data)

    built_roles = build_kb(kb_names)
    roles = list(built_roles)
    seen = {role_key(r) for r in built_roles}
    # 合并 JSON 里 auto 条目的别名：手改 auto 条目（如给砂狼白子加"白子"别名）也生效。
    # 同 role_key 时把 json 的 cn/en 别名并入 built 条目；json 独有的过时条目忽略。
    for j in (data.get("roles") or []):
        if j.get("source") == "manual":
            continue
        k = role_key(j)
        if k not in seen:
            continue
        b = next(r for r in roles if role_key(r) == k)
        for f in ("cn", "en"):
            bv = b.get(f)
            b_list = bv if isinstance(bv, list) else ([bv] if bv else [])
            jv = j.get(f)
            j_list = jv if isinstance(jv, list) else ([jv] if jv else [])
            merged = list(b_list)
            for x in j_list:
                if x and x not in merged:
                    merged.append(x)
            b[f] = merged
    for m in manual_roles:
        key = role_key(m)
        if key in seen:
            # 手工条目优先：替换 built 中同 key 的条目（保留手工别名）
            roles = [r for r in roles if role_key(r) != key]
        else:
            seen.add(key)
        roles.append(m)
    print(f"知识库: 实时构建 {len(built_roles)} 条 + JSON 手工 {len(manual_roles)} 条"
          f" = {len(roles)} 条")

    if args.build_kb:
        from kb_tool import save_kb_json
        data["roles"] = roles
        # works 由 README.md 同步维护（sync_works_from_readme），无需内置于脚本播种
        save_kb_json(kb_path, data)
        print(f"对照数据库已保存: {kb_path}")

    cn_idx, en_idx, en_to_cn, cn_to_en = build_indexes(roles, manual_roles,
                                                       data.get("aliases") or [])

    results = []
    for d in dirs:
        res = resolve_name(d.name, cn_idx, en_idx, en_to_cn, cn_to_en)
        res["path"] = d
        results.append(res)

    # 报告
    counts = {"OK": 0, "FIX": 0, "KB": 0, "UNK": 0, "MANUAL": 0, "SKIP": 0}
    ALL_TAGS = ("OK", "FIX", "KB", "UNK", "MANUAL", "SKIP")
    # 显示过滤：默认只显示人工确认（MANUAL）；--show/--show-* 叠加，--show-all 全显示
    if args.show_all:
        visible = set(ALL_TAGS)
    elif args.only_manual:
        visible = {"MANUAL"}
    else:
        # 默认只显示人工确认；指定任一 --show/--show-* 即精确指定（不含默认 MANUAL）
        explicit = bool(args.show or args.show_kb or args.show_fix
                        or args.show_unk or args.show_skip or args.show_ok)
        visible = set() if explicit else {"MANUAL"}
        for s in (args.show or []):
            for part in s.split(","):
                part = part.strip().upper()
                if part in ALL_TAGS:
                    visible.add(part)
        if args.show_kb:
            visible.add("KB")
        if args.show_fix:
            visible.add("FIX")
        if args.show_unk:
            visible.add("UNK")
        if args.show_skip:
            visible.add("SKIP")
        if args.show_ok:
            visible.add("OK")
    # 按状态分组收集（多状态显示时分类输出，单状态不加组标题）
    TAG_LABELS = {"OK": "已规范", "FIX": "自动修正", "KB": "知识库补作品",
                  "UNK": "未识别 Unknown", "MANUAL": "人工确认", "SKIP": "跳过"}
    grouped: dict[str, list[str]] = {t: [] for t in ALL_TAGS}
    for r in results:
        rel = r["path"].relative_to(REPO_ROOT).as_posix()
        if r["status"] == "SKIP":
            tag = "SKIP"
        elif r["notes"]:
            tag = "MANUAL"
        elif r["work"] == "Unknown":
            tag = "UNK"
        elif r["work_source"] == "kb" and r["new"] != r["original"]:
            tag = "KB"
        elif r["status"] == "FIX":
            tag = "FIX"
        else:
            tag = "OK"
        counts[tag] += 1

        if r["status"] != "SKIP":
            line = f"[{tag}] {rel}  =>  {r['new']}"
            if r["notes"]:
                line += "   <-- " + r["notes"]
            if r.get("filled"):
                line += "   [补全: " + r["filled"] + "]"
        else:
            line = f"[{tag}] {rel}  (kept as-is"
            if r["notes"]:
                line += " -- " + r["notes"]
            line += ")"
        if tag in visible:
            grouped[tag].append(line)

    report_lines: list[str] = []
    for t in ALL_TAGS:
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
    print(f"汇总: OK={counts['OK']}  FIX={counts['FIX']}  KB补作品={counts['KB']}  "
          f"Unknown={counts['UNK']}  人工确认={counts['MANUAL']}  跳过={counts['SKIP']}")

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

    if args.apply:
        done = failed = skipped = 0
        for r in results:
            if r["status"] == "SKIP" or r["new"] == r["original"]:
                continue
            target = r["path"].with_name(r["new"])
            if target.exists():
                skipped += 1
                print(f"[warn] 目标已存在，跳过: {r['original']} -> {r['new']}", file=sys.stderr)
                continue
            try:
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
