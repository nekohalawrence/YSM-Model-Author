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
     可直接用编辑器改；知识库维护命令在 check&fix/kb_tool.py，实现位于 lib/kb/）。
     唯一命中才填作品名，否则 Unknown；多候选冲突也标 Unknown 并提示。
  5. 知识库为纯手工维护（无自动构建）：直接编辑 .github/data/model-info/ 下的
     character/<作品>.json；或用 check&fix/kb_tool.py（--roles/--add/--del 等）
     交互式增删改查。手改后无需任何命令，脚本下次运行即生效。
  6. 本脚本只负责重命名：Unknown / 跨作品同名冲突只标记跳过（保持原文件夹名、
     不收录数据库）；需要收录请先用 check&fix/kb_tool.py 手工维护。

默认 dry-run 只预览；加 --apply 才真正重命名。

用法（按功能分组）:

  预览与重命名（纯重命名，不收录数据库）:
    python '.github/scripts/models_organize/02_rename_model_folders.py'                        # 预览（默认 Models + Other-YSM-Models）
    python '.github/scripts/models_organize/02_rename_model_folders.py' --apply                # 执行重命名
    python '.github/scripts/models_organize/02_rename_model_folders.py' Models/0001 --apply    # 只处理某作者目录（直接引用路径，无需 --path）
    python '.github/scripts/models_organize/02_rename_model_folders.py' Models/0001/模型名      # 只处理单个模型目录

  Unknown / 跨作品同名冲突：只标记跳过（保持原文件夹名，不写数据库）；
  需要收录请先用 check&fix/kb_tool.py 维护（--add/--roles），再重跑本脚本。

  预览显示过滤（控制台与报告一致；默认只显示已修改 fix）:
    python '.github/scripts/models_organize/02_rename_model_folders.py' --show ok               # 只显示已规范
    python '.github/scripts/models_organize/02_rename_model_folders.py' --show fix,ok            # 显示已修改 + 已规范
    python '.github/scripts/models_organize/02_rename_model_folders.py' --show-kb --show-fix     # 显示知识库补全修复 / 已修改（快捷开关可组合）
    python '.github/scripts/models_organize/02_rename_model_folders.py' --show-skip              # 只显示跳过（含问题）
    python '.github/scripts/models_organize/02_rename_model_folders.py' --show-all               # 显示全部条目
  
  分类体系（3 个主状态 + 问题级计数）:
    ok    已规范：无任何问题、无改动
    fix   已修改：本次有改动（知识库补全作品名/中英文名、格式修正、别名归一），
          显示修改内容；若有遗留问题一并显示
    skip  跳过：除 ok 外未改动的条目（副本后缀 / 空名 / 纯数字，或有遗留问题但未改名），
          预览时显示其对应问题
    问题级计数：统计非 ok 条目的问题（fix 遗留 + skip 未处理），每类单独计数；
    跳过条目按问题分组显示：一条目含多个问题时会同时出现在对应的多个分组中
    （如 同时含 other + en-name -> 两个分组都能看到），便于逐类处理。

  知识库维护（已分离到 check&fix/kb_tool.py，本脚本不再提供）:
    python .github/scripts/check&fix/kb_tool.py --help
  根 README 模型分类区块：03_generate_root_readme.py --build-category-map


