# -*- coding: utf-8 -*-
"""kb 名称字符串工具：CJK 检测、英文名规范化、作品名规范化、皮肤标签（无 lib 依赖）。"""
import json
import re
from pathlib import Path

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TOUHOU_PREFIX_RE = re.compile(r"(?i)^touhou(.+)$")
MIXED_SEG_RE = re.compile(
    r"^(?P<cn>[\u4e00-\u9fff·]+)(?:-(?P<skin>[\u4e00-\u9fff·][\u4e00-\u9fff·-]*))?(?:-|_|\s+)(?P<en>.+)$"
)
CN_SKIN_RE = re.compile(r"^(.+?)-([\u4e00-\u9fff].*)$")
EN_TAIL_RE = re.compile(r"[-_][^-_]+$")
PAREN_RE = re.compile(r"[\(（][^\)）]*[\)）]")


def has_cjk(s: str) -> bool:
    """是否包含中文字符。"""
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


def normalize_work_name(name: str) -> str:
    """作品名归一化：小写、去标点（保留中文字符与字母数字）。"""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", name.lower())


# 皮肤标签外部化：.github/data/model-info/skin_tags.json（方便维护，不写死在代码里）。
# 结构: {"common": {"zh":[...], "en":[...]}, "<作品键>": {"zh":[...], "en":[...]}}
# 剥离皮肤时用「通用 common + 当前作品专属」合并词表（work 为 None 时仅通用）。
_DEFAULT_SKIN_TAGS_PATH = (Path(__file__).resolve().parents[4]
                           / '.github' / 'data' / 'model-info' / 'skin_tags.json')
_SKIN_TAGS: dict | None = None
_SKIN_CACHE: dict[tuple, set] = {}


def set_skin_tags(tags: dict) -> None:
    """写入皮肤标签（运行时/测试注入，替代默认文件加载）。"""
    global _SKIN_TAGS
    _SKIN_TAGS = tags
    _SKIN_CACHE.clear()


def _skin_tags() -> dict:
    global _SKIN_TAGS
    if _SKIN_TAGS is None:
        try:
            _SKIN_TAGS = json.loads(_DEFAULT_SKIN_TAGS_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _SKIN_TAGS = {'common': {'zh': [], 'en': []}}
    return _SKIN_TAGS


def _work_skin_set(work: str | None, field: str) -> set[str]:
    """某作品（None=仅通用）某语言皮肤词集合（带缓存）。"""
    key = (work or '', field)
    cached = _SKIN_CACHE.get(key)
    if cached is not None:
        return cached
    tags = _skin_tags()
    out = set(str(x) for x in (tags.get('common') or {}).get(field) or [])
    if work:
        out |= set(str(x) for x in (tags.get(work) or {}).get(field) or [])
    _SKIN_CACHE[key] = out
    return out


def is_skin_cn(tag: str, work: str | None = None) -> bool:
    """是否为中文皮肤标签（通用 + 该作品专属）。"""
    return tag in _work_skin_set(work, 'zh')


def is_skin_en(tag: str, work: str | None = None) -> bool:
    """是否为英文皮肤标签（通用 + 该作品专属）。"""
    return tag.lower() in _work_skin_set(work, 'en')



