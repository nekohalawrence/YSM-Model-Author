# -*- coding: utf-8 -*-
"""新命名解析规则：Token 化 + 数据库归类 + 重组。

替代 parse.py 的「格式化→分段→补丁」式解析：
- 按语言块 tokenize：下划线/连字符/无分隔/间隔号/空格 统一处理；
- 每个 token 用数据库归类（作品/角色/评级/Unknown）；
- 识别段按 <作品>_<中文角色>[_中文附加段]_<英文角色>[_英文附加段]_<评级> 重组；
- 未识别段（数据库无收录，含形态/皮肤词）不做语义判定，一律保留原位：
  中文段并入中文侧（_ 连接）、英文段并入英文侧（- 连接、保留原始大小写）。

与 parse.resolve_name 返回结构兼容，可无缝替换（02_rename 等调用方不改）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.kb.text import (  # noqa: E402
    has_cjk, init_caps, normalize_en_key,
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
# 豁免 6.5b 降级的作品：角色无法穷举收录（原创/开放式大群体），前缀可信赖
# OC（原创）：角色名作者自创无法穷举；VTuber（虚拟主播）：开放式大群体，
# 角色海量且持续涌现，数据库无法穷举收录——前缀 VTuber_ 已是明确作品归属。
NO_ROLE_VALIDATION_WORKS = {"OC", "VTuber"}


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
        # 编号后缀"号"（如 21号/1号）：紧贴前一个纯数字段时并入整体一段，
        # 避免拆成 21 + 号（对齐 TOKEN_RE 的 \d+号 整体 token 规则）。
        if (ch == '号' and cur_kind == 'ascii' and cur_start is not None
                and name[cur_start:i].isdigit()):
            cur_kind = 'cjk'
            continue
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


def match_work(fmt: str, allow_prefix: bool = True) -> tuple[str, str, int]:
    """第 2 步：作品整体匹配。返回 (work, source, prefix_end)。

    - 前缀累积匹配（对齐 r2）：首段 ASCII 逐段拼接查 get_work_canonical，
      命中即前缀作品（如 Magia Record 的 magia_record），记录消耗段数；
    - 长全称（中文/长名）：normalize 后子串匹配；
    - allow_prefix=False（Unknown_ 前缀输入）：禁用前缀累积，只靠子串全称/
      角色反查，避免 Unknown_Rei-Ayanami 的 rei 被误当作品前缀。
    - prefix_end 供重组跳过前缀作品段（防 Record/Ghoul 等混入角色/英文）。
    """
    segs = fmt.split("_")
    best, best_len, source, prefix_end = "", 0, "none", 0
    if allow_prefix:
        acc = ""
        for i, seg in enumerate(segs):
            if not seg.isascii():
                break
            acc = (acc + "_" if acc else "") + seg
            w = get_work_canonical(acc)
            if w and len(acc) > best_len:
                best, best_len, source = w, len(acc), "prefix"
                prefix_end = i + 1
    nfmt = normalize_work_name(fmt)
    for nk, w in EXTRA_WORK_ALIASES.items():
        # 子串匹配只对长名/中文全称（短英文简称走前缀累积，避免 mikuba 里的 ba 误匹配）
        if (len(nk) >= 2 and (len(nk) >= 4 or has_cjk(nk))
                and nk in nfmt and len(nk) > best_len):
            best, best_len, source = w, len(nk), "substr"
    return best, source, prefix_end


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


def _eng_groups(segs: list[str]) -> list[tuple[int, int, str]]:
    """识别连续英文段组：返回 (start, end, 剔除内容标签后的组合串)。

    英文角色名须整体匹配（防单段误配：如 tachibana 撞其他作品单段角色）；
    组内内容标签（nsfw/sfw）不参与组合。
    """
    out: list[tuple[int, int, str]] = []
    i, n = 0, len(segs)
    while i < n:
        if segs[i].isascii():
            j = i
            while j < n and segs[j].isascii():
                j += 1
            parts = [segs[k] for k in range(i, j)
                     if segs[k].lower() not in CONTENT_TAGS]
            if parts:
                out.append((i, j, "_".join(parts)))
            i = j
        else:
            i += 1
    return out


def match_role(fmt: str, role_zh: dict, role_en: dict, prefix_end: int = 0):
    """第 2 步：角色整体匹配。返回 (cn, en, works, kind, hit_key, zh_s, zh_e, en_range)。

    - 中文：独立段/同语言组合/段内子串（最长优先）；英文：连续英文组整体匹配；
    - 支持中英双命中（cn 来自中文、en 来自同作品英文组）；
    - en_range 是命中的英文组段范围（供重组跳过，防英文段重复）；
    - cn/en 取命中的规范名；works 是归属作品集合。
    - prefix_end：前缀作品段数。英文组匹配跳过前缀段（避免 AK_Logos 把
      前缀 ak 和角色 logos 连成 ak_logos 导致匹配失败）。
    """
    segs = fmt.split("_")
    combo_lookup: dict[str, list] = {}
    for s, e, t in _seg_combos(segs):
        if e <= prefix_end:
            continue  # 前缀作品段不参与角色组合匹配
        combo_lookup.setdefault(t, []).append((s, e))
    zh_cands: list = []
    for k, vs in role_zh.items():
        if k in combo_lookup:
            for s, e in combo_lookup[k]:
                zh_cands.append((len(k), k, vs, s, e))
    en_cands: list = []
    for s, e, c in _eng_groups(segs[prefix_end:] if prefix_end else segs):
        ss, ee = s + prefix_end, e + prefix_end
        if c in role_en:
            en_cands.append((len(c), c, role_en[c], ss, ee))
    if zh_cands:
        zh_cands.sort(reverse=True)
        _, kz, vz, zs, ze = zh_cands[0]
        works = {w for _n, w in vz}
        cn = sorted(n for n, _w in vz)[0]
        en = ""
        en_range = None
        for _, ke, ve, es, ee in en_cands:
            if any(w in works for _n, w in ve):
                # 取 norm 与命中组合一致的 en 变体（如 New-...-New），不取字母序第一个
                en = next((nm for nm, _w in ve if format_name(nm)[0] == ke),
                          sorted(nm for nm, _w in ve)[0])
                en_range = (es, ee)
                break
        return cn, en, works, "zh", kz, zs, ze, en_range
    if en_cands:
        en_cands.sort(reverse=True)
        _, ke, ve, es, ee = en_cands[0]
        works = {w for _n, w in ve}
        en = next((nm for nm, _w in ve if format_name(nm)[0] == ke),
                  sorted(nm for nm, _w in ve)[0])
        return "", en, works, "en", "", 0, 0, (es, ee)
    # 中文段内子串兜底（小花子 -> 花子）
    for k, vs in role_zh.items():
        for i, seg in enumerate(segs):
            if i < prefix_end:
                continue  # 前缀作品段不参与子串兜底
            if k and len(k) >= 2 and k in seg and k != seg:
                return (sorted(n for n, _w in vs)[0], "",
                        {w for _n, w in vs}, "zh", k, i, i + 1, None)
    return "", "", set(), "", "", 0, 0, None


def resolve_name3(name: str, roles: list[dict],
                  en_to_cn: dict | None = None, cn_to_en: dict | None = None,
                  cn_alias: dict | None = None) -> dict:
    """整体匹配版解析器：第 1 步格式化 → 第 2 步作品/角色匹配 → 第 3 步重组。

    返回与 resolve_name2 兼容的结构。
    """
    orig = name
    notes: list[str] = []
    problems: list[str] = []
    filled: list[str] = []
    role_zh, role_en = build_norm_role_index(roles)

    # 第 1 步：格式化 + 去评级
    fmt, grade, spans = format_name(name)
    segs = fmt.split("_") if fmt else []
    # Unknown 前缀剥离（同步去掉首段）。剥离后按正常名称匹配（恢复前缀累积），
    # 便于 Unknown_HI3刻律德菈 把 HI3 识别为作品前缀并剥离；Unknown_Rei-Ayanami
    # 的 rei 非作品键不会被误当作品（match_work 前缀累积只认 get_work_canonical 命中）。
    unknown_seen = False
    if segs and segs[0].lower() == "unknown":
        unknown_seen = True
        segs, spans = segs[1:], spans[1:]
        fmt = "_".join(segs)

    # 第 2 步：作品 + 角色匹配（Unknown_ 前缀已剥离，前缀累积恢复启用）
    work, work_source, prefix_end = match_work(fmt, allow_prefix=True)
    # 作品锁定（2026-08-19）：匹配到数据库作品后，角色只在该作品下匹配，不再全局
    # 匹配 + 事后归属校验（归属判定随之简化）。
    # 收紧：不再把任意 ASCII 首段当作品候选（原逻辑会把 Rei-Ayanami 的 rei 误当
    # 作品前缀，且配合"无角色保留前缀"会产出 Rei_Ayanami 这种错误前缀）——只认
    # 数据库真实作品键；未注册缩写走"无作品 -> 角色匹配"。
    if work and work != "Unknown":
        # 作品限定角色索引：只保留归属当前 work 的角色条目
        role_zh_scope = {k: {(n, w) for n, w in vs if w == work}
                         for k, vs in role_zh.items()
                         if any(w == work for _n, w in vs)}
        role_en_scope = {k: {(n, w) for n, w in vs if w == work}
                         for k, vs in role_en.items()
                         if any(w == work for _n, w in vs)}
        cn, en, role_works, kind, hit_key, hit_s, hit_e, en_range = match_role(
            fmt, role_zh_scope, role_en_scope, prefix_end)
    else:
        cn, en, role_works, kind, hit_key, hit_s, hit_e, en_range = match_role(
            fmt, role_zh, role_en, prefix_end)
    # 英文组消费为 en：仅在「中文角色未命中」时进行（纯英文/英文开头输入，如
    # Unknown_Lingsha），把英文名设为 en 供下方 en→cn 反查补全中文名。
    # 中文命中时英文组一律不消费——未识别英文段统一由第 3 步重组原位保留
    # （en_parts，- 连接、保留原始大小写），不做「角色英文名/皮肤附加段」判定，
    # 避免被下方补全/标准化覆盖而丢失（如 初音Bunnygirl 的 Bunnygirl）。
    if not hit_key and en_range is None and segs:
        for s, e, c in _eng_groups(segs):
            if get_work_canonical(segs[s]):
                continue  # 跳过作品段
            raw = "-".join(spans[i][0] for i in range(s, e)
                           if segs[i].lower() not in CONTENT_TAGS
                           and not get_work_canonical(segs[i]))
            if raw:
                en = raw
                en_range = (s, e)
            break
    # en 命中且有输入英文组：优先保留输入原始写法（与数据库名相关时），
    # 避免数据库小写名覆盖 TiaoXiangShi/FrostNova 等原始大小写
    if en and en_range:
        raw_en = "-".join(spans[i][0] for i in range(en_range[0], en_range[1])
                          if segs[i].isascii())
        if raw_en and _related(en, raw_en):
            en = raw_en

    # 归属判定（作品锁定简化版，2026-08-19）：
    #   - 有作品：角色命中 -> 直接用该作品；角色未命中 -> 保留前缀，只作品标准化
    #     （不再降级 Unknown，也不做跨作品前缀纠错）
    #   - 无作品 + 角色命中：唯一归属 -> 反查加前缀；多归属 -> unknown 前缀
    #   - 无作品 + 无角色：unknown
    conflict = False
    conflict_works: list[str] = []
    if work and work != "Unknown":
        if not cn and not en:
            notes.append(f"work locked: {work} has no role match in db, keep prefix")
    elif not work and (cn or en):
        if len(role_works) == 1:
            work, work_source = next(iter(role_works)), "kb"
        elif len(role_works) > 1:
            conflict = True
            conflict_works = sorted(role_works)
            work, work_source = "Unknown", "conflict"
    elif not work and not (cn or en):
        work, work_source = "Unknown", "none"

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
        # 中英文都有：标准化为数据库规范名，但保留原有写法（仅大小写/写法差异时不覆盖）
        if cn and en and cn_to_en:
            cands = {e for w, e in cn_to_en.get(cn, []) if w == work}
            if len(cands) == 1:
                cand = init_caps(cands.pop())
                if not _related(en, cand):
                    en = cand
                    filled.append("EN standardized: " + cand)

    # 第 3 步：残留段分类 + 重组。不做皮肤/附加段语义判定：未识别段一律保留原位
    # （中文 -> cn_extra，_ 连接；英文 -> en_parts，- 连接、保留原始大小写；
    #   紧贴中文角色段的英文 -> 并入中文名，与前紧贴残留对称）。
    content_tag = ""
    cn_extra: list[str] = []  # 未识别中文段（原位保留）
    en_parts: list[str] = []
    pending_pre = ""  # 角色前紧贴残留（原始无分隔，最后并入核心 cn）
    # cn 规范名内嵌的英文 token（如 穆小泠Official 的 official、酒狐H 的 h）——
    # 它们是角色名的一部分，残留/en 合并时不再重复进英文名（防重名，非皮肤判定）。
    cn_inner_tokens = set(normalize_en_key(w) for w in re.findall(r'[A-Za-z]+', cn)) if cn else set()
    for i, seg in enumerate(segs):
        if i < prefix_end:
            continue  # 前缀作品段（含多词作品后半段，如 Magia Record 的 record）
        low = seg.lower()
        if low in CONTENT_TAGS:
            content_tag = CONTENT_CANON[low]
            continue
        if hit_key and hit_s <= i < hit_e:
            # 中文角色段：核心 cn（匹配/补全后的规范名）承载角色名；
            # 段内附加（rem，如 小花子 的 小）并入 cn（只处理首段）
            if i == hit_s:
                full = "_".join(segs[hit_s:hit_e])
                rem = full.replace(hit_key, "", 1) if hit_key in full else ""
                if rem:
                    cn = (cn + rem) if full.startswith(hit_key) else (rem + cn)
            continue
        # 英文组已消费（en 命中段）-> 跳过，防英文段重复（如 Exusiai-The-New-Covenant）
        if en_range and en_range[0] <= i < en_range[1]:
            continue
        # 末尾作品标记段（如 xiao月雪宫子BA 的 ba）：仅当与当前 work 一致才跳过。
        # 前缀作品段已由 prefix_end 跳过；不在开头/末尾的 get_work_canonical 命中
        # 是角色英文名段（如 Unknown_Rei-Ayanami 的 rei 恰好是某作品别名），不跳。
        if (i == len(segs) - 1 and work and work != "Unknown"
                and get_work_canonical(seg) == work):
            continue
        # 英文角色段已被 en/补全覆盖 -> 跳过（避免 Rosmontis/Shiroko 重复）
        if seg in role_en and work and work != "Unknown":
            if any(w == work for _n, w in role_en[seg]):
                continue
        # 角色段前紧贴残留（原始无分隔，如 xiao）-> 累积，最后并入核心 cn
        if hit_key and i == hit_s - 1 and spans[i][2] == spans[hit_s][1]:
            pending_pre += seg
            continue
        # 角色段后紧贴残留（如 穆小泠Official 的 Official、初音Bunnygirl 的 Bunnygirl）
        # ——紧贴中文角色段（原始无分隔）的英文段是中文名的紧贴部分，保留在中文位
        #   （与前紧贴残留 pending_pre 对称）；cn 规范名已含该英文（Official/H）
        #   则是角色名内嵌，不重复。
        if hit_key and i == hit_e and spans[hit_e - 1][2] == spans[i][1]:
            if cn:
                if normalize_en_key(seg) in cn_inner_tokens:
                    continue  # 角色名已含该英文（Official/H 是角色名一部分），不重复
                cn += spans[i][0]  # 紧贴未识别英文段（如 Bunnygirl）并入中文名，保留原始大小写
            else:
                cn_extra.append(seg)
            continue
        if has_cjk(seg):
            cn_extra.append(seg)  # 独立未识别中文段，原位保留
        else:
            # 未识别英文保留原始大小写（spans 原始文本），不强制 init_caps
            en_parts.append(spans[i][0])
    if pending_pre:
        cn = pending_pre + cn
    # 中文主块 = 核心 cn（匹配/补全后的规范名，直接参与组装）+ 未识别中文段（_ 连接）
    cn_seg_str = cn if cn else ""
    if cn_extra:
        cn_seg_str = "_".join([cn_seg_str] + cn_extra) if cn_seg_str else "_".join(cn_extra)

    # 未识别英文并入 en（- 连接）：数据库/补全部分 init_caps，未识别部分保留原始。
    # 防重名规则（非语义判定，仅字符串包含判断）：
    #   - 单个附加段已含完整角色英文写法（如 AronaBunnygirl ⊃ 补全的 Arona）→
    #     说明原始名已带完整英文名，保留原始写法，避免 Arona-AronaBunnygirl 重复；
    #   - 附加段是补全 en 的子串（如 MuXiaoLing ⊂ ...）或已含在中文名里的段
    #     （如 穆小泠Official 的 Official）不重复并入。
    if en_parts:
        enk = normalize_en_key(en) if en else ""
        if (enk and len(en_parts) == 1
                and normalize_en_key(en_parts[0]) and enk in normalize_en_key(en_parts[0])):
            en = en_parts[0]
        else:
            kept = [p for p in en_parts
                    if not (enk and normalize_en_key(p) and normalize_en_key(p) in enk)
                    and normalize_en_key(p) not in cn_inner_tokens]
            if kept:
                extra = "-".join(kept)
                if en:
                    en = init_caps(en) + "-" + extra  # 数据库部分标准，extra 原始
                else:
                    en = extra  # 纯未识别：保留原始大小写（如 PUR）
    elif en:
        en = init_caps(en)
    # en 中若含 cn 内嵌的英文 token（如 穆小泠Official 的 official、酒狐H 的 h），
    # 剔除避免重复——cn（角色名）已含该英文，不应再进英文名。
    if cn_inner_tokens and en:
        parts = en.split('-')
        kept = [p for p in parts if normalize_en_key(p) not in cn_inner_tokens]
        if kept and len(kept) < len(parts):
            en = '-'.join(kept)

    new = work
    if cn_seg_str:
        new += "_" + cn_seg_str
    if en:
        new += "_" + en
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
        "cn_skin": "", "en_skin": "", "conflict": conflict,
        "conflict_works": conflict_works, "work_source": work_source,
        "problems": problems, "candidate_skins": [],  # 皮肤判定已移除，恒为空（兼容返回结构）
    }


def _idx_work_has_roles(cn_idx: dict, en_idx: dict, work: str) -> bool:
    """resolve_name2 用：前缀作品库是否有已收录角色（cn_idx/en_idx 值=作品集合）。

    方案 B 判断「前缀作品库非空」：库空（如 NEKOPARA 无任何角色收录）时无法
    验证角色归属，避免把正确前缀（如 NEKOPARA_红豆）误判为标错。
    """
    for ws in cn_idx.values():
        if work in ws:
            return True
    for ws in en_idx.values():
        if work in ws:
            return True
    return False


def _norm_work_has_roles(role_zh: dict, role_en: dict, work: str) -> bool:
    """resolve_name3 用：前缀作品库是否有已收录角色（role_zh/role_en 值=(名,作品)）。"""
    for _k, vs in role_zh.items():
        if any(w == work for _n, w in vs):
            return True
    for _k, vs in role_en.items():
        if any(w == work for _n, w in vs):
            return True
    return False


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
    """当前名 a 是否已与规范名 b 一致（应保留，不覆盖）。

    ASCII 归一化（去括号/空白/小写）并把 `_` 与 `-` 等价（Padoru_Hakurei 与
    Padoru-Hakurei 视为相同）；中文去空格。
    """
    def fold(s: str) -> str:
        if s.isascii():
            return normalize_en_key(s).replace('_', '-')
        return s.replace(' ', '').replace('　', '')
    x, y = fold(a), fold(b)
    if not x or not y:
        return False
    return x == y or y in x


def resolve_name2(name: str, cn_idx: dict, en_idx: dict,
                  en_to_cn: dict | None = None, cn_to_en: dict | None = None,
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
                    cn_pending.remove(tok)
    # 未归类的剩余中文段：cn 为空时保留第一段为角色名（保持原样，待收录），
    # 其余段在重组阶段作为普通独立段保留原位（皮肤不再特殊识别）。
    for tok in cn_pending:
        if not cn:
            cn = tok

    # 6) 英文角色提取
    en = ""
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
    # 英文 pending 段：未识别英文拼接为 en（可能是英文名写法）
    if not en and en_pending:
        en = "-".join(en_pending)
    # 英文段内部剥离尾部内容标签（Miku-Rabbithole-Sfw -> Miku-Rabbithole + SFW）。
    # nsfw/sfw 总在段尾。
    if en and "-" in en:
        head, tail = en.rsplit("-", 1)
        if head and tail and tail.lower() in CONTENT_TAGS:
            en = head
            content_tag = CONTENT_CANON[tail.lower()]

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
    #       OC（原创）/VTuber（开放式大群体）豁免：角色无法穷举收录，
    #       前缀可信赖，不降级。
    if (work_source == "prefix" and work and work != "Unknown"
            and work not in NO_ROLE_VALIDATION_WORKS
            and not cn_from_kb and not cn_role_exact and not en_role_exact):
        notes.append(f"work unmatched: {work} has no known role, set Unknown")
        work = "Unknown"
        work_source = "unmatched"

    # 6.5c) 前缀作品与角色归属校验（方案 B）：角色命中但归属不含前缀作品，
    #       且「前缀作品库非空且无此角色」+「角色唯一归属单一他作」
    #       -> 高置信度纠正作品前缀（如 AL_阿罗娜酱_Arona -> BA）；
    #       库空（NEKOPARA）/跨作品同名（中英归属不一致）/豁免作品
    #       -> 仅标记问题提示人工，不自动改。
    if (work_source == "prefix" and work and work != "Unknown"
            and work not in NO_ROLE_VALIDATION_WORKS):
        cn_hit: set[str] = set()
        for c in cn_role_exact:
            cn_hit |= cn_idx.get(c, set())
        en_hit: set[str] = set()
        for e in en_role_exact:
            key = normalize_en_key(e)
            en_hit |= en_idx.get(key, set())
            en_hit |= en_idx.get(key.replace("_", "-"), set())
        if en and not en_role_exact:
            key = normalize_en_key(en)
            en_hit |= en_idx.get(key, set())
            en_hit |= en_idx.get(key.replace("_", "-"), set())
        hit = cn_hit | en_hit
        if hit and work not in hit:
            # 中英命中的作品集一致才视为可靠归属；单语言命中取其集；
            # 中英不一致或含多作品（跨作品同名）-> 保守不自动改。
            if cn_hit and en_hit and cn_hit != en_hit:
                reliable: set[str] = set()
            else:
                reliable = cn_hit or en_hit
            other = reliable - {work}
            if len(other) == 1 and _idx_work_has_roles(cn_idx, en_idx, work):
                new_work = next(iter(other))
                notes.append(f"work corrected: {work} -> {new_work}（角色归属校验）")
                work = new_work
                work_source = "corrected"
            else:
                problems.append("works")
                notes.append(
                    f"prefix work mismatch: {work} has no role, "
                    f"role belongs to {sorted(hit)}")

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

    # 8) 重组输出（保留原顺序：角色/未识别词原位替换）
    #    中文角色段按原 rest token 顺序重建：命中的角色子串替换为规范名、
    #    未识别词（如 xiao/小）保留原位、作品标记 token 抽离。
    # 重组前：cn 规范名可能对应 rest 中多个连续中文 token（如数据库名
    # 「奥托.阿波卡利斯」被符号格式化拆成 奥托+阿波卡利斯）。识别该段，
    # 重组时用规范名原样替换，避免规范名中的分隔符（.·）被再次格式化。
    cn_span: list[int] = []
    if cn:
        cn_flat = re.sub(r"[·・.、，,:：;；]", "", cn)
        if cn_flat:
            for i in range(len(rest)):
                if not has_cjk(rest[i]):
                    continue
                acc = ""
                for j in range(i, len(rest)):
                    if not has_cjk(rest[j]):
                        break
                    acc += rest[j]
                    if acc == cn_flat:
                        cn_span = list(range(i, j + 1))
                        break
                if cn_span:
                    break
    cn_seg: list[str] = []
    for idx, t in enumerate(rest):
        if t == grade:
            continue
        if cn_span:
            if idx == cn_span[0]:
                cn_seg.append(cn)  # 规范名原样（保留 .· 等分隔符）
                continue
            if idx in cn_span[1:]:
                continue
        if has_cjk(t):
            if t in cn_idx:
                cn_seg.append(_canon_cn(t, cn_alias, work))
            else:
                m = _extract_role_substr(t, work if work != "Unknown" else "", cn_idx)
                if m and work in cn_idx[m[0]]:
                    r, rem = m
                    std = _canon_cn(r, cn_alias, work)
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
            if "-" in t:
                segs = t.split("-")
                if any(s.lower() in CONTENT_TAGS for s in segs):
                    continue
            cn_seg.append(t)  # 未识别英文（xiao）保留到中文段
    # 段间用 _ 连接（独立段保留原位，皮肤/形态词不合并，见 ①A）
    cn_seg_str = "_".join(cn_seg)
    if cn and cn in (cn_alias or {}):
        cn = _canon_cn(cn, cn_alias, work)

    new = work
    if cn_seg_str:
        new += "_" + cn_seg_str
    if en:
        new += "_" + en
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
        "cn_skin": "", "en_skin": "", "conflict": conflict,
        "conflict_works": conflict_works, "work_source": work_source,
        "problems": problems, "candidate_skins": sorted(candidate_skins),
    }
