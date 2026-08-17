# -*- coding: utf-8 -*-
"""新命名解析规则：Token 化 + 数据库归类 + 重组。

替代 parse.py 的「格式化→分段→补丁」式解析：
- 按语言块 tokenize：下划线/连字符/无分隔/间隔号/空格 统一处理；
- 每个 token 用数据库归类（作品/角色/皮肤/评级/Unknown）；
- 按 <作品>_<中文角色>[_中文皮肤]_<英文角色>[_英文皮肤]_<评级> 重组。

与 parse.resolve_name 返回结构兼容，可无缝替换（02_rename 等调用方不改）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.kb.text import (  # noqa: E402
    has_cjk, init_caps, is_skin_cn, is_skin_en, normalize_en_key,
    normalize_work_name,
)
from lib.kb.parse import (  # noqa: E402
    GRADE_RE, EXTRA_WORK_ALIASES, get_work_canonical, role_names,
)

# 按语言块切分：连续 CJK+日文假名（含间隔号）一块；连续 ASCII（含内部 -/. 与数字）一块。
# 注意：`_` 是分隔符边界，不能吞进英文块（否则 `Mika-Misono_LA` 的评级、
# `Unknown_xxx` 的 Unknown 标记都会失效）。
# 日文假名（平假名/片假名）并入 CJK 块，使 長崎そよ 等日文名整体成一个 token。
# 数字+"号"（如 21号、1号）是编号后缀，整体成一个 token，避免拆成 21 + 号。
TOKEN_RE = re.compile(
    r'\d+号'
    r'|[\u4e00-\u9fff\u3040-\u30ff·・々]+'
    r'|[A-Za-z0-9][A-Za-z0-9.\-]*'
)

GRADE_TOKENS = {"LA", "LB", "LC", "LD"}
UNKNOWN_TOKENS = {"unknown", "待定"}
# 内容分级标签（大小写不敏感，输出统一全大写 NSFW/SFW，重组放评级前）
CONTENT_TAGS = {"nsfw", "sfw"}
CONTENT_CANON = {"nsfw": "NSFW", "sfw": "SFW"}
# 豁免 6.5b 降级的作品：角色无法穷举收录（原创等），前缀可信赖
NO_ROLE_VALIDATION_WORKS = {"OC"}


def tokenize(name: str) -> list[str]:
    """把文件夹名切成语义 token（语言块），保留英文内部连字符。"""
    return TOKEN_RE.findall(name)


# 第 1 步：名称格式化（整体匹配重构）。符号统一为 `_`、语言切换分段、
# 英文小写、末尾独立段剥离评级。产出匹配副本；原始名由调用方保留供重组定位。
_SYM_TO_UNDERSCORE_RE = re.compile(r"[\s\-_·・：:（）()，,。.、]+")
# 语言切换点（中文/假名 ↔ 英文数字）也是段边界，插入 `_`。
_CJK_EN_GAP_RE = re.compile(r"(?<=[\u4e00-\u9fff\u3040-\u30ff])(?=[A-Za-z0-9])"
                            r"|(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff\u3040-\u30ff])")
# 末尾独立段评级：前面是字符串开头或 `_`（如 `mika_la`、纯 `la`），
# 不匹配词内结尾（如 `amala` 的 la 前面不是边界）。
_TAIL_GRADE_RE = re.compile(r"(?:^|_)(la|lb|lc|ld)$")


def _segment_spans(name: str) -> list[tuple[str, int, int]]:
    """切段并记录每段在原始名中的 (文本, 原始起始, 原始结束)。

    符号（空白/连字符/下划线/间隔号/冒号/括号/标点）是段边界、不属于任何段；
    语言切换点（中文↔英文）也是段边界。
    """
    segs: list[tuple[str, int, int]] = []
    cur_start: int | None = None
    cur_kind = ""
    for i, ch in enumerate(name):
        if _SYM_TO_UNDERSCORE_RE.match(ch):
            if cur_start is not None:
                segs.append((name[cur_start:i], cur_start, i))
                cur_start, cur_kind = None, ""
            continue
        kind = "cjk" if has_cjk(ch) else "ascii"
        if cur_start is None:
            cur_start, cur_kind = i, kind
        elif cur_kind != kind:
            segs.append((name[cur_start:i], cur_start, i))
            cur_start, cur_kind = i, kind
    if cur_start is not None:
        segs.append((name[cur_start:len(name)], cur_start, len(name)))
    return segs


def format_name(name: str) -> tuple[str, str, list]:
    """第 1 步：名称格式化（匹配副本 + 段原始位置）。

    - 符号统一为 `_`（段边界）、语言切换分段、英文小写；
    - 末尾独立段剥离评级 LA/LB/LC/LD（大小写不敏感）。

    返回 (格式化副本, 评级, 段列表)。段列表元素 (原始文本, 原始起始, 原始结束)，
    供第 3 步重组成型时按原始位置归位残留词（如 xiao 与月雪宫子原始紧贴则合并）。
    """
    spans = _segment_spans(name)
    texts = [t.lower() for t, _s, _e in spans]
    grade = ""
    if texts:
        m = _TAIL_GRADE_RE.search(texts[-1])
        if m:
            grade = m.group(1).upper()
            texts = texts[:-1]
            spans = spans[:-1]
    fmt = "_".join(texts)
    return fmt, grade, spans


# ========== 整体匹配版（第 1~3 步重构：resolve_name3） ==========


def match_work(fmt: str) -> tuple[str, str]:
    """第 2 步：作品整体匹配。返回 (work, source)。

    - 短简称（≤3 且纯 ascii）：独立段匹配（get_work_canonical 逐段查）；
    - 长全称（中文/长名）：normalize 后子串匹配（复用 EXTRA_WORK_ALIASES）。
    均未命中返回 ('', 'none')。
    """
    best, best_len, source = "", 0, "none"
    for seg in fmt.split("_"):
        if len(seg) <= 3 and seg.isascii():
            w = get_work_canonical(seg)
            if w and len(seg) > best_len:
                best, best_len, source = w, len(seg), "prefix"
    nfmt = normalize_work_name(fmt)
    for nk, w in EXTRA_WORK_ALIASES.items():
        # 子串匹配只对长名/中文全称（短英文简称走独立段，避免 mikuba 里的 ba 误匹配）
        if (len(nk) >= 2 and (len(nk) >= 4 or has_cjk(nk))
                and nk in nfmt and len(nk) > best_len):
            best, best_len, source = w, len(nk), "substr"
    return best, source


def build_norm_role_index(roles: list[dict]) -> tuple[dict, dict]:
    """构建统一 `_` 后的角色索引：norm_zh -> set((zh, work))，norm_en 同理。"""
    role_zh: dict[str, set] = {}
    role_en: dict[str, set] = {}
    for r in roles:
        work = str(r.get("work", ""))
        for c in role_names(r, "zh"):
            nk = format_name(c)[0]
            if nk:
                role_zh.setdefault(nk, set()).add((c, work))
        for e in role_names(r, "en"):
            nk = format_name(e)[0]
            if nk:
                role_en.setdefault(nk, set()).add((e, work))
    return role_zh, role_en


def _seg_combos(segs: list[str]) -> list[tuple[int, int, str]]:
    """所有连续段组合：返回 (start_idx, end_idx, 组合串)。end_idx 不含。

    用于跨段角色名匹配（如 希儿_芙乐艾 是两段中文的组合）。组合内的段必须
    同语言（中文/假名 或 英文）——跨中英的组合（如 海太_umita）是误匹配，
    不生成，避免把「中文名+英文名」误当单个角色。
    """
    out: list[tuple[int, int, str]] = []
    for length in range(1, len(segs) + 1):
        for i in range(len(segs) - length + 1):
            parts = segs[i:i + length]
            kinds = {"cjk" if has_cjk(p) else "ascii" for p in parts}
            if len(kinds) == 1:
                out.append((i, i + length, "_".join(parts)))
    return out


def match_role(fmt: str, role_zh: dict, role_en: dict):
    """第 2 步：角色整体匹配。返回 (cn, en, works, kind, hit_key, hit_s, hit_e)。

    - 独立段/连续段组合精确匹配优先（zh 优先于 en），无命中再单段内子串兜底；
    - 最长优先（司霆惊蛰 优先于 惊蛰）；
    - cn/en 取命中的规范名；works 是归属作品集合；
      hit_key 是命中的 norm 名，hit_s/hit_e 是命中的段索引范围（供重组）。
    """
    segs = fmt.split("_")
    combo_lookup: dict[str, list] = {}
    for s, e, t in _seg_combos(segs):
        combo_lookup.setdefault(t, []).append((s, e))

    def scan(items: list) -> list:
        out = []
        for k, vs in items:
            if k in combo_lookup:
                for s, e in combo_lookup[k]:
                    out.append((len(k), k, vs, s, e))
        return out

    cands = scan(list(role_zh.items()))
    if not cands:
        cands = scan(list(role_en.items()))
    if not cands:
        # 单段内子串兜底（小花子 -> 花子）
        for k, vs in list(role_zh.items()):
            for i, seg in enumerate(segs):
                if k and len(k) >= 2 and k in seg and k != seg:
                    cands.append((len(k), k, vs, i, i + 1))
        if not cands:
            for k, vs in list(role_en.items()):
                for i, seg in enumerate(segs):
                    if k and len(k) >= 2 and k in seg and k != seg:
                        cands.append((len(k), k, vs, i, i + 1))
    if not cands:
        return "", "", set(), "", "", 0, 0
    cands.sort(reverse=True)
    _, k, vs, hit_s, hit_e = cands[0]
    kind = "zh" if k in role_zh else "en"
    works = {w for _n, w in vs}
    names = sorted(n for n, _w in vs)
    cn = names[0] if kind == "zh" else ""
    en = names[0] if kind == "en" else ""
    return cn, en, works, kind, k, hit_s, hit_e


def resolve_name3(name: str, roles: list[dict],
                  en_to_cn: dict | None = None, cn_to_en: dict | None = None,
                  work_skins: dict | None = None,
                  cn_alias: dict | None = None) -> dict:
    """整体匹配版解析器：第 1 步格式化 → 第 2 步作品/角色匹配 → 第 3 步重组。

    返回与 resolve_name2 兼容的结构。
    """
    orig = name
    notes: list[str] = []
    problems: list[str] = []
    candidate_skins: set[str] = set()
    filled: list[str] = []
    role_zh, role_en = build_norm_role_index(roles)

    # 第 1 步：格式化 + 去评级
    fmt, grade, spans = format_name(name)
    segs = fmt.split("_") if fmt else []
    # Unknown 前缀剥离（同步去掉首段）
    unknown_seen = False
    if segs and segs[0].lower() == "unknown":
        unknown_seen = True
        segs, spans = segs[1:], spans[1:]
        fmt = "_".join(segs)

    # 第 2 步：作品 + 角色匹配
    work, work_source = match_work(fmt)
    cn, en, role_works, kind, hit_key, hit_s, hit_e = match_role(fmt, role_zh, role_en)

    # 归属判定（作品-角色一致）
    conflict = False
    conflict_works: list[str] = []
    if work and work != "Unknown" and (cn or en):
        if role_works and work not in role_works:
            if len(role_works) == 1:
                new_work = next(iter(role_works))
                notes.append(f"work corrected: {work} -> {new_work}（角色归属）")
                work, work_source = new_work, "corrected"
            elif len(role_works) > 1:
                conflict = True
                conflict_works = sorted(role_works)
                work, work_source = "Unknown", "conflict"
    elif not work and (cn or en):
        if len(role_works) == 1:
            work, work_source = next(iter(role_works)), "kb"
        elif len(role_works) > 1:
            conflict = True
            conflict_works = sorted(role_works)
            work, work_source = "Unknown", "conflict"
    elif not work and not (cn or en):
        work, work_source = "Unknown", "none"

    # 6.5b：前缀作品但角色无命中 -> Unknown（OC 豁免）
    if (work_source == "prefix" and work and work != "Unknown"
            and work not in NO_ROLE_VALIDATION_WORKS and not cn and not en):
        notes.append(f"work unmatched: {work} has no known role, set Unknown")
        work, work_source = "Unknown", "unmatched"

    # 别名归一（规范名替换）
    if cn and cn_alias and cn in cn_alias:
        cn = _canon_cn(cn, cn_alias, work)

    # 中英文补全（重组前，使输出含补全后的名）
    if work and work != "Unknown":
        if cn and not en and cn_to_en:
            cands = {e for w, e in cn_to_en.get(cn, []) if w == work}
            if len(cands) == 1:
                en = init_caps(cands.pop())
                filled.append("EN auto-filled: " + en)
        if en and not cn and en_to_cn:
            cands = set()
            for kk in {normalize_en_key(en), normalize_en_key(en).replace("_", "-")}:
                for w, c in en_to_cn.get(kk, []):
                    if w == work:
                        cands.add(c)
            if len(cands) == 1:
                cn = cands.pop()
                filled.append("CN auto-filled: " + cn)

    # 第 3 步：残留段分类 + 重组（按原始位置归位）
    content_tag = ""
    cn_skin, en_skin = "", ""
    cn_seg: list[str] = []
    en_parts: list[str] = []
    for i, seg in enumerate(segs):
        low = seg.lower()
        if low in CONTENT_TAGS:
            content_tag = CONTENT_CANON[low]
            continue
        if is_skin_cn(seg, work, work_skins):
            cn_skin = seg if not cn_skin else cn_skin + "_" + seg
            continue
        if is_skin_en(seg, work, work_skins):
            en_skin = seg if not en_skin else en_skin + "-" + seg
            continue
        if hit_key and hit_s <= i < hit_e:
            # 角色段（可能跨多段）：只处理首段，段内剩余按原始顺序归位
            if i == hit_s:
                full = "_".join(segs[hit_s:hit_e])
                rem = full.replace(hit_key, "", 1) if hit_key in full else ""
                if rem and is_skin_cn(rem, work, work_skins):
                    # 角色段内剩余是皮肤词 -> 进皮肤位（末花泳装 -> 圣园未花_泳装）
                    cn_skin = rem if not cn_skin else cn_skin + "_" + rem
                    cn_seg.append(cn)
                elif rem:
                    cn_seg.append((cn + rem) if full.startswith(hit_key) else (rem + cn))
                else:
                    cn_seg.append(cn)
            continue
        if get_work_canonical(seg):
            continue  # 作品段（前缀/末尾标记/降级残留），命中已知作品即丢弃
        # 英文角色段已被 en/补全覆盖 -> 跳过（避免 Rosmontis/Shiroko 重复）
        if seg in role_en and work and work != "Unknown":
            if any(w == work for _n, w in role_en[seg]):
                continue
        # 未识别段：与角色段原始紧贴则进中文段原位（xiao 紧贴月雪宫子 -> xiao月雪宫子）
        if hit_key:
            if i == hit_s - 1 and spans[i][2] == spans[hit_s][1]:
                cn_seg.append(seg)
                continue
            if i == hit_e and spans[hit_e - 1][2] == spans[i][1]:
                cn_seg.append(seg)
                continue
        if has_cjk(seg):
            cn_seg.append(seg)
        else:
            en_parts.append(seg)

    # 未识别英文并入 en（- 连接）；已含在补全 en 里的段（如 Shiroko ⊂ Sunaookami-Shiroko）
    # 不重复并入
    if en_parts:
        enk = normalize_en_key(en) if en else ""
        kept = [p for p in en_parts
                if not (enk and normalize_en_key(p) and normalize_en_key(p) in enk)]
        if kept:
            extra = "-".join(kept)
            en = (en + "-" + extra) if en else extra
    if en:
        en = init_caps(en)

    cn_seg_str = "".join(cn_seg)
    new = work
    if cn_seg_str:
        new += "_" + cn_seg_str
        if cn_skin:
            new += "_" + cn_skin
    if en:
        new += "_" + en
        if en_skin:
            new += "-" + init_caps(en_skin)
    if content_tag:
        new += "_" + content_tag
    if grade:
        new += "_" + grade

    # 问题标记
    if not cn:
        problems.append("cn-name")
    if not en:
        problems.append("en-name")
    if (not conflict) and (not work or work == "Unknown") and (cn or en):
        problems.append("works")
    problems = list(dict.fromkeys(problems))

    status = "OK" if new == orig else "FIX"
    return {
        "original": orig, "new": new, "status": status, "notes": "; ".join(notes),
        "filled": "; ".join(filled), "work": work, "zh": cn, "en": en, "grade": grade,
        "cn_skin": cn_skin, "en_skin": en_skin, "conflict": conflict,
        "conflict_works": conflict_works, "work_source": work_source,
        "problems": problems, "candidate_skins": sorted(candidate_skins),
    }


def _extract_role_substr(tok: str, work: str, cn_idx: dict) -> tuple[str, str] | None:
    """在中文 token 内找最长角色子串（work 匹配或唯一作品归属）。

    返回 (角色名, 剩余段) 或 None（无法确定归属）。
    """
    if tok in cn_idx:
        return tok, ""
    cands = [rn for rn, works in cn_idx.items()
             if rn in tok and rn != tok
             and (work in works or not work or work == "Unknown")]
    if not cands:
        return None
    best = max(cands, key=len)
    best_works = cn_idx[best]
    if work in best_works:
        pass
    elif len(best_works) == 1 and (not work or work == "Unknown"):
        work = next(iter(best_works))
    else:
        return None
    if work in best_works:
        remainder = tok.replace(best, "", 1).strip("_·-")
        return best, remainder
    return None


def build_cn_alias(roles: list[dict]) -> dict[str, set[tuple[str, str]]]:
    """构建 中文别名 -> {(规范名, work)} 映射。

    角色条目 zh 数组首项为规范名、其余为别名；build_indexes 会把别名也注册进
    cn_idx，导致解析时别名段被误判为独立角色（如 南希露-网络魅影 中网络魅影）。
    这里返回别名→(规范名, work)，供 resolve_name2 归一/丢弃别名段。
    """
    out: dict[str, set[tuple[str, str]]] = {}
    for r in roles:
        work = str(r.get("work", ""))
        cn_list = role_names(r, "zh")
        if not cn_list:
            continue
        main = cn_list[0]
        for c in cn_list[1:]:
            out.setdefault(c, set()).add((main, work))
    return out


def _canon_cn(t: str, cn_alias: dict | None, work: str) -> str:
    """取角色名的规范中文名（别名 -> 规范名；非别名原样返回）。

    供重组阶段把命中的角色子串替换为标准名（如 花子 -> 浦和花子）。
    """
    if cn_alias and t in cn_alias:
        for main, w in cn_alias[t]:
            if w == work:
                return main
        uniq = {m for m, _w in cn_alias[t]}
        if len(uniq) == 1:
            return next(iter(uniq))
    return t


def _related(a: str, b: str) -> bool:
    """当前名 a 是否已与规范名 b 一致（应保留，不覆盖）。"""
    def fold(s: str) -> str:
        return normalize_en_key(s) if s.isascii() else s.replace(' ', '').replace('　', '')
    x, y = fold(a), fold(b)
    if not x or not y:
        return False
    return x == y or y in x


def resolve_name2(name: str, cn_idx: dict, en_idx: dict,
                  en_to_cn: dict | None = None, cn_to_en: dict | None = None,
                  work_skins: dict | None = None,
                  cn_alias: dict | None = None) -> dict:
    """新版名称解析：Token 化 + 数据库归类 + 重组。

    返回与 parse.resolve_name 兼容的结构（original/new/status/work/zh/en/
    grade/cn_skin/en_skin/conflict/notes/problems/filled/candidate_skins）。
    cn_alias：build_cn_alias 的产物，用于归一中文别名段（可选）。
    """
    orig = name
    notes: list[str] = []
    problems: list[str] = []
    candidate_skins: set[str] = set()
    filled: list[str] = []

    tokens = tokenize(name)

    # 1) 评级剥离（末尾 LA/LB/LC/LD）
    grade = ""
    if tokens and tokens[-1].upper() in GRADE_TOKENS:
        grade = tokens[-1].upper()
        tokens = tokens[:-1]

    # 2) Unknown / 待定 前缀剥离
    unknown_seen = False
    if tokens and tokens[0].lower() in UNKNOWN_TOKENS:
        unknown_seen = True
        tokens = tokens[1:]

    # 3) 作品前缀识别：首段 ASCII 累积拼接（多词作品名如 Food Girls、Sun Shower
    #    用空格拼接）、中文作品全称单独查；取最长命中的已知作品键。
    #    未命中已知作品但首段是 ASCII 时，保留首段作作品候选（不丢信息）。
    work = ""
    work_source = "none"
    best_work = ""
    best_len = 0
    ascii_tokens: list[str] = []
    acc = ""
    for i, t in enumerate(tokens):
        if has_cjk(t):
            canon = get_work_canonical(t)
            if canon and not best_work:
                best_work = canon
                best_len = i + 1
            break
        ascii_tokens.append(t)
        acc = (acc + " " if acc else "") + t
        canon = get_work_canonical(acc)
        if canon:
            best_work = canon
            best_len = i + 1
    if (best_work
            and (not ascii_tokens
                 or re.search(re.escape(ascii_tokens[0]) + r'[_\- ]', name))):
        # 命中已知作品：中文全称命中（ascii_tokens 空）直接采用；
        # ASCII 前缀命中需首段后跟分隔符（_/-/空格）才算独立作品段。
        # 连写情况如 WW×2077（'WW' 后是 ×）不是独立段，交给角色反查。
        work = best_work
        work_source = "prefix"
        prefix_end = best_len
    elif (ascii_tokens and any(has_cjk(t) for t in tokens[1:])
          and re.search(re.escape(ascii_tokens[0]) + r'[_\- ]', name)):
        # 未命中已知作品，但首段是 ASCII 且后跟分隔符（_/-/空格）再接内容：
        # 保留首段作作品候选（如 TTKP_苦命鸳鸯、mh_天慧龙、Sun Shower）。
        # 首段 ASCII 紧贴中文/括号（如 C酱 的 C、MK011(米莉安) 的 MK011）
        # 是角色名的一部分，不当作作品。
        work = ascii_tokens[0]
        work_source = "prefix"
        prefix_end = 1
    else:
        prefix_end = 0
    rest = tokens[prefix_end:]

    # 4) rest 角色/皮肤归类（作品前缀之后的 token）
    cn_role_exact: set[str] = set()
    cn_alias_hits: dict[str, set] = {}
    en_role_exact: set[str] = set()
    skin_tokens: set[str] = set()
    cn_pending: list[str] = []
    en_pending: list[str] = []
    content_tag = ""  # 内容分级标签（NSFW/SFW），重组放评级前
    cn_from_kb = False  # cn 是否来自数据库命中（精确/子串），用于前缀作品校验
    for t in rest:
        if has_cjk(t):
            if t in cn_idx:
                # 区分规范名与别名：别名段不直接算角色，稍后归一/丢弃
                if cn_alias and t in cn_alias:
                    cn_alias_hits[t] = cn_alias[t]
                else:
                    cn_role_exact.add(t)
            elif is_skin_cn(t, "", work_skins):
                skin_tokens.add(t)
            else:
                cn_pending.append(t)
        else:
            low = t.lower()
            if low in CONTENT_TAGS:
                # 内容分级标签（nsfw/sfw，大小写不敏感）：独立成段，不参与
                # 角色/皮肤归类，重组时统一大写放评级前。
                content_tag = CONTENT_CANON[low]
                continue
            key = normalize_en_key(t)
            if key and key in en_idx:
                # 同一英文名不同写法（大小写/连字符）只记一次，
                # 避免 HK416 与 Hk416 误判为 multiple en roles
                if not any(normalize_en_key(e) == key for e in en_role_exact):
                    en_role_exact.add(t)
            elif is_skin_en(t, "", work_skins):
                skin_tokens.add(t)
            else:
                en_pending.append(t)

    # 4.5) 别名归一：同条目规范名段已命中则别名是冗余（丢弃）；
    #      别名段单独出现时归一到规范名（跨作品同名歧义保留待人工）。
    for t, mains in cn_alias_hits.items():
        mains = list(mains)
        if any(m in cn_role_exact for m, _w in mains):
            continue  # 规范名已在，别名冗余
        if work and work != "Unknown":
            same_work = [m for m, w in mains if w == work]
            if len(same_work) == 1:
                cn_role_exact.add(same_work[0])
                continue
        uniq_main = {m for m, _w in mains}
        if len(uniq_main) == 1:
            cn_role_exact.add(next(iter(uniq_main)))
        else:
            cn_pending.append(t)  # 跨作品同名别名歧义，保持待人工

    # 5) 中文角色提取：精确命中 + 子串提取（仅 work 已定或唯一归属）
    cn = ""
    cn_skin = ""
    if len(cn_role_exact) == 1:
        cn = next(iter(cn_role_exact))
        cn_from_kb = True
    elif len(cn_role_exact) > 1:
        cn = ""
        notes.append("multiple cn roles: " + "/".join(sorted(cn_role_exact)))
        problems.append("other")
    if not cn and cn_pending and cn_idx:
        # 子串提取：work 未定/Unknown 时，唯一作品的子串命中可确定归属
        # （如 Unknown_梅莉 -> 梅；Unknown_大明酒狐 -> 酒狐；Unknown_末花泳装 -> 末花）。
        for tok in list(cn_pending):
            m = _extract_role_substr(tok, work if work != "Unknown" else "", cn_idx)
            if m:
                r, rem = m
                rw = cn_idx[r]
                if not work or work == "Unknown":
                    if len(rw) == 1:
                        work = next(iter(rw))
                        work_source = "kb"
                    else:
                        continue  # 跨作品同名，不剥离
                if work in rw:
                    if not cn:
                        # 子串提取的角色（用于反查/补全；显示段在重组时重建为
                        # 规范名 + 剩余词原位，如 小花子 -> 小浦和花子）
                        cn = r
                        cn_from_kb = True
                    if rem and not cn_skin:
                        if is_skin_cn(rem, work, work_skins):
                            cn_skin = rem  # 已收录皮肤词正常拆
                        # 未收录皮肤词（酱/小小/小）不在此拼：重组时保留原位
                    cn_pending.remove(tok)
    # 未归类的剩余中文段：cn 为空时保留第一段为角色名（保持原样，待收录），
    # 其余作为皮肤候选（供收录，如 `月雪宫子兔女郎` 拆出角色后的剩余）。
    for tok in cn_pending:
        if not cn:
            cn = tok
        elif tok != cn and tok != cn_skin:
            candidate_skins.add(tok)
            if not cn_skin:
                cn_skin = tok

    # 6) 英文角色提取
    en = ""
    en_skin = ""
    if len(en_role_exact) == 1:
        en = next(iter(en_role_exact))
    elif len(en_role_exact) > 1:
        # 多个英文段命中：若都指向同一角色（经 en_to_cn 归一），取规范英文名，
        # 避免 Hk416+Klukai（同一角色主名+别名）误判为冲突。
        uniq_cn: set[str] = set()
        for e in en_role_exact:
            cands: set[str] = set()
            k = normalize_en_key(e)
            for kk in {k, k.replace('_', '-')}:
                for w, c in (en_to_cn or {}).get(kk, []):
                    if w == work:
                        cands.add(c)
            if len(cands) == 1:
                uniq_cn.add(next(iter(cands)))
        if len(uniq_cn) == 1:
            cn_main = next(iter(uniq_cn))
            cands = {enm for w, enm in (cn_to_en or {}).get(cn_main, []) if w == work}
            en = next(iter(cands)) if len(cands) == 1 else next(iter(en_role_exact))
            en = init_caps(en)
        else:
            notes.append("multiple en roles")
            problems.append("other")
    # 英文 pending 段：若仅一段且是皮肤词则归皮肤，否则保留（可能是英文名写法）
    if not en and en_pending:
        non_skin = [t for t in en_pending if not is_skin_en(t, work, work_skins)]
        skin_part = [t for t in en_pending if is_skin_en(t, work, work_skins)]
        if non_skin:
            en = "-".join(non_skin)
        if skin_part:
            en_skin = "-".join(skin_part)
    # 英文段内部剥离尾部内容标签（Miku-Rabbithole-Sfw -> Miku-Rabbithole + SFW）。
    # nsfw/sfw 总在段尾，故先于皮肤剥离。
    if en and "-" in en:
        head, tail = en.rsplit("-", 1)
        if head and tail and tail.lower() in CONTENT_TAGS:
            en = head
            content_tag = CONTENT_CANON[tail.lower()]
    # 英文段内部剥离尾部皮肤（Hatsune-Miku-Swimsuit -> Hatsune-Miku + Swimsuit）
    if en and "-" in en:
        head, tail = en.rsplit("-", 1)
        if head and tail and is_skin_en(tail, work, work_skins):
            en = head
            en_skin = tail if not en_skin else en_skin + "-" + tail

    # 6b) 作品反查：前缀未识别作品时，从精确/提取的角色反查（唯一命中才确定）
    conflict = False
    conflict_works: list[str] = []
    if not work or work == "Unknown":
        hits: set[str] = set()
        for c in cn_role_exact:
            hits |= cn_idx.get(c, set())
        for e in en_role_exact:
            key = normalize_en_key(e)
            hits |= en_idx.get(key, set())
            hits |= en_idx.get(key.replace('_', '-'), set())
        if cn and cn in cn_idx:
            hits |= cn_idx[cn]
        if en:
            for cand in {normalize_en_key(en), normalize_en_key(en).replace('_', '-')}:
                hits |= en_idx.get(cand, set())
        if len(hits) == 1:
            work = next(iter(hits))
            work_source = "kb"
        elif len(hits) > 1:
            conflict = True
            conflict_works = sorted(hits)
            work = "Unknown"
            work_source = "conflict"
        elif not work:
            work = "Unknown"
            work_source = "none"

    # 6.5) 前缀作品与角色归属校验（保守版）：
    #      仅当角色中英文都精确命中、且两者归属一致指向非前缀作品时，才纠正前缀
    #      （作者前缀写错的强证据，如 AveMujica_千早爱音_Chihaya-Anon -> MyGO）。
    #      跨作品同名（NEKOPARA_红豆/AK 红豆、BA_爱丽丝/Nikke 爱丽丝）或只有单语言
    #      命中时保守不纠正，避免知识库不完整（某作品角色未收录）导致的误伤。
    if work_source == "prefix" and best_work and cn_role_exact and en_role_exact:
        cn_works: set[str] = set()
        for c in cn_role_exact:
            cn_works |= cn_idx.get(c, set())
        en_works: set[str] = set()
        for e in en_role_exact:
            key = normalize_en_key(e)
            en_works |= en_idx.get(key, set())
            en_works |= en_idx.get(key.replace('_', '-'), set())
        if cn_works and en_works and cn_works == en_works and work not in cn_works:
            if len(cn_works) == 1:
                new_work = next(iter(cn_works))
                notes.append(f"work corrected: {work} -> {new_work}（角色归属）")
                work = new_work
                work_source = "corrected"
            elif len(cn_works) > 1:
                conflict = True
                conflict_works = sorted(cn_works)
                notes.append("prefix work conflicts with role works: "
                             + "/".join(sorted(cn_works)))
                work = "Unknown"
                work_source = "conflict"

    # 6.5b) 前缀作品但角色无任何数据库命中 -> Unknown。
    #       （数据驱动：作者前缀标注的作品里查无此角色，宁缺毋滥标 Unknown，
    #        待数据库逐步完善后自动归位；命中但归属他作的情况仍走 6.5）
    #       OC（原创）豁免：角色名作者自创无法穷举收录，前缀可信赖，不降级。
    if (work_source == "prefix" and work and work != "Unknown"
            and work not in NO_ROLE_VALIDATION_WORKS
            and not cn_from_kb and not cn_role_exact and not en_role_exact):
        notes.append(f"work unmatched: {work} has no known role, set Unknown")
        work = "Unknown"
        work_source = "unmatched"

    # 6c) 皮肤 token 输出：中文皮肤词 → cn_skin，英文皮肤词 → en_skin
    for s in sorted(skin_tokens):
        if has_cjk(s):
            cn_skin = s if not cn_skin else cn_skin + "_" + s
        else:
            en_skin = s if not en_skin else en_skin + "-" + s

    # 7) 英文名规范化 + 中英文补全（与旧逻辑一致）
    if en:
        en = init_caps(en)
    if work and work != "Unknown":
        if cn and not en and cn_to_en:
            cands = {e for w, e in cn_to_en.get(cn, []) if w == work}
            if len(cands) == 1:
                en = cands.pop()
                filled.append("EN auto-filled: " + en)
                en = init_caps(en)
        if en and not cn and en_to_cn:
            cands: set[str] = set()
            k1 = normalize_en_key(en)
            for k in {k1, k1.replace('_', '-')}:
                for w, c in en_to_cn.get(k, []):
                    if w == work:
                        cands.add(c)
            if len(cands) == 1:
                cn = cands.pop()
                filled.append("CN auto-filled: " + cn)
        if cn and en and cn_to_en:
            cands = {e for w, e in cn_to_en.get(cn, []) if w == work}
            if len(cands) == 1:
                cand = cands.pop()
                if not _related(en, cand):
                    en = cand
                    filled.append("EN standardized: " + cand)
                    en = init_caps(en)
        if cn and en and en_to_cn:
            cands = set()
            k1 = normalize_en_key(en)
            for k in {k1, k1.replace('_', '-')}:
                for w, c in en_to_cn.get(k, []):
                    if w == work:
                        cands.add(c)
            if len(cands) == 1:
                cand = cands.pop()
                if not _related(cn, cand):
                    cn = cand
                    filled.append("CN standardized: " + cand)

    # 7.5) 只有皮肤词而无角色名：把皮肤提升为角色名（保留信息，如 Unknown_兔女郎）。
    #      命名模板要求皮肤依附于角色；纯皮肤（无角色）时不丢弃，降级为角色名。
    if not cn and not en and (cn_skin or en_skin):
        if cn_skin:
            cn = cn_skin
            cn_skin = ""
        if en_skin:
            en = en_skin
            en_skin = ""
        notes.append("no role; skin kept as role name")

    # 8) 重组输出（保留原顺序：角色/未识别词原位替换，皮肤移到皮肤位）
    #    中文角色段按原 rest token 顺序重建：命中的角色子串替换为规范名、
    #    未识别词（如 xiao/小）保留原位、皮肤与作品标记 token 抽离。
    cn_seg: list[str] = []
    for t in rest:
        if t == grade:
            continue
        if has_cjk(t):
            if is_skin_cn(t, work, work_skins):
                continue  # 皮肤已收集到 cn_skin
            if t in cn_idx:
                cn_seg.append(_canon_cn(t, cn_alias, work))
            else:
                m = _extract_role_substr(t, work if work != "Unknown" else "", cn_idx)
                if m and work in cn_idx[m[0]]:
                    r, rem = m
                    std = _canon_cn(r, cn_alias, work)
                    if rem and is_skin_cn(rem, work, work_skins):
                        # 剩余是已收录皮肤词：只取角色标准名（皮肤已抽到 cn_skin）
                        cn_seg.append(std)
                    else:
                        # 剩余词保留原位：角色在前 -> 标准名+剩余；剩余在前 -> 剩余+标准名
                        cn_seg.append((std + rem) if t.startswith(r) else (rem + std))
                else:
                    cn_seg.append(t)  # 未识别中文，原样保留
        else:
            if t.lower() in CONTENT_TAGS:
                continue  # 内容分级标签（独立段），重组时放评级前
            key = normalize_en_key(t)
            if key and key in en_idx:
                continue  # 角色英文在 en 位
            if is_skin_en(t, work, work_skins):
                continue  # 皮肤
            if work and work != "Unknown" and get_work_canonical(t):
                # 作品标记 token：命中任意已知作品（缩写/全称）即丢弃。
                # 作品应只出现在前缀；rest 中残留（如 xiao月雪宫子BA 的末尾 BA、
                # HI3遐蝶 的 HI3）是作者重复标记/误标，不并入角色段。
                # 未识别英文（xiao 等）不是作品，仍保留原位。
                continue
            # 英文段已消费（en/en_skin/内容标签拆分后原始 token 完整保留）时不再并入
            # 中文段。覆盖三类：
            #  - Shiroko 是标准化 en=Sunaookami-Shiroko 的一部分（endswith/startswith）
            #  - Miku-Rabbithole 拆为 en+en_skin（含皮肤段）
            #  - Merlin-Nsfw 拆为 en+NSFW（含内容标签段）
            if en:
                enk = normalize_en_key(en)
                tk = normalize_en_key(t)
                if (tk == enk or enk.endswith("-" + tk) or enk.startswith(tk + "-")):
                    continue
                if en_skin and tk == normalize_en_key(en_skin):
                    continue
            if "-" in t:
                segs = t.split("-")
                if any(s.lower() in CONTENT_TAGS for s in segs) \
                   or any(is_skin_en(s, work, work_skins) for s in segs):
                    continue
            cn_seg.append(t)  # 未识别英文（xiao）保留到中文段
    cn_seg_str = "".join(cn_seg)
    if cn and cn in (cn_alias or {}):
        cn = _canon_cn(cn, cn_alias, work)

    new = work
    if cn_seg_str:
        new += "_" + cn_seg_str
        if cn_skin:
            new += "_" + cn_skin
    if en:
        new += "_" + en
        if en_skin:
            new += "-" + en_skin
    if content_tag:
        new += "_" + content_tag
    if grade:
        new += "_" + grade

    # 9) 问题标记
    if not cn:
        problems.append("cn-name")
    if not en:
        problems.append("en-name")
    if (not conflict) and (not work or work == "Unknown") and (cn or en):
        problems.append("works")
    problems = list(dict.fromkeys(problems))

    status = "OK" if new == orig else "FIX"
    return {
        "original": orig, "new": new, "status": status, "notes": "; ".join(notes),
        "filled": "; ".join(filled), "work": work, "zh": cn, "en": en, "grade": grade,
        "cn_skin": cn_skin, "en_skin": en_skin, "conflict": conflict,
        "conflict_works": conflict_works, "work_source": work_source,
        "problems": problems, "candidate_skins": sorted(candidate_skins),
    }
