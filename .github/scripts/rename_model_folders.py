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
     （.github/scripts/data/ysm-rename/：works.json + aliases.json + roles/<作品>.json，
     可直接用编辑器改，每个脚本的独立数据库位于 data/<脚本名>/ 下）。
     唯一命中才填作品名，否则 Unknown；多候选冲突也标 Unknown 并提示。
  5. 知识库中 source="manual" 的手工条目在重建时保留，且优先于自动条目。
     手工修改：直接编辑 data/ysm-rename/ 下的 json 文件（roles/<作品>.json 等）。
     手改后无需任何命令，脚本下次运行即生效。

默认 dry-run 只预览；加 --apply 才真正重命名。

用法（按功能分组）:

  预览与重命名:
    python .github/scripts/ysm_rename.py                    # 预览（默认只显示人工确认条目）
    python .github/scripts/ysm_rename.py --apply            # 执行重命名
    python .github/scripts/ysm_rename.py --path Models      # 只处理单个根
    python .github/scripts/ysm_rename.py --no-sync          # 关闭 README works 同步

  知识库维护:
    python .github/scripts/ysm_rename.py --build-kb         # 重建并保存对照数据库
    python .github/scripts/ysm_rename.py --add              # 交互式添加手工对照条目
    python .github/scripts/ysm_rename.py --alias            # 登记别名/变体（大昔涟 -> 昔涟）
    python .github/scripts/ysm_rename.py --del              # 删除条目（搜索 -> 选 id）
    python .github/scripts/ysm_rename.py --check            # 数据质量检查
    python .github/scripts/ysm_rename.py --suggest          # 疑似匹配建议（确认后写别名）
    python .github/scripts/ysm_rename.py --list             # 查看数据库全部条目

  预览显示过滤（控制台与报告一致；默认只显示人工确认 MANUAL）:
    python .github/scripts/ysm_rename.py --show KB          # 只显示知识库补作品
    python .github/scripts/ysm_rename.py --show KB,FIX      # 只显示 KB 和 FIX
    python .github/scripts/ysm_rename.py --show-kb --show-fix   # 同上（快捷开关可组合）
    python .github/scripts/ysm_rename.py --show-all         # 显示全部条目

维护说明：
- 直接编辑 .github/scripts/data/ysm-rename/ 下的 json 文件即可增删改（手改即时生效）
- 也可以命令行：--add 加角色 / --alias 加别名 / --del 删 / --list 看
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
  后藤一里/波奇酱）；数组第一个为出现最多的规范名；跨作品不合并。
  合并后的 auto 条目重建时自动重新合并，无需手工维护
- 别名/变体（别称、大小修饰、多英文名）也可放 aliases 数组，如 大昔涟 -> 昔涟
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3  # 仅用于首次从旧 SQLite 库迁移
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOTS = [REPO_ROOT / "Models", REPO_ROOT / "Other-YSM-Models"]
# 对照数据库（外置，目录：works.json + aliases.json + roles/<作品>.json）
# 每个脚本的独立数据库位于 .github/scripts/data/<脚本名>/ 下
KB_DEFAULT = Path(__file__).resolve().parent / "data" / "ysm-rename"


CJK_RE = re.compile(r"[\u4e00-\u9fff]")
GRADE_RE = re.compile(r"(?i)_(la|lb|lc|ld)$")
TOUHOU_PREFIX_RE = re.compile(r"(?i)^touhou(.+)$")
MIXED_SEG_RE = re.compile(
    r"^(?P<cn>[\u4e00-\u9fff·]+)(?:-(?P<skin>[\u4e00-\u9fff·][\u4e00-\u9fff·-]*))?(?:-|_|\s+)(?P<en>.+)$"
)
CN_SKIN_RE = re.compile(r"^(.+?)-([\u4e00-\u9fff].*)$")
EN_TAIL_RE = re.compile(r"[-_][^-_]+$")
PAREN_RE = re.compile(r"[\(（][^\)）]*[\)）]")


def has_cjk(s: str) -> bool:
    return CJK_RE.search(s) is not None


def init_caps(s: str) -> str:
    """全小写 token 首字母大写；已含大写的 token 不动。"""
    if not s:
        return s

    def repl(m: re.Match) -> str:
        sep, t = m.group(1), m.group(2)
        return sep + t[0].upper() + t[1:]

    # 分隔符（串首 / 空白 / - _ （ (）后的全小写 token -> 首字母大写
    return re.sub(r"(^|[\s_\-（(])([a-z][a-z0-9]*)", repl, s)


def normalize_en_key(s: str) -> str:
    """英文名归一化：去括号内容、去空白、小写。"""
    t = PAREN_RE.sub("", s)
    t = re.sub(r"\s+", "", t)
    return t.lower()


# 运行时由 works 数据（含 README 同步）派生的作品名 -> 键 映射（去标点归一化后）
EXTRA_WORK_ALIASES: dict[str, str] = {}