维护说明：
- 知识库（character/*.json、skin_tags.json、merge_skips.json 等）维护已分离到
  check&fix/kb_tool.py；本脚本只重命名、不写数据库（Unknown/冲突仅标记跳过）。
- --apply 重命名时，若目标名已存在（同名冲突）自动加 -数字 副本序号
  （如 VOC_初音_Chuyin 与已有 VOC_初音_Miku 冲突 -> 重命名为 VOC_初音_Miku-1，
  副本序号放在评级前，幂等；已是最小副本时保持不动）
- 命名规范：<英文作品名>_<中文角色名>[_中文皮肤]_<英文角色名>[_英文皮肤]_<评定等级>；
  作品名前缀统一为规范缩写，唯一命中才填，否则 Unknown（保持原文件夹名不处理）
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import paths as lib_paths
from lib.kb.cmds import (
    build_indexes, build_work_skins, get_target_dirs,
)
from lib.kb.parse import (
    resolve_name,
)
from lib.kb.storage import (
    load_kb_json, migrate_from_sqlite,
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
# 模型文件夹重命名
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    g_run = parser.add_argument_group("预览与重命名")
    g_run.add_argument("--apply", action="store_true",
                       help="真正执行重命名（默认 dry-run 预览）")
    g_run.add_argument("--kb", metavar="DIR", default=str(KB_DEFAULT),
                       help=f"对照数据库目录（默认 {KB_DEFAULT}）")
    g_run.add_argument("--report", metavar="FILE", default="",
                       help="报告输出路径（默认写入系统临时目录）")

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
    parser.add_argument('paths', nargs='*', default=None,
                        help='直接引用路径处理（可多个，如 Models/0001 或 Models/0001/模型名；'
                             '不传则默认 Models + Other-YSM-Models）')
    args = parser.parse_args()

    kb_path = Path(args.kb)
    if not kb_path.is_absolute():
        kb_path = REPO_ROOT / kb_path

    # 直接引用路径（位置参数）处理；不传则默认 Models + Other-YSM-Models
    dirs: list[Path] = []
    for p in (args.paths or [None]):
        sub = get_target_dirs(p)
        if not sub and p:
            # 传入的是具体模型目录（如 Models/0001/模型名）：直接作为目标
            pp = Path(p)
            if pp.is_dir():
                dirs.append(pp)
        else:
            dirs.extend(sub)
    dirs = sorted(set(dirs), key=lambda d: str(d))
    if not dirs:
        print("未找到任何目标文件夹。", file=sys.stderr)
        return 2
    print(f"共找到 {len(dirs)} 个待处理文件夹（直接引用路径；默认 Models + Other-YSM-Models）")

    # 候选皮肤自动收录：解析时识别出"角色名 + 未知中文段"结构的皮肤词
    # （如 泠鸢_登门喜鹊 的「登门喜鹊」，前提 泠鸢 是 OC 已收录角色），
    # 自动加入 skin_tags.json 对应作品（幂等，下次运行即识别为皮肤）。
    def collect_candidate_skins() -> None:
        # 皮肤词表外部化在 skin_tags.json：不再自动收录候选皮肤，
        # 仅提示供手工维护（用 check&fix/kb_tool.py --roles 或编辑 skin_tags.json）。
        total = 0
        for r in results:
            for s in (r.get("candidate_skins") or []):
                total += 1
                rel = r["path"].relative_to(REPO_ROOT).as_posix()
                print(f"  [候选皮肤] {rel} -> 皮肤词 {s}（{r.get('work')}）请用 kb_tool --roles 收录")
        if total:
            print(f"发现 {total} 个候选皮肤（未自动收录，用 check&fix/kb_tool.py --roles 维护）")

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
    work_skins = build_work_skins(roles)

    results = []
    for d in dirs:
        res = resolve_name(d.name, cn_idx, en_idx, en_to_cn, cn_to_en, work_skins)
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

    # 作品未确定（work=Unknown，非跨作品冲突）的条目：纯重命名不收录，
    # 直接标 SKIP 保持原文件夹名（避免重命名成 Unknown_ 前缀；收录请用 kb_tool --add）。
    for r in results:
        if r["status"] != "SKIP" and not r.get("conflict") \
                and r["work"] in ("Unknown", ""):
            r["status"] = "SKIP"
            r["notes"] = "作品未确定（Unknown），保持原文件夹名（收录请用 kb_tool --add）"

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
    for r in results:
        rel = r["path"].relative_to(REPO_ROOT).as_posix()
        tag, probs = classify(r)
        counts[tag] += 1
        # 问题计数：统计非 ok 条目的问题（fix 遗留 + skip 未处理）
        if tag != "ok":
            for p in probs:
                if p in problem_counts:
                    problem_counts[p] += 1
        # 行内容：每条目只在所属状态区出现一次，问题合并进行内显示
        # （不再按问题/修复类型二次分组，避免同一条目重复列出）
        if tag == "skip":
            line = f"[skip] {rel}  (跳过"
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

    report_lines: list[str] = []
    # 每状态一个区（OK/fix/skip），每条目只出现一次，问题合并显示
    SECTION_HEADERS = {"ok": "OK", "fix": "fix", "skip": "skip"}
    for t in ALL_TAGS:
        lines = grouped[t]
        if not lines or t not in visible:
            continue
        head = f"== {SECTION_HEADERS[t]} =="
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

    if args.apply:
        # 跨作品同名冲突：不收录、不询问（本脚本只重命名），直接标 SKIP 保持原文件夹名；
        # 需要收录请先用 check&fix/kb_tool.py 维护知识库。
        unresolved = [r for r in results
                      if r["status"] != "SKIP" and r.get("conflict")]
        if unresolved:
            print(f"跨作品同名冲突 {len(unresolved)} 个：保持原文件夹名，不收录"
                  f"（收录请用 check&fix/kb_tool.py --add）")
            for r in unresolved:
                r["status"] = "SKIP"
                r["notes"] = "跨作品同名冲突，保持原文件夹名（收录请用 kb_tool）"

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
