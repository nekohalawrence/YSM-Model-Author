# -*- coding: utf-8 -*-
"""kb 名称解析与知识库构建：resolve_name / build_kb（原 kb_tool.py 核心逻辑）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 把 .github/scripts 加回 sys.path，保证 lib/ 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib import models as lib_models
from lib.kb.text import (  # noqa: E402
    CN_SKIN_RE, EN_TAIL_RE, MIXED_SEG_RE, TOUHOU_PREFIX_RE,
    has_cjk, init_caps, is_skin_cn, is_skin_en, normalize_en_key, normalize_work_name,
)

GRADE_RE = lib_models.GRADE_SUFFIX_RE

# 无分隔的中英混合段（如「初音miku」「miku初音」）按中英边界拆分
CN_EN_FUSED_RE = re.compile(r"^([\u4e00-\u9fff]+)([A-Za-z][A-Za-z0-9]*)$")
EN_CN_FUSED_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)([\u4e00-\u9fff]+)$")
# 作品缩写紧贴中文 + "-"英文（如 HI3刻律德菈-Cerydra）：ASCII 前缀是已知作品缩写
# 时才拆分（get_work_canonical 命中），否则保持 mixed segment 待人工。
EN_CN_EN_SEG_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9]*)([\u4e00-\u9fff·]+)-(?=[A-Za-z])([A-Za-z][A-Za-z0-9-]*)$")
# en 尾部版本号（MikU1.0 -> MikU；v3.1 -> 空）
EN_VERSION_RE = re.compile(r"[vV]?\d+(?:\.\d+)*$")

# 运行时由 works 数据（含 README 同步）派生的作品名 -> 键 映射（去标点归一化后）
EXTRA_WORK_ALIASES: dict[str, str] = {}


def set_work_aliases(aliases: dict[str, str]) -> None:
    """写入作品名 -> 键 映射（由 sync.build_work_index 调用，替代跨模块改全局）。"""
    EXTRA_WORK_ALIASES.clear()
    EXTRA_WORK_ALIASES.update(aliases)


def _work_fuzzy_hits(seg: str) -> set[str]:
    """宽松前缀匹配的候选键集合：seg 归一化后长度 >=3，且恰为某作品某个名称的前缀。

    供作品别名归一使用（resolve_name 的 work 归一环节）：唯一命中才自动归一，
    多候选（如 Red 同时是 Red-Alert-2/3、Redo of Healer 等名称的前缀）不归一，
    仅提示人工确认，避免误伤。
    """
    key = normalize_work_name(seg)
    if len(key) < 3:
        return set()
    return {w for n, w in EXTRA_WORK_ALIASES.items() if n.startswith(key)}


def get_work_canonical(seg: str, fuzzy: bool = False) -> str | None:
    """作品名 -> 规范键（完全依赖外置 works 数据构建的 EXTRA_WORK_ALIASES）。

    fuzzy=True 时先做精确匹配，失败再尝试宽松前缀匹配（作品别名归一用）：
    唯一命中才返回键；多候选返回 None（由调用方决定是否提示人工）。
    """
    exact = EXTRA_WORK_ALIASES.get(normalize_work_name(seg))
    if exact is not None or not fuzzy:
        return exact
    hits = _work_fuzzy_hits(seg)
    if len(hits) == 1:
        return next(iter(hits))
    return None


def role_names(r: dict, field: str) -> list[str]:
    """取角色条目某字段的名称列表（字符串 -> 单元素列表；数组去空保序）。"""
    v = r.get(field)
    if isinstance(v, list):
        out = []
        for x in v:
            if x and x not in out:
                out.append(x)
        return out
    return [v] if v else []


def _related(a: str, b: str) -> bool:
    """当前名 a 是否已与规范名 b 一致（应保留，不覆盖）。

    方向性判断（en 归一化、cn 去空白）：
    - a == b：完全一致 -> 相关，不覆盖；
    - b in a：当前名 = 规范名 + 皮肤/后缀（如 Miku-Halloween 含规范 Miku）
      -> 相关，不覆盖（保护皮肤/复合名）；
    - a in b：当前名是规范名的简称/别名（如 初音 ⊂ 初音未来）
      -> 不相关，应标准化为完整规范名（补全中英文名）。
    """

    def fold(s: str) -> str:
        return normalize_en_key(s) if s.isascii() else s.replace(' ', '').replace('　', '')

    x, y = fold(a), fold(b)
    if not x or not y:
        return False
    return x == y or y in x


def resolve_name(name: str, cn_idx: dict, en_idx: dict,
                 en_to_cn: dict | None = None, cn_to_en: dict | None = None,
                 work_skins: dict | None = None) -> dict:
    """把一个文件夹名解析为 (作品, 中文名, 英文名, 评定等级) 结构。

    cn_idx/en_idx 为 build_indexes 构建的名称索引；en_to_cn/cn_to_en 用于
    作品已确定但缺中/英文名时的知识库补全与"标准化"（把已存在的非标准名，
    如拼音 Chuyin，替换为规范名 Miku）。
    返回 dict 含 status/new/notes 等。"""
    orig = name
    grade = ""
    manual: list[str] = []
    # 结构化问题标签（用于问题级计数）：works / cn-name / en-name / conflict / other
    problems: list[str] = []
    # 识别出的候选皮肤词（不在皮肤表，供调用方自动收录进 skin_tags.json）
    candidate_skins: set[str] = set()

    m = GRADE_RE.search(name)
    if m:
        grade = m.group(1).upper()
        name = name[: m.start()]
    # 符号格式化（先做，再进行后续字段归属判断）：
    # 中文间隔号/顿号/逗号/冒号等统一为 `_` 分隔符，
    # 如 `泠鸢·登门喜鹊` -> `泠鸢_登门喜鹊`、`初音Miku: 兔女郎` -> `初音Miku_ 兔女郎`。
    # 空格不在此处转换（英文名内部空格如 Katō Megumi 需保留，由段内拆分处理）。
    name = re.sub(r"[·・、，,:：;；]", "_", name)
    name = name.strip().rstrip("_- ")
    segments = [s.strip() for s in name.split("_")]
    segments = [s for s in segments if s]

    if not segments:
        return {"original": orig, "new": "", "status": "SKIP", "notes": "empty name",
                "work": "", "zh": "", "en": "", "grade": grade, "work_source": "none",
                "candidate_skins": []}

    work = ""
    work_source = "none"
    cn = ""
    cn_skin = ""
    en = ""
    en_skin = ""

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
    elif re.match(r"^[A-Za-z]", first) and not has_cjk(first):
        # ASCII 首段：若单段不是作品键，尝试拼后续连续 ASCII 段查作品
        # （如 Ash_Arms -> asharms 命中 works 里的 "Ash-Arms"；Azur_Lane -> AL）
        canon = None
        consumed = 1
        merged = first
        for seg in rest:
            if has_cjk(seg):
                break
            merged += seg
            consumed += 1
            if (c := get_work_canonical(merged)):
                canon = c
                break
        if canon:
            work = canon
            work_source = "prefix"
            rest = rest[consumed - 1:]
        elif rest_has_cjk and normalize_en_key(first) not in en_idx:
            # ASCII 段 + 后续有中文段 -> 视为作品名（除非该 ASCII 是知识库中已知的英文角色名）
            work = first
            work_source = "prefix"
        else:
            rest = segments
    else:
        rest = segments

    # Unknown 前缀（或待定）后紧跟的作品缩写段：识别为作品并剥离，如
    # Unknown_AKE_Endministrator_Female -> work=AKE, 角色部分 Endministrator_Female
    # 注意：first 是 "Unknown" 等待定标记时，else 分支会把首段也放回 rest，
    # 需先跳过该标记段，再查后续的作品缩写（否则会把 "Unknown" 当角色名）。
    if (not work or work == "Unknown") and rest:
        if normalize_work_name(rest[0]) in ("unknown", "待定"):
            rest = rest[1:]
        w0 = get_work_canonical(rest[0]) if rest else None
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
                    # 无分隔的中英混合段（如「初音miku」）-> 按中英边界拆分
                    m = CN_EN_FUSED_RE.match(seg) or EN_CN_FUSED_RE.match(seg)
                    if m:
                        a, b = m.group(1), m.group(2)
                        if has_cjk(a):   # 中文在前：a=cn, b=en
                            cjk_segs.append(a)
                            en_segs.append(b)
                        else:            # 英文在前：a=en, b=cn
                            en_segs.append(a)
                            cjk_segs.append(b)
                    else:
                        # 作品缩写紧贴中文 + "-"英文（如 HI3刻律德菈-Cerydra）：
                        # ASCII 前缀是已知作品缩写才拆，否则保持待人工
                        m2 = EN_CN_EN_SEG_RE.match(seg)
                        canon = get_work_canonical(m2.group(1)) if m2 else None
                        if (m2 and canon
                                and (not work or work == "Unknown" or work == canon)):
                            work = canon
                            work_source = "prefix"
                            cjk_segs.append(m2.group(2))
                            en_segs.append(m2.group(3))
                        else:
                            cjk_segs.append(seg)
                            manual.append("mixed segment unresolved: " + seg)
                            problems.append("other")
            else:
                cjk_segs.append(seg)
        else:
            en_segs.append(seg)

    if cjk_segs:
        # 段内再按空白/冒号拆成 token：兼容空格/冒号分隔的旧命名
        # （如 `BA_枣 伊吕波：泳装` -> 枣 / 伊吕波 / 泳装）。
        # had_inner_split：是否发生了段内拆分（空格/冒号）——这是"旧命名残留"的
        # 特征，只有此时才做知识库角色名过滤；下划线分隔的规范段（如
        # `小鸟游星野_常服`、`末影人娘_塔尔薇`）不做过滤，避免误丢皮肤词/未收录角色名。
        had_inner_split = False
        cjk_tokens: list[str] = []
        for seg in cjk_segs:
            parts = [t for t in re.split(r"[\s：:]+", seg) if t]
            if len(parts) > 1:
                had_inner_split = True
            cjk_tokens.extend(parts)
        cn_raw = "_".join(cjk_tokens)
        m = CN_SKIN_RE.match(cn_raw)
        if m:
            cn = m.group(1)
            cn_skin = m.group(2)
        else:
            cn = cn_raw
            # 容错：`_` 连接的中文皮肤段（历史写法，如「阿米娅_泳装」「伽摩_泳装」），
            # 用皮肤词表把末尾皮肤词剥离为皮肤（输出仍规范为 `-` 连接）。
            if len(cjk_tokens) > 1 and is_skin_cn(cjk_tokens[-1], work, work_skins):
                cn_skin = cjk_tokens[-1]
                cn = "_".join(cjk_tokens[:-1])
        # 知识库 CJK 角色名匹配（仅限空格/冒号拆分的旧命名残留，如 `枣 伊吕波`）：
        # 用知识库把命中的角色名挑出来，未命中 token（如姓氏「枣」）丢弃、
        # 皮肤词归为皮肤：BA_枣 伊吕波：泳装 -> cn=伊吕波, cn_skin=泳装。
        # 下划线分隔的规范段不触发，避免误丢常服/神装等皮肤词或未收录角色名。
        if (had_inner_split and work and work != "Unknown"
                and len(cjk_tokens) > 1 and cn_idx):
            role_tokens = [t for t in cjk_tokens if not is_skin_cn(t, work, work_skins)]
            matched = [t for t in role_tokens
                       if cn_idx.get(t) and work in cn_idx[t]]
            if len(matched) == 1:
                dropped = [t for t in role_tokens if t != matched[0]]
                if dropped:
                    manual.append("kb CJK filter: dropped "
                                  + ", ".join(dropped))
                    problems.append("other")
                cn = matched[0]
                skins = [t for t in cjk_tokens if is_skin_cn(t, work, work_skins)]
                if skins:
                    cn_skin = skins[0]
        # 皮肤识别（2026-08-15 增强）：CJK 多段中，若恰好一段命中角色库（cn_idx
        # 含当前 work），则其余中文段为皮肤——已知皮肤词直接收，未知中文段作为
        # 候选皮肤（candidate_skins，供自动收录进 skin_tags.json）。
        # 如 `泠鸢_登门喜鹊`（泠鸢是 OC 角色）-> cn=泠鸢, cn_skin=登门喜鹊；
        # `黎歌_国风`（黎歌未收录）-> 无角色命中，保持 multiple CJK 待人工。
        if (work and work != "Unknown" and len(cjk_tokens) > 1 and cn_idx
                and not cn_skin):
            role_hits = [t for t in cjk_tokens
                         if cn_idx.get(t) and work in cn_idx[t]]
            if len(role_hits) == 1:
                role = role_hits[0]
                others = [t for t in cjk_tokens if t != role]
                # 其余段都非角色（cn_idx 未命中当前 work）才安全剥离为皮肤
                if others and all(not (cn_idx.get(t) and work in cn_idx[t])
                                  for t in others):
                    cn = role
                    cn_skin = others[0]
                    for s in others:
                        if not is_skin_cn(s, work, work_skins):
                            candidate_skins.add(s)
                    if len(others) > 1:
                        manual.append("multiple CJK segments")
                        problems.append("other")
        # 段内角色名提取（2026-08-15）：CJK 段未精确命中角色，但包含某角色名
        # 子串（最长优先）时，提取角色名 + 剩余段为皮肤/形态词。
        # 如 `大明酒狐` -> 角色=酒狐 + 剩余=大明；`神秘酒狐` -> 酒狐 + 神秘。
        # work 未定时，唯一作品的命中可确定归属；多作品同名不剥离（保持待人工）。
        if (cn and not cn_skin and cn_idx and cn not in cn_idx):
            cand_names = [rn for rn, works in cn_idx.items()
                          if rn in cn and rn != cn
                          and (work in works or work == "Unknown")]
            if cand_names:
                best = max(cand_names, key=len)
                best_works = cn_idx[best]
                if work in best_works:
                    pass
                elif len(best_works) == 1 and (not work or work == "Unknown"):
                    work = next(iter(best_works))
                    work_source = "kb"
                if work in best_works:
                    remainder = cn.replace(best, "", 1).strip("_·-")
                    if remainder:
                        cn = best
                        cn_skin = remainder
                        if not is_skin_cn(remainder, work, work_skins):
                            candidate_skins.add(remainder)
                        manual.append(f"segment role: {best} + {remainder}")
        # multiple CJK segments：剥离皮肤后角色名仍由多段组成（含 _）才提示。
        # 皮肤词（如 桐生桔梗_常服 的「常服」）已剥离为 cn_skin，不再误报；
        # 仅当角色名本身由多段组成（如 棕榈_芊）时需人工确认。
        if "_" in cn:
            manual.append("multiple CJK segments")
            problems.append("other")
    if en_segs:
        # 每段剥离版本号（MikU1.0 -> MikU），再归一化去重（miku / MikU 视为同一拼写）
        stripped: list[str] = []
        seen_en: set[str] = set()
        for e in en_segs:
            # 纯数字段（如 1234）不是版本号，保留（后续走 numeric SKIP）
            e2 = (e if re.fullmatch(r"\d+(?:\.\d+)*", e)
                  else EN_VERSION_RE.sub('', e).rstrip('-_ '))
            if not e2:
                continue
            key = normalize_en_key(e2)
            if key and key in seen_en:
                continue
            seen_en.add(key)
            stripped.append(e2)
        # 英文皮肤剥离（逐段）：皮肤词可出现在任意位置（如 New_Sorasaki-Hina 的
        # New、Miku-Swimsuit 的 Swimsuit），皮肤段归 en_skin，角色段用 - 连接
        # （Rei_Ayanami -> Rei-Ayanami；Ayanami 非皮肤词，不动）。
        role_parts: list[str] = []
        skin_parts: list[str] = []
        for e in stripped:
            # 段内尾部皮肤：X-Y 且 Y 是皮肤词（如 Miku-Swimsuit）-> X 角色 + Y 皮肤
            if "-" in e:
                head, tail = e.rsplit("-", 1)
                if head and is_skin_en(tail, work, work_skins):
                    role_parts.append(head)
                    skin_parts.append(tail)
                    continue
            # 整段皮肤词（如 New）-> 皮肤
            if is_skin_en(e, work, work_skins):
                skin_parts.append(e)
            else:
                role_parts.append(e)
        en = "-".join(role_parts)
        if skin_parts:
            # 皮肤段去重（如 魂魄妖梦_New_Konpaku-Youmu-New 有两个 New -> 只留一个）
            seen_skin: set[str] = set()
            dedup_skin: list[str] = []
            for s in skin_parts:
                k = normalize_en_key(s)
                if k not in seen_skin:
                    seen_skin.add(k)
                    dedup_skin.append(s)
            en_skin = "-".join(dedup_skin)
        # multiple EN segments：剥离皮肤后仍 >1 个角色段才提示（如复合名/变体需人工确认）。
        # 皮肤词（如 New）已剥离为 en_skin，不再误报。
        if len(role_parts) > 1:
            manual.append("multiple EN segments")
            problems.append("other")

    # 单个中文段命中该作品皮肤词：剥离为 cn_skin，角色名交给英文段反查填充
    # （如 OC_天眼泡狐龙_Wine-Fox -> cn_skin=天眼泡狐龙，cn 由 Wine-Fox 反查酒狐）
    if (cn and work and work != "Unknown" and work_skins
            and cn in set(str(x) for x in (work_skins.get(work) or {}).get('zh') or [])):
        cn_skin = cn
        cn = ""

    if not cn and not en:
        return {"original": orig, "new": "", "status": "SKIP", "notes": "no role info",
                "work": work, "zh": "", "en": "", "grade": grade, "work_source": work_source,
                "candidate_skins": []}

    # 作品别名归一：work 为 ASCII 别名（非键）时，尝试宽松匹配归一为标准键
    # （character/*.json 顶层键）。唯一命中自动归一（如 WanderingWitch -> MNT、
    # ATRI -> AIRI）；多候选不归一、仅提示人工确认（如 Red -> RA2/RA3/ROH），
    # 避免误伤。
    if work and work != "Unknown" and work.isascii():
        if get_work_canonical(work) is None:
            canon = get_work_canonical(work, fuzzy=True)
            if canon:
                work = canon
                manual.append("work alias normalized: " + work)
                # 作品别名归一属自动修复，不算遗留问题（不加入 problems）
            else:
                cands = _work_fuzzy_hits(work)
                if cands:
                    manual.append("ambiguous work alias: "
                                  + "/".join(sorted(cands)))
                    problems.append("conflict")

    # 作品名：前缀优先；但 Unknown 前缀视为「待定」，仍允许知识库修正。
    conflict = False
    conflict_works: list[str] = []  # 跨作品同名时的候选作品（供交互选择）
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
            conflict_works = sorted(hits)
            manual.append("ambiguous work: " + "/".join(conflict_works))
            problems.append("conflict")
            work = "Unknown"
            work_source = "conflict"
        elif not work:
            work = "Unknown"
            work_source = "none"
        # hits 为空且 work 原本就是 Unknown（前缀）：保持 Unknown，不再改写

    # 知识库规范化：work 已确定时，用该作品角色的名称做补齐与标准化。
    # - 补全（缺失才补）：cn/en 数组首项来自索引（所有别名也参与），唯一候选才补。
    # - 标准化（已有但非标准，如拼音 Chuyin -> Miku）：以条目 en/cn 数组首项
    #   （规范名）为权威；_related 保护皮肤/复合名，避免把已规范名误覆盖。
    filled: list[str] = []
    if work and work != "Unknown":
        if cn and not en and cn_to_en:
            cands: set[str] = set()
            for w, e in cn_to_en.get(cn, []):
                if w == work:
                    cands.add(e)
            if len(cands) == 1:
                en = cands.pop()
                filled.append("EN auto-filled: " + en)
        if en and not cn and en_to_cn:
            cands = set()
            k1 = normalize_en_key(en)
            for k in {k1, k1.replace('_', '-')}:
                for w, c in en_to_cn.get(k, []):
                    if w == work:
                        cands.add(c)
            if len(cands) == 1:
                cn = cands.pop()
                filled.append("CN auto-filled: " + cn)
        if cn and en and cn_to_en:
            cands = set()
            for w, e in cn_to_en.get(cn, []):
                if w == work:
                    cands.add(e)
            if len(cands) == 1:
                cand = cands.pop()
                if not _related(en, cand):
                    en = cand
                    filled.append("EN standardized: " + cand)
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

    if en:
        en = init_caps(en)
        if re.fullmatch(r"[0-9]+", en):
            return {"original": orig, "new": "", "status": "SKIP", "notes": "numeric EN only",
                    "work": work, "zh": cn, "en": en, "grade": grade, "work_source": work_source,
                    "candidate_skins": sorted(candidate_skins)}

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

    if not cn:
        manual.append("missing CN name")
        problems.append("cn-name")
    if not en:
        manual.append("missing EN name")
        problems.append("en-name")
    # 缺作品（work 无法确定且非跨作品冲突）：需手动补作品前缀
    if (not conflict) and (not work or work == "Unknown") and not (not cn and not en):
        problems.append("works")
    # 去重（同一问题可能重复触发，如 multiple CJK 多段）
    problems = list(dict.fromkeys(problems))

    status = "OK" if new == orig else "FIX"
    return {"original": orig, "new": new, "status": status, "notes": "; ".join(manual),
            "filled": "; ".join(filled), "work": work, "zh": cn, "en": en, "grade": grade,
            "cn_skin": cn_skin, "en_skin": en_skin, "conflict": conflict,
            "conflict_works": conflict_works, "work_source": work_source,
            "problems": problems, "candidate_skins": sorted(candidate_skins)}


def role_key(r: dict) -> str:
    """角色条目的去重键：取 cn/en 的规范名（数组第一个）。"""
    cn = role_names(r, "zh")
    en = role_names(r, "en")
    cn_main = cn[0] if cn else ""
    en_main = en[0] if en else ""
    return f"{r['work']}|{cn_main}|{en_main.lower()}"


def build_kb(all_names: list[str]) -> list[dict]:
    """从文件夹名提取角色条目，并自动合并同一角色的不同写法（别名）。

    合并规则（仅限同一作品内）：
      1. 同 中文名 + 不同英文名  -> 合并为 en 数组（如 阿米娅 amiya/amyia）
      2. 英文名集合有交集        -> 合并为 cn 数组（如 后藤一里/波奇酱 都是 hitori-goto）
      3. 跨作品不合并（如 夏安 在 GF 与 GF2 各自保留）
    cn 数组第一个为出现次数最多、名称最长的规范名（补全默认用它）。
    """
    from collections import defaultdict

    cn_en: dict[tuple, set] = defaultdict(set)      # (work, cn) -> {en}
    cn_cnt: dict[tuple, int] = defaultdict(int)     # (work, cn) -> 出现次数
    for n in all_names:
        r = resolve_name(n, {}, {})  # 仅前缀解析，不需要知识库
        if r["status"] == "SKIP":
            continue  # 无法安全解析的（纯数字编号、无角色信息等）不进数据库
        if r["work"] and r["work"] != "Unknown" and r["zh"] and r["en"]:
            key = (r["work"], r["zh"])
            cn_en[key].add(r["en"].lower())
            cn_cnt[key] += 1

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
        cns.sort(key=lambda c: (-len(c), -cnts[c]))  # 全称（较长）优先，同长按出现次数
        ens = sorted(set().union(*[g[2] for g in group]))
        merged.append({"work": work, "zh": cns, "en": ens})
    return merged
