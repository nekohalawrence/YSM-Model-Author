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
)
from lib.kb.parse import (  # noqa: E402
    GRADE_RE, get_work_canonical, role_names,
)

# 按语言块切分：连续 CJK+日文假名（含间隔号）一块；连续 ASCII（含内部 -/. 与数字）一块。
# 注意：`_` 是分隔符边界，不能吞进英文块（否则 `Mika-Misono_LA` 的评级、
# `Unknown_xxx` 的 Unknown 标记都会失效）。
# 日文假名（平假名/片假名）并入 CJK 块，使 長崎そよ 等日文名整体成一个 token。
TOKEN_RE = re.compile(
    r'[\u4e00-\u9fff\u3040-\u30ff·・々]+'
    r'|[A-Za-z0-9][A-Za-z0-9.\-]*'
)

GRADE_TOKENS = {"LA", "LB", "LC", "LD"}
UNKNOWN_TOKENS = {"unknown", "待定"}


def tokenize(name: str) -> list[str]:
    """把文件夹名切成语义 token（语言块），保留英文内部连字符。"""
    return TOKEN_RE.findall(name)


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
            key = normalize_en_key(t)
            if key and key in en_idx:
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
                        cn = r
                    if rem and not cn_skin:
                        cn_skin = rem
                        if not is_skin_cn(rem, work, work_skins):
                            candidate_skins.add(rem)
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

    # 8) 重组输出
    new = work
    if cn:
        new += "_" + cn
        if cn_skin:
            new += "_" + cn_skin
    if en:
        new += "_" + en
        if en_skin:
            new += "-" + en_skin
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
