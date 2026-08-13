#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSM 模型知识库维护工具（本仓库专用）。

知识库为外置多文件，位于 .github/data/knowledge/ 下：
    works.json         作品表（英文名/中文名/日文名，README.md 为权威源自动同步）
    aliases.json       别名/变体表
    roles/<作品>.json  按作品分文件存放角色对照

本脚本既是被 ysm_rename.py 复用的知识库核心库，也可独立运行做维护。

用法:
  构建:
    python .github/scripts/ysm_kb.py --build-kb   # 重建（扫描文件夹 + 同步 README + 保存）
  维护命令:
    python .github/scripts/ysm_kb.py --add        # 交互式添加手工对照条目
    python .github/scripts/ysm_kb.py --alias      # 登记别名/变体（大昔涟 -> 昔涟）
    python .github/scripts/ysm_kb.py --del        # 删除条目（搜索 -> 选 id）
    python .github/scripts/ysm_kb.py --check      # 数据质量检查
    python .github/scripts/ysm_kb.py --suggest    # 疑似匹配建议（确认后写别名）
    python .github/scripts/ysm_kb.py --merge      # 合并重复角色条目（交互确认）
    python .github/scripts/ysm_kb.py --list       # 查看数据库全部条目
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3  # 浠呯敤浜庨娆′粠鏃?SQLite 搴撹縼绉?
import sys
from pathlib import Path

from lib import models as lib_models
from lib import paths as lib_paths