def normalize_work_name(name: str) -> str:
    """作品名归一化：小写、去标点（保留中文字符与字母数字）。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", name.lower())


def get_work_canonical(seg: str) -> str | None:
    # 作品名识别完全依赖外置数据库（works 数据构建的 EXTRA_WORK_ALIASES）
    return EXTRA_WORK_ALIASES.get(normalize_work_name(seg))


def ask(prompt: str) -> str:
    """安全的交互输入：去 BOM、去首尾空白；非交互 stdin 耗尽时返回 'q'（退出）。"""
    try:
        return input(prompt).strip().lstrip('\ufeff')
    except EOFError:
        return 'q'


# ---------------------------------------------------------------------------
# 名称解析
# ---------------------------------------------------------------------------
def resolve_name(name: str, cn_idx: dict, en_idx: dict,
                 en_to_cn: dict | None = None, cn_to_en: dict | None = None) -> dict:
    orig = name
    grade = ""
    manual: list[str] = []

    m = GRADE_RE.search(name)
    if m:
        grade = m.group(1).upper()
        name = name[: m.start()]
    name = name.strip().rstrip("_- ")
    segments = [s.strip() for s in name.split("_")]
    segments = [s for s in segments if s]

    if not segments:
        return {"original": orig, "new": "", "status": "SKIP", "notes": "empty name",
                "work": "", "cn": "", "en": "", "grade": grade, "work_source": "none"}

    work = ""
    work_source = "none"
    cn = ""
    cn_skin = ""
    en = ""

    first = segments[0]
    rest = segments[1:]
    rest_has_cjk = any(has_cjk(s) for s in rest)

    touhou_m = TOUHOU_PREFIX_RE.match(first)
    if touhou_m and has_cjk(first):
        work = "Touhou"
        work_source = "prefix"
        rest = [touhou_m.group(1)] + rest
    elif (canon := get_work_canonical(first)):
        work = canon
        work_source = "prefix"
    elif (re.match(r"^[A-Za-z]", first) and not has_cjk(first) and rest_has_cjk
          and normalize_en_key(first) not in en_idx):
        # ASCII 段 + 后续有中文段 -> 视为作品名（除非该 ASCII 是知识库中已知的英文角色名）
        work = first
        work_source = "prefix"
    else:
        rest = segments

    # Unknown 前缀（或待定）后紧跟的作品缩写段：识别为作品并剥离，如
    # Unknown_AKE_Endministrator_Female -> work=AKE, 角色部分 Endministrator_Female
    if (not work or work == "Unknown") and rest:
        w0 = get_work_canonical(rest[0])
        if w0 and w0 != work:
            work = w0
            work_source = "prefix"
            rest = rest[1:]

    cjk_segs: list[str] = []
    en_segs: list[str] = []
    for seg in rest:
        if has_cjk(seg):
            if re.search(r"[A-Za-z]", seg):
                mm = MIXED_SEG_RE.match(seg)
                if mm:
                    cn_with_skin = mm.group("cn")
                    if mm.group("skin"):
                        cn_with_skin += "-" + mm.group("skin")
                    cjk_segs.append(cn_with_skin)
                    en_segs.append(mm.group("en"))
                else:
                    cjk_segs.append(seg)
                    manual.append("mixed segment unresolved: " + seg)
            else:
                cjk_segs.append(seg)
        else:
            en_segs.append(seg)

    if cjk_segs:
        cn_raw = "_".join(cjk_segs)
        m = CN_SKIN_RE.match(cn_raw)
        if m:
            cn = m.group(1)
            cn_skin = m.group(2)
        else:
            cn = cn_raw
        if len(cjk_segs) > 1:
            manual.append("multiple CJK segments")
    if en_segs:
        en = "_".join(en_segs)
        if len(en_segs) > 1:
            manual.append("multiple EN segments")

    if not cn and not en:
        return {"original": orig, "new": "", "status": "SKIP", "notes": "no role info",
                "work": work, "cn": "", "en": "", "grade": grade, "work_source": work_source}

    # 作品名：前缀优先；但 Unknown 前缀视为「待定」，仍允许知识库修正。
    conflict = False
    if not work or work == "Unknown":
        hits: set[str] = set()
        if cn and cn in cn_idx:
            hits |= cn_idx[cn]
        if en:
            # 英文名查询：同时尝试 原样 与 下划线->连字符 两种键，容错录入差异
            for cand in {normalize_en_key(en), normalize_en_key(en).replace('_', '-')}:
                while cand:
                    if cand in en_idx:
                        hits |= en_idx[cand]
                    cand = EN_TAIL_RE.sub('', cand) if EN_TAIL_RE.search(cand) else ''
            # 英文名首段为已知作品缩写（如 UM-Agnes-Digital 的 UM -> UmaMusume、
            #  GF-M200 的 GF -> 少女前线）：确定性的作品归属
            first_bit = re.split(r"[-_\s]", en, maxsplit=1)[0].lower()
            if first_bit:
                w = get_work_canonical(first_bit)
                if w:
                    hits.add(w)
        if len(hits) == 1:
            work = next(iter(hits))
            work_source = "kb"
        elif len(hits) > 1:
            conflict = True
            manual.append("ambiguous work: " + "/".join(sorted(hits)))
            work = "Unknown"
            work_source = "conflict"
        elif not work:
            work = "Unknown"
            work_source = "none"
        # hits 为空且 work 原本就是 Unknown（前缀）：保持 Unknown，不再改写

    # 知识库补全：work 已确定但缺中文名/英文名时，用数据库反查补上（唯一候选才补）
    filled: list[str] = []
    if work and work != "Unknown":
        if not cn and en and en_to_cn:
            cands: set[str] = set()
            k1 = normalize_en_key(en)
            for k in {k1, k1.replace('_', '-')}:
                for w, c in en_to_cn.get(k, []):
                    if w == work:
                        cands.add(c)
            if len(cands) == 1:
                cn = cands.pop()
                filled.append("CN auto-filled: " + cn)
        if cn and not en and cn_to_en:
            cands = set()
            for w, e in cn_to_en.get(cn, []):
                if w == work:
                    cands.add(e)
            if len(cands) == 1:
                en = cands.pop()
                filled.append("EN auto-filled: " + en)

    if en:
        en = init_caps(en)
        if re.fullmatch(r"[0-9]+", en):
            return {"original": orig, "new": "", "status": "SKIP", "notes": "numeric EN only",
                    "work": work, "cn": cn, "en": en, "grade": grade, "work_source": work_source}

    new = work
    if cn:
        new += "_" + cn
        if cn_skin:
            new += "-" + cn_skin
    if en:
        new += "_" + en
    if grade:
        new += "_" + grade

    if not cn:
        manual.append("missing CN name")
    if not en:
        manual.append("missing EN name")

    status = "OK" if new == orig else "FIX"
    return {"original": orig, "new": new, "status": status, "notes": "; ".join(manual),
            "filled": "; ".join(filled), "work": work, "cn": cn, "en": en, "grade": grade,
            "conflict": conflict, "work_source": work_source}


# ---------------------------------------------------------------------------
# 知识库
# ---------------------------------------------------------------------------
def role_key(r: dict) -> str:
    """角色条目的去重键：取 cn/en 的规范名（数组第一个）。"""
    cn = r["cn"][0] if isinstance(r["cn"], list) else r["cn"]
    en = r["en"][0] if isinstance(r["en"], list) else r["en"]
    return f"{r['work']}|{cn}|{en.lower()}"


def build_kb(all_names: list[str]) -> list[dict]:
    """从文件夹名提取角色条目，并自动合并同一角色的不同写法（别名）。

    合并规则（仅限同一作品内）：
      1. 同 中文名 + 不同英文名  -> 合并为 en 数组（如 阿米娅 amiya/amyia）
      2. 英文名集合有交集        -> 合并为 cn 数组（如 后藤一里/波奇酱 都是 hitori-goto）
      3. 跨作品不合并（如 夏安 在 GF 与 GF2 各自保留）
    cn 数组第一个为出现次数最多的规范名（补全默认用它）。
    """
    from collections import defaultdict

    cn_en: dict[tuple, set] = defaultdict(set)      # (work, cn) -> {en}
    cn_cnt: dict[tuple, int] = defaultdict(int)     # (work, cn) -> 出现次数
    for n in all_names:
        r = resolve_name(n, {}, {})  # 仅前缀解析，不需要知识库
        if r["status"] == "SKIP":
            continue  # 无法安全解析的（纯数字编号、无角色信息等）不进数据库
        if r["work"] and r["work"] != "Unknown" and r["cn"] and r["en"]:
            key = (r["work"], r["cn"])
            cn_en[key].add(r["en"].lower())
            cn_cnt[key] += 1

    # 基础条目（同 work+cn 聚合 en）
    base: list[list] = [[work, cn, ens, cn_cnt[(work, cn)]]
                        for (work, cn), ens in cn_en.items()]

    # 按 (work, en 交集) 合并：同一作品内英文名重叠 => 同一角色（昵称/别称）
    n = len(base)
    used = [False] * n
    merged: list[dict] = []
    for i in range(n):
        if used[i]:
            continue
        group = [base[i]]
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j in range(n):
                if used[j]:
                    continue
                if any(base[j][0] == g[0] and base[j][2] & g[2] for g in group):
                    group.append(base[j])
                    used[j] = True
                    changed = True
        work = group[0][0]
        cns = [g[1] for g in group]
        cnts = {g[1]: g[3] for g in group}
        cns.sort(key=lambda c: -cnts[c])  # 出现次数多者在前（规范名）
        ens = sorted(set().union(*[g[2] for g in group]))
        merged.append({"work": work, "cn": cns, "en": ens, "source": "auto"})
    return merged


# ---------------------------------------------------------------------------
# 知识库（JSON 格式，可直接用文本编辑器修改）
# ---------------------------------------------------------------------------
def _safe_name(wk: str) -> str:
    """作品键 -> 安全文件名（Windows 非法字符替换为 _）。"""
    return re.sub(r'[\\/:*?"<>|]', '_', wk or "_")


def load_kb_json(kb_path: Path) -> dict:
    """读取知识库。

    kb_path 为目录：读多文件（works.json / aliases.json / roles/<作品>.json）；
    为旧单文件（ysm_kb.json）时直接读取（兼容，保存时自动迁移为多文件）。
    """
    empty = {"version": 2, "works": {}, "roles": [], "aliases": []}
    if not kb_path.exists():
        return empty
    if kb_path.is_file():
        try:
            data = json.loads(kb_path.read_text(encoding="utf-8"))
            data.setdefault("works", {})
            data.setdefault("roles", [])
            data.setdefault("aliases", [])
            return data
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] 知识库 JSON 无法解析: {e}", file=sys.stderr)
            return empty
    data = {"version": 2, "works": {}, "roles": [], "aliases": []}
    wf = kb_path / "works.json"
    old_single = kb_path / "ysm_kb.json"
    if not wf.exists() and not (kb_path / "roles").exists() and old_single.exists():
        # 尚未迁移：读旧单文件（避免手工条目丢失）
        try:
            d = json.loads(old_single.read_text(encoding="utf-8"))
            d.setdefault("works", {})
            d.setdefault("roles", [])
            d.setdefault("aliases", [])
            return d
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] 知识库 JSON 无法解析: {e}", file=sys.stderr)
            return empty
    if wf.exists():
        try:
            data["works"] = json.loads(wf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] 忽略损坏文件 {wf}: {e}", file=sys.stderr)
    af = kb_path / "aliases.json"
    if af.exists():
        try:
            data["aliases"] = json.loads(af.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] 忽略损坏文件 {af}: {e}", file=sys.stderr)
    rdir = kb_path / "roles"
    roles: list = []
    if rdir.is_dir():
        for f in sorted(rdir.glob("*.json")):
            try:
                roles.extend(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[warn] 忽略损坏文件 {f}: {e}", file=sys.stderr)
    data["roles"] = roles
    return data


def save_kb_json(kb_path: Path, data: dict) -> None:
    """写回知识库（多文件）：works.json + aliases.json + roles/<作品>.json。

    kb_path 为目录；若为旧单文件路径则以其父目录为数据根并迁移。
    """
    if kb_path.is_file():
        old_single = kb_path
        kb_path = old_single.parent
    else:
        old_single = kb_path / "ysm_kb.json"
    kb_path.mkdir(parents=True, exist_ok=True)
    data["version"] = 2
    # works 值支持三种写法：平铺数组 / 空 [] / 按语言分类对象
    works_out: dict = {}
    for k, v in (data.get("works") or {}).items():
        if isinstance(v, dict):
            d_out: dict[str, list] = {}
            for lang, names in v.items():
                if isinstance(names, list):
                    out = []
                    for x in names:
                        if x and x not in out:
                            out.append(x)
                    d_out[lang] = out
                elif names:
                    d_out[lang] = [names]
                else:
                    d_out[lang] = []
            works_out[k] = d_out
        elif isinstance(v, list):
            out = []
            for x in v:
                if x and x not in out:
                    out.append(x)
            works_out[k] = out
        elif v:
            works_out[k] = [v]
        else:
            works_out[k] = []
    data["works"] = dict(sorted(works_out.items()))
    for r in (data.get("roles") or []):
        for f in ("cn", "en"):
            v = r.get(f)
            if isinstance(v, list):
                out = []
                for x in v:
                    if x and x not in out:
                        out.append(x)
                r[f] = out
    roles = sorted(data.get("roles") or [],
                   key=lambda r: (r.get("source") != "manual",
                                  str(r.get("work", "")), str(r.get("cn", ""))))
    aliases = sorted(data.get("aliases") or [],
                     key=lambda a: (a.get("kind", ""), str(a.get("alias", ""))))
    (kb_path / "works.json").write_text(
        json.dumps(data["works"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (kb_path / "aliases.json").write_text(
        json.dumps(aliases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # roles 按作品分组写 roles/<作品>.json（重建前清空旧文件）
    rdir = kb_path / "roles"
    rdir.mkdir(exist_ok=True)
    for f in rdir.glob("*.json"):
        f.unlink()
    groups: dict[str, list] = {}
    for r in roles:
        groups.setdefault(str(r.get("work", "_")), []).append(r)
    for wk, lst in sorted(groups.items()):
        (rdir / f"{_safe_name(wk)}.json").write_text(
            json.dumps(lst, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if old_single and old_single.exists():
        print(f"已迁移为多文件结构（works.json / aliases.json / roles/*.json），"
              f"旧 {old_single.name} 可删除")


def migrate_from_sqlite(kb_path: Path, sqlite_path: Path) -> tuple[list[dict], list[dict]]:
    """首次迁移：旧 SQLite 库存在且 JSON 不存在时，搬移手工角色与别名。"""
    if kb_path.exists() or not sqlite_path.exists():
        return [], []
    try:
        conn = sqlite3.connect(str(sqlite_path))
        try:
            cur = conn.cursor()
            cur.execute("SELECT cn, en, work, note FROM roles WHERE source = 'manual'")
            manual = [{"cn": r[0], "en": r[1], "work": r[2], "source": "manual",
                       "note": r[3] or ""} for r in cur.fetchall()]
            cur.execute("SELECT kind, alias, canonical, work, note FROM aliases")
            aliases = [{"kind": r[0], "alias": r[1], "canonical": r[2],
                        "work": r[3], "source": "manual", "note": r[4] or ""}
                       for r in cur.fetchall()]
        finally:
            conn.close()
        print(f"已从旧 SQLite 迁移 {len(manual)} 条手工角色、{len(aliases)} 条别名")
        return manual, aliases
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 旧 SQLite 迁移失败（忽略）: {e}", file=sys.stderr)
        return [], []


def add_manual_entries(kb_path: Path) -> None:
    """交互式添加手工对照条目（source='manual'，重建时保留、匹配时优先）。"""
    data = load_kb_json(kb_path)
    print("交互式添加对照条目：逐项输入，回车跳过；输入 q 结束。")
    print("提示：英文名请填文件夹中出现的写法（如 kitasan_black），")
    print("      或规范形式（kitasan-black）——两者都能匹配。")
    added = 0
    while True:
        print("-" * 40)
        cn = ask("中文角色名 (可空): ")
        if cn.lower() in ("q", "quit"):
            break
        en = ask("英文角色名 (可空): ")
        if en.lower() in ("q", "quit"):
            break
        work = ask("作品 (必填，如 BA/AK/OC): ")
        if work.lower() in ("q", "quit"):
            break
        if not work:
            print("作品不能为空，本条跳过。")
            continue
        if not cn and not en:
            print("中文名和英文名至少填一个，本条跳过。")
            continue
        note = ask("备注 (可空): ")
        if note.lower() in ("q", "quit"):
            break
        data["roles"].append({"cn": cn or "", "en": en or "", "work": work,
                              "source": "manual", "note": note})
        save_kb_json(kb_path, data)
        added += 1
        print(f"已添加: {cn or '?'} | {en or '?'} | {work} [manual]")
    print(f"共添加 {added} 条。知识库: {kb_path}")


def add_alias_entries(kb_path: Path) -> None:
    """交互式登记别名/变体：别称、大小修饰、多英文名 -> 规范名。"""
    data = load_kb_json(kb_path)
    print("交互式登记别名：把 别称/变体（大昔涟、小昔涟、多英文名…）指向规范角色名。")
    print("输入 q 结束。")
    added = 0
    while True:
        print("-" * 40)
        kind_in = ask("类型 (1=中文别名, 2=英文别名, q=退出): ")
        if kind_in.lower() in ("q", "quit"):
            break
        if kind_in == "1":
            kind = "cn"
        elif kind_in == "2":
            kind = "en"
        else:
            print("请输入 1 或 2。")
            continue
        alias = ask("别名/变体（如 大昔涟）: ")
        if alias.lower() in ("q", "quit"):
            break
        if not alias:
            print("别名不能为空，跳过。")
            continue
        canonical = ask("规范名（如 昔涟，即角色对照表里的标准名字）: ")
        if canonical.lower() in ("q", "quit"):
            break
        if not canonical:
            print("规范名不能为空，跳过。")
            continue
        work = ask("作品（如 HSR）: ")
        if work.lower() in ("q", "quit"):
            break
        if not work:
            print("作品不能为空，跳过。")
            continue
        note = ask("备注 (可空): ")
        if note.lower() in ("q", "quit"):
            break
        data["aliases"].append({"kind": kind, "alias": alias, "canonical": canonical,
                                "work": work, "source": "manual", "note": note})
        save_kb_json(kb_path, data)
        added += 1
        print(f"已登记: [{kind}] {alias} -> {canonical} ({work}) [manual]")
    print(f"共登记 {added} 条别名。知识库: {kb_path}")


def list_db(kb_path: Path) -> None:
    """列出知识库全部条目（角色对照 + 别名）。"""
    data = load_kb_json(kb_path)
    roles = data.get("roles") or []
    aliases = data.get("aliases") or []
    if not roles and not aliases:
        print(f"知识库为空或不存在: {kb_path}（先运行 --build-kb 生成）")
        return
    if roles:
        print(f"角色对照 {len(roles)} 条（manual=手工，auto=自动）:")
        for r in roles:
            cn_v, en_v = r.get("cn"), r.get("en")
            cn_s = cn_v[0] if isinstance(cn_v, list) else (cn_v or '-')
            en_s = en_v[0] if isinstance(en_v, list) else (en_v or '-')
            extra = ""
            if isinstance(cn_v, list) and len(cn_v) > 1:
                extra += f" (+{len(cn_v) - 1}中文别名)"
            if isinstance(en_v, list) and len(en_v) > 1:
                extra += f" (+{len(en_v) - 1}英文别名)"
            line = (f"  {r.get('work', ''):<12} | {cn_s:<14} | {en_s:<28}"
                    f" | [{r.get('source', '')}]{extra}")
            if r.get("note"):
                line += f"  #{r['note']}"
            print(line)
    if aliases:
        print(f"别名/变体 {len(aliases)} 条:")
        for a in aliases:
            line = (f"  [{a.get('kind', '')}] {a.get('alias', ''):<12}"
                    f" -> {a.get('canonical', ''):<12} ({a.get('work', '')})"
                    f" [{a.get('source', '')}]")
            if a.get("note"):
                line += f"  #{a['note']}"
            print(line)


def del_entries(kb_path: Path) -> None:
    """交互式删除条目（角色对照或别名）。按关键词搜索 -> 选编号删除。"""
    data = load_kb_json(kb_path)
    while True:
        kw = ask("搜索关键词 (中文名/英文名/作品，留空=列出全部，q=退出): ")
        if kw.lower() in ("q", "quit"):
            break
        print("-" * 60)
        roles = data.get("roles") or []
        aliases = data.get("aliases") or []
        if kw:
            r_hits = [r for r in roles
                      if kw.lower() in str(r.get("cn", "")).lower()
                      or kw.lower() in str(r.get("en", "")).lower()
                      or kw.lower() in str(r.get("work", "")).lower()]
            a_hits = [a for a in aliases
                      if kw.lower() in str(a.get("alias", "")).lower()
                      or kw.lower() in str(a.get("canonical", "")).lower()
                      or kw.lower() in str(a.get("work", "")).lower()]
        else:
            r_hits, a_hits = roles, aliases
        if r_hits:
            print(f"角色对照 {len(r_hits)} 条（输入编号删除，多个用逗号分隔）:")
            for i, r in enumerate(r_hits, 1):
                line = (f"  [{i}] {r.get('work', ''):<12} | {r.get('cn') or '-':<14}"
                        f" | {r.get('en') or '-':<28} | [{r.get('source', '')}]")
                if r.get("note"):
                    line += f"  #{r['note']}"
                print(line)
        if a_hits:
            print(f"别名 {len(a_hits)} 条（编号前加 a，如 a1）:")
            for i, a in enumerate(a_hits, 1):
                line = (f"  [a{i}] {a.get('alias', ''):<12} -> {a.get('canonical', ''):<12}"
                        f" ({a.get('work', '')}) [{a.get('source', '')}]")
                if a.get("note"):
                    line += f"  #{a['note']}"
                print(line)
        if not r_hits and not a_hits:
            print("无匹配条目。")
            continue
        sel = ask("要删除的编号（角色直接输数字，别名用 a+数字；留空=不删，q=退出）: ")
        if sel.lower() in ("q", "quit"):
            break
        if not sel:
            continue
        removed = 0
        for token in sel.replace("，", ",").split(","):
            token = token.strip()
            if not token:
                continue
            if token.lower().startswith("a"):
                idx = int(token[1:]) - 1
                if 0 <= idx < len(a_hits):
                    aliases.remove(a_hits[idx])
                    removed += 1
            else:
                idx = int(token) - 1
                if 0 <= idx < len(r_hits):
                    roles.remove(r_hits[idx])
                    removed += 1
        data["roles"] = roles
        data["aliases"] = aliases
        save_kb_json(kb_path, data)
        print(f"已删除 {removed} 条。")


def parse_readme_works(readme_path: Path) -> list[dict]:
    """解析 README 作品表。

    每行格式：英文名称[,别名...] | 中文名称[,别名...] | 日文名称
    跳过分类标题（无 |）和 Markdown 表格（行首 |）。
    """
    if not readme_path.exists():
        return []
    works: list[dict] = []
    for line in readme_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("|") or "|" not in line:
            continue
        # 剥离 Markdown 无序列表标记（- 名称 | ...）
        for marker in ("- ", "* ", "+ "):
            if line.startswith(marker):
                line = line[len(marker):].strip()
                break
        parts = [p.strip() for p in line.split("|")]
        en_names = [n.strip() for n in parts[0].split(",") if n.strip()]
        if not en_names:
            continue
        cn_names = [n.strip() for n in parts[1].split(",") if n.strip()] if len(parts) > 1 else []
        ja_names = [n.strip() for n in parts[2].split(",") if n.strip()] if len(parts) > 2 else []
        works.append({"en": en_names, "cn": cn_names, "ja": ja_names})
    return works


def work_value_names(v) -> list[str]:
    """从 works 值（dict/列表/字符串）提取全部名称。"""
    names: list[str] = []
    if isinstance(v, dict):
        for lst in v.values():
            if isinstance(lst, list):
                names.extend(lst)
            elif lst:
                names.append(lst)
    elif isinstance(v, list):
        names.extend(v)
    elif v:
        names.append(v)
    return names


def _dedup(items: list[str]) -> list[str]:
    out = []
    for x in items:
        if x and x not in out:
            out.append(x)
    return out


def sync_works_from_readme(data: dict, readme_path: Path) -> tuple[int, int]:
    """README 为 works 权威源：同步新增/更新。

    键规则：英文名列表的最后一项作为作品键（用户约定的默认缩写）；
    若与现有 works 任一名称匹配则复用现有键。README 提供的语言键覆盖，
    未提供的语言键（如现有 ko 等）保留。
    返回 (新增数, 更新数)。
    """
    parsed = parse_readme_works(readme_path)
    if not parsed:
        return 0, 0
    works = data.setdefault("works", {})
    idx: dict[str, str] = {}
    for wk, v in works.items():
        for name in work_value_names(v):
            idx.setdefault(normalize_work_name(name), wk)
        idx.setdefault(normalize_work_name(wk), wk)
    added = updated = 0
    for p in parsed:
        norm_all = [normalize_work_name(n) for n in p["en"] + p["cn"]]
        key = next((idx[n] for n in norm_all if n and n in idx), None)
        if key is None:
            key = p["en"][-1]  # 新作品：英文名最后一项作为默认键
            added += 1
        else:
            updated += 1
        new_val: dict = {}
        if key in works and isinstance(works[key], dict):
            new_val = dict(works[key])  # 保留现有其它语言键
        if p["en"]:
            new_val["en"] = _dedup(p["en"])
        if p["cn"]:
            new_val["cn"] = _dedup(p["cn"])
        if p["ja"]:
            new_val["ja"] = _dedup(p["ja"])
        works[key] = new_val
    return added, updated


def build_work_index(data: dict) -> None:
    """从 works 数据构建全局作品名 -> 键 映射（解析前缀时使用）。"""
    global EXTRA_WORK_ALIASES
    EXTRA_WORK_ALIASES = {}
    for wk, v in (data.get("works") or {}).items():
        for name in work_value_names(v):
            norm = normalize_work_name(name)
            if norm:
                EXTRA_WORK_ALIASES.setdefault(norm, wk)
        norm = normalize_work_name(wk)
        if norm:
            EXTRA_WORK_ALIASES.setdefault(norm, wk)


def run_check(kb_path: Path) -> None:
    """数据质量检查：同名多作品、空字段、重复条目、别名悬空。"""
    data = load_kb_json(kb_path)
    roles = data.get("roles") or []
    aliases = data.get("aliases") or []
    issues: list[str] = []

    def split(v):
        return v if isinstance(v, list) else ([v] if v else [])

    cn_works: dict[str, set] = {}
    en_works: dict[str, set] = {}
    seen_pairs: dict[str, int] = {}
    for r in roles:
        cn_list = [c for c in split(r.get("cn")) if c]
        en_list = [e for e in split(r.get("en")) if e]
        for c in cn_list:
            cn_works.setdefault(c, set()).add(r.get("work", "?"))
        for e in en_list:
            en_works.setdefault(normalize_en_key(e), set()).add(r.get("work", "?"))
        # 完全重复检测（同 cn+en+work）
        key = "|".join([r.get("work", "?"), "&".join(cn_list), "&".join(en_list)])
        seen_pairs[key] = seen_pairs.get(key, 0) + 1
    for c, ws in sorted(cn_works.items()):
        if len(ws) > 1:
            issues.append(f"同名多作品: {c} -> {', '.join(sorted(ws))}")
    for e, ws in sorted(en_works.items()):
        if len(ws) > 1:
            issues.append(f"同英文名多作品: {e} -> {', '.join(sorted(ws))}")
    for r in roles:
        cn_list = [c for c in split(r.get("cn")) if c]
        en_list = [e for e in split(r.get("en")) if e]
        if not cn_list and not en_list:
            issues.append(f"空条目: {r}")
        elif not cn_list or not en_list:
            issues.append(f"缺中/英文名: work={r.get('work', '?')} cn={r.get('cn') or '-'} en={r.get('en') or '-'}")
    for key, cnt in seen_pairs.items():
        if cnt > 1:
            issues.append(f"重复条目 x{cnt}: {key}")
    # 别名悬空：canonical 不在 roles 中
    known_cn = {c for r in roles for c in split(r.get("cn"))}
    known_en = {normalize_en_key(e) for r in roles for e in split(r.get("en"))}
    for a in aliases:
        if a.get("kind") == "cn" and a.get("canonical") not in known_cn:
            issues.append(f"别名悬空: [{cn}] {a.get('alias')} -> {a.get('canonical')} ({a.get('work')})")
        if a.get("kind") == "en" and normalize_en_key(a.get("canonical", "")) not in known_en:
            issues.append(f"别名悬空: [en] {a.get('alias')} -> {a.get('canonical')} ({a.get('work')})")

    if not issues:
        print(f"检查通过：{len(roles)} 条角色、{len(aliases)} 条别名，无问题。")
        return
    print(f"发现 {len(issues)} 个问题（同类合并，最多显示 50 条）:")
    shown = set()
    n = 0
    for line in issues:
        if line in shown:
            continue
        shown.add(line)
        print("  - " + line)
        n += 1
        if n >= 50:
            print("  ...（其余略）")
            break


def run_suggest(kb_path: Path) -> None:
    """疑似匹配建议：扫描 work=Unknown 的文件夹，按包含关系给出候选，确认后写入别名。"""
    data = load_kb_json(kb_path)
    build_work_index(data)
    manual = [r for r in (data.get("roles") or []) if r.get("source") == "manual"]
    built = build_kb([d.name for d in get_target_dirs(None)])
    roles = list(built)
    seen = {role_key(r) for r in built}
    for m in manual:
        key = role_key(m)
        if key in seen:
            # 手工条目优先：替换 built 中同 key 的条目（保留手工别名）
            roles = [r for r in roles if role_key(r) != key]
        else:
            seen.add(key)
        roles.append(m)
    cn_idx, en_idx, en_to_cn, cn_to_en = build_indexes(
        roles, manual, data.get("aliases") or [])

    cn_keys = sorted([k for k in cn_idx if len(k) >= 2 and "_" not in k],
                     key=len, reverse=True)
    # 允许连字符（misaka-mikoto 等标准英文名），排除下划线（皮肤/多段串如 padoru_hakurei-...）
    en_keys = sorted([k for k in en_idx if len(k) >= 4 and "_" not in k],
                     key=len, reverse=True)

    suggestions: list[tuple] = []
    no_cand: list[tuple] = []
    for d in get_target_dirs(None):
        r = resolve_name(d.name, cn_idx, en_idx, en_to_cn, cn_to_en)
        if r["work"] != "Unknown" or not (r["cn"] or r["en"]):
            continue
        cands: list[tuple] = []
        if r["cn"]:
            for k in cn_keys:
                if k in r["cn"] or r["cn"] in k:
                    ws = cn_idx[k]
                    if len(ws) == 1:
                        cands.append((k, next(iter(ws)), "cn"))
        if r["en"]:
            enk = normalize_en_key(r["en"])
            if enk:
                for k in en_keys:
                    if k in enk or enk in k:
                        ws = en_idx[k]
                        if len(ws) == 1:
                            cands.append((k, next(iter(ws)), "en"))
        seen_c = set()
        shown = 0
        for canonical, work, kind in cands:
            key = (canonical, work)
            if key in seen_c:
                continue
            seen_c.add(key)
            suggestions.append((d.name, r, canonical, work, kind))
            shown += 1
            if shown >= 3:
                break
        if not seen_c:
            no_cand.append((d.name, r))

    if not suggestions:
        print("没有发现疑似匹配。")
    else:
        print(f"发现 {len(suggestions)} 条疑似匹配（y=接受写入别名, n=跳过, q=退出）:")
        accepted = 0
        for i, (folder, r, canonical, work, kind) in enumerate(suggestions, 1):
            if kind == "cn":
                alias = r["cn"]
                desc = f"中文名「{alias}」包含/被包含于「{canonical}」"
            else:
                alias = r["en"]
                desc = f"英文名「{alias}」包含/被包含于「{canonical}」"
            ans = ask(f"[{i}/{len(suggestions)}] {folder}  {desc} -> {canonical} ({work})? (y/n/q): ").lower()
            if ans in ("q", "quit"):
                break
            if ans not in ("y", "yes"):
                continue
            data["aliases"].append({"kind": kind, "alias": alias, "canonical": canonical,
                                    "work": work, "source": "manual", "note": ""})
            accepted += 1
            print(f"  已登记别名: [{kind}] {alias} -> {canonical} ({work})")
        if accepted:
            save_kb_json(kb_path, data)
            print(f"共登记 {accepted} 条别名，已保存: {kb_path}")
        else:
            print("未登记任何别名。")

    if no_cand:
        print(f"\n另有 {len(no_cand)} 个 Unknown 文件夹无候选，需手工补充"
              f"（--add 添加对照，或编辑 JSON 的 roles/aliases；仅显示前 30 条）:")
        for name, _r in no_cand[:30]:
            print(f"  {name}")
        if len(no_cand) > 30:
            print(f"  ...（其余 {len(no_cand) - 30} 条略，完整清单见报告文件）")


def build_indexes(roles: list[dict], manual_roles: list[dict] | None = None,
                  aliases: list[dict] | None = None):
    """返回 (cn_idx, en_idx, en_to_cn, cn_to_en)。后两者用于补全缺失的中/英文名。
    角色条目的 cn/en 可以是字符串或数组：数组第一个为规范名（补全默认用它），
    其余为别名（仅用于匹配，补全时也归一到规范名）。"""

    def split_names(v):
        """字符串 -> 单元素列表；数组 -> 去重（保留顺序）后的列表。"""
        if isinstance(v, list):
            out = []
            for x in v:
                if x and x not in out:
                    out.append(x)
            return out
        return [v] if v else []

    cn_idx: dict[str, set] = {}
    en_idx: dict[str, set] = {}
    en_to_cn: dict[str, list] = {}
    cn_to_en: dict[str, list] = {}
    for r in roles:
        cn_list = split_names(r.get("cn"))
        en_list = split_names(r.get("en"))
        cn_main = cn_list[0] if cn_list else ""
        en_main = en_list[0] if en_list else ""
        for c in cn_list:
            cn_idx.setdefault(c, set()).add(r["work"])
        for e in en_list:
            key = normalize_en_key(e)
            en_idx.setdefault(key, set()).add(r["work"])
            en_idx.setdefault(key.replace('_', '-'), set()).add(r["work"])
        if cn_main and en_main:
            # 规范名与所有别名都可触发补全，补全值统一取规范名（第一个）
            en_to_cn.setdefault(normalize_en_key(en_main), []).append((r["work"], cn_main))
            cn_to_en.setdefault(cn_main, []).append((r["work"], en_main))
            for c in cn_list:
                if c != cn_main:
                    cn_to_en.setdefault(c, []).append((r["work"], en_main))
            for e in en_list:
                if e != en_main:
                    key = normalize_en_key(e)
                    en_to_cn.setdefault(key, []).append((r["work"], cn_main))
                    en_to_cn.setdefault(key.replace('_', '-'), []).append((r["work"], cn_main))
    # 手工条目优先：同角色名下以手工标注的作品为准（含补全索引覆盖）
    for r in (manual_roles or []):
        cn_list = split_names(r.get("cn"))
        en_list = split_names(r.get("en"))
        cn_main = cn_list[0] if cn_list else ""
        en_main = en_list[0] if en_list else ""
        for c in cn_list:
            cn_idx[c] = {r["work"]}
            if en_main:
                cn_to_en[c] = [(r["work"], en_main)]
        for e in en_list:
            key = normalize_en_key(e)
            en_idx[key] = {r["work"]}
            en_idx[key.replace('_', '-')] = {r["work"]}
            if cn_main:
                en_to_cn[key] = [(r["work"], cn_main)]
                en_to_cn[key.replace('_', '-')] = [(r["work"], cn_main)]
    # 别名/变体展开（手工登记，优先级最高）：别名能确定作品，也能借助规范名补全
    for a in (aliases or []):
        work = a["work"]
        if a["kind"] == "cn":
            cn_idx.setdefault(a["alias"], set()).add(work)
            for w, e in cn_to_en.get(a["canonical"], []):
                if w == work:
                    cn_to_en.setdefault(a["alias"], []).append((w, e))
        elif a["kind"] == "en":
            key = normalize_en_key(a["alias"])
            en_idx.setdefault(key, set()).add(work)
            en_idx.setdefault(key.replace('_', '-'), set()).add(work)
            for w, c in en_to_cn.get(normalize_en_key(a["canonical"]), []):
                if w == work:
                    en_to_cn.setdefault(key, []).append((w, c))
                    en_to_cn.setdefault(key.replace('_', '-'), []).append((w, c))
    return cn_idx, en_idx, en_to_cn, cn_to_en


# ---------------------------------------------------------------------------
# 扫描：本仓库专用，严格两层
# ---------------------------------------------------------------------------
def get_target_dirs(path: str | None) -> list[Path]:
    roots = [Path(path).resolve()] if path else DEFAULT_ROOTS
    dirs: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        if root.name == "Models":
            for author in sorted(root.iterdir()):
                if not (author.is_dir() and re.fullmatch(r"\d{4}", author.name)):
                    continue
                for model in sorted(author.iterdir()):
                    if model.is_dir() and model.name != "previews":
                        dirs.append(model)
        else:
            for model in sorted(root.iterdir()):
                if model.is_dir() and model.name != "previews":
                    dirs.append(model)
    return sorted(dirs)


# ---------------------------------------------------------------------------
# 主流程
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
                       help="对照数据库目录（默认 .github/scripts/data/ysm-rename）")
    g_run.add_argument("--report", metavar="FILE", default="",
                       help="报告输出路径（默认写入系统临时目录）")

    g_db = parser.add_argument_group("知识库维护")
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

    if args.add:
        add_manual_entries(kb_path)
        return 0
    if args.alias:
        add_alias_entries(kb_path)
        return 0
    if args.delete:
        del_entries(kb_path)
        return 0
    if args.check:
        run_check(kb_path)
        return 0
    if args.suggest:
        run_suggest(kb_path)
        return 0
    if args.list:
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