REPO_ROOT = lib_paths.WORKSPACE_ROOT
DEFAULT_ROOTS = [REPO_ROOT / "Models", REPO_ROOT / "Other-YSM-Models"]
# 鐭ヨ瘑搴撶粺涓€瀛樻斁浜?.github/data/knowledge/锛堢敱 lib/paths.py 瀹氫綅锛屼笌鑴氭湰瑙ｈ€︼級
KB_DEFAULT = lib_paths.KNOWLEDGE_DIR

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
GRADE_RE = lib_models.GRADE_SUFFIX_RE
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
    """
    全小写 token 首字母大写；已含大写的 token 不动。
    """
    英文名归一化：去括号内容、去空白、小写。
    """
    作品名归一化：小写、去标点（保留中文字符与字母数字）。
    """
    安全的交互输入：去 BOM、去首尾空白；非交互 stdin 耗尽时返回 'q'（退出）。
    """
    角色条目的去重键：取 cn/en 的规范名（数组第一个）。
    """
    取角色条目某字段的名称列表（字符串 -> 单元素列表；数组去空保序）。
    """
    从文件夹名提取角色条目，并自动合并同一角色的不同写法（别名）。
    
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
        r = resolve_name(n, {}, {})  # 浠呭墠缂€瑙ｆ瀽锛屼笉闇€瑕佺煡璇嗗簱
        if r["status"] == "SKIP":
            continue  # 鏃犳硶瀹夊叏瑙ｆ瀽鐨勶紙绾暟瀛楃紪鍙枫€佹棤瑙掕壊淇℃伅绛夛級涓嶈繘鏁版嵁搴?
        if r["work"] and r["work"] != "Unknown" and r["cn"] and r["en"]:
            key = (r["work"], r["cn"])
            cn_en[key].add(r["en"].lower())
            cn_cnt[key] += 1

    base: list[list] = [[work, cn, ens, cn_cnt[(work, cn)]]
                        for (work, cn), ens in cn_en.items()]

    # 鎸?(work, en 浜ら泦) 鍚堝苟锛氬悓涓€浣滃搧鍐呰嫳鏂囧悕閲嶅彔 => 鍚屼竴瑙掕壊锛堟樀绉?鍒О锛?
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
        merged.append({"work": work, "cn": cns, "en": ens, "source": "auto"})
    return merged


# ---------------------------------------------------------------------------
# 鐭ヨ瘑搴擄紙澶氭枃浠?JSON锛屽彲鐩存帴鐢ㄦ枃鏈紪杈戝櫒淇敼锛?
# ---------------------------------------------------------------------------
def _safe_name(wk: str) -> str:
    """
    作品键 -> 安全文件名（Windows 非法字符替换为 _）。
    """
    读取知识库。
    
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
            print(f"[warn] 鐭ヨ瘑搴?JSON 鏃犳硶瑙ｆ瀽: {e}", file=sys.stderr)
            return empty
    data = {"version": 2, "works": {}, "roles": [], "aliases": []}
    wf = kb_path / "works.json"
    old_single = kb_path / "ysm_kb.json"
    if not wf.exists() and not (kb_path / "roles").exists() and old_single.exists():
        # 灏氭湭杩佺Щ锛氳鏃у崟鏂囦欢锛堥伩鍏嶆墜宸ユ潯鐩涪澶憋級
        try:
            d = json.loads(old_single.read_text(encoding="utf-8"))
            d.setdefault("works", {})
            d.setdefault("roles", [])
            d.setdefault("aliases", [])
            return d
        except (json.JSONDecodeError, OSError) as e:
            print(f"[warn] 鐭ヨ瘑搴?JSON 鏃犳硶瑙ｆ瀽: {e}", file=sys.stderr)
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
    """
    写回知识库（多文件）：works.json + aliases.json + roles/<作品>.json。
    
    kb_path 为目录；若为旧单文件路径则以其父目录为数据根并迁移。
    """
    if kb_path.is_file():
        old_single = kb_path
        kb_path = old_single.parent
    else:
        old_single = kb_path / "ysm_kb.json"
    kb_path.mkdir(parents=True, exist_ok=True)
    data["version"] = 2
    # works 鍊兼敮鎸佷笁绉嶅啓娉曪細骞抽摵鏁扮粍 / 绌?[] / 鎸夎瑷€鍒嗙被瀵硅薄
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
        # skin锛氱毊鑲ゅ悕绉帮紝鏀寔澶氳瑷€锛堝 {"cn": ["娉宠"], "en": ["Swimsuit"]}锛?
        sk = r.get("skin")
        if isinstance(sk, dict):
            for lang, names in list(sk.items()):
                if isinstance(names, list):
                    out = []
                    for x in names:
                        if x and x not in out:
                            out.append(x)
                    sk[lang] = out
                elif names:
                    sk[lang] = [names]
                else:
                    sk[lang] = []
        elif isinstance(sk, list):
            items = [x for x in sk if x]
            r["skin"] = ({"cn": items} if any(has_cjk(x) for x in items)
                         else {"en": items})
        elif sk:
            r["skin"] = {"cn": [sk]} if has_cjk(sk) else {"en": [sk]}
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
              f"鏃?{old_single.name} 鍙垹闄?)


def migrate_from_sqlite(kb_path: Path, sqlite_path: Path) -> tuple[list[dict], list[dict]]:
    """
    首次迁移：旧 SQLite 库存在且 JSON 不存在时，搬移手工角色与别名。
    """
    解析 README 作品表。
    
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
        # 鍓ョ Markdown 鏃犲簭鍒楄〃鏍囪锛? 鍚嶇О | ...锛?
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
    """
    从 works 值（dict/列表/字符串）提取全部名称。
    """
    README 为 works 权威源：同步新增/更新。
    
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
            new_val = dict(works[key])  # 淇濈暀鐜版湁鍏跺畠璇█閿?
        if p["en"]:
            new_val["en"] = _dedup(p["en"])
        if p["cn"]:
            new_val["cn"] = _dedup(p["cn"])
        if p["ja"]:
            new_val["ja"] = _dedup(p["ja"])
        works[key] = new_val
    return added, updated


def build_work_index(data: dict) -> None:
    """
    从 works 数据构建全局作品名 -> 键 映射（解析前缀时使用）。
    """
    返回 (cn_idx, en_idx, en_to_cn, cn_to_en)。后两者用于补全缺失的中/英文名。
    角色条目的 cn/en 可以是字符串或数组：数组第一个为规范名（补全默认用它），
    其余为别名（仅用于匹配，补全时也归一到规范名）。
    """
        字符串 -> 单元素列表；数组 -> 去重（保留顺序）后的列表。
        """
    交互式添加手工对照条目（source='manual'，重建时保留、匹配时优先）。
    """
    交互式登记别名/变体：别称、大小修饰、多英文名 -> 规范名。
    """
    列出知识库全部条目（角色对照 + 别名）。
    """
    交互式删除条目（角色对照或别名）。按关键词搜索 -> 选编号删除。
    """
    数据质量检查：同名多作品、空字段、重复条目、别名悬空。
    """
    疑似匹配建议：扫描 work=Unknown 的文件夹，按包含关系给出候选，确认后写入别名。
    """
    合并重复角色条目（两阶段）。
    
    阶段 1（自动）：cn 或 en 有完全相等项的两条 = 确定同一角色，直接并入；
    阶段 2（手动）：仅子串/简称重叠的对，逐对 y/n 确认（不再整组闭包合并，
                   避免如 hina 是 hinata/hiyori 共同子串导致的误并）。
    合并时 cn/en 数组按名称长度降序（全称在前，作为规范名/补全默认值）。
    """
    data = load_kb_json(kb_path)
    roles = data.get("roles") or []
    if not roles:
        print("鐭ヨ瘑搴撲负绌恒€?)
        return

    def cn_set(r):
        return {c for c in role_names(r, "cn") if c}

    def en_set(r):
        return {normalize_en_key(e) for e in role_names(r, "en") if e}

    def has_exact(r1, r2):
        return bool(cn_set(r1) & cn_set(r2) or en_set(r1) & en_set(r2))

    def has_substr(r1, r2):
        """
        仅子串重叠（不含完全相等）：cn>=2 或 en>=3 的一方是另一方的子串。
        """
        把 r2 并入 r1（cn/en 数组去重，按长度降序全称在前），移除 r2。
        """
