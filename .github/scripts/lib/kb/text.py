# -*- coding: utf-8 -*-
"""kb 名称字符串工具：CJK 检测、英文名规范化、作品名规范化、皮肤标签（无 lib 依赖）。"""
import json
import re
from pathlib import Path

# 中文字符 + 日文假名（平假名/片假名）：知识库角色名可含日文写法（如 長崎そよ）。
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")
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


# 皮肤标签标准化表：.github/data/model-info/skin_tags.json。
# 结构: {标签键: {name: {语言: 标准名}, aliases: [混合别名(不分语言，用于匹配)]}}
# 全局通用，不再按作品分组；中文词=name.zh+CJK 别名，英文词=name.en+非 CJK 别名。
_DEFAULT_SKIN_TAGS_PATH = (Path(__file__).resolve().parents[4]
                           / '.github' / 'data' / 'model-info' / 'skin_tags.json')
_SKIN_TAGS: dict | None = None
_SKIN_LANG_CACHE: tuple[set[str], set[str]] | None = None


def set_skin_tags(tags: dict) -> None:
    """写入皮肤标签（运行时/测试注入，替代默认文件加载）。"""
    global _SKIN_TAGS, _SKIN_LANG_CACHE
    _SKIN_TAGS = tags
    _SKIN_LANG_CACHE = None


def _skin_tags() -> dict:
    global _SKIN_TAGS
    if _SKIN_TAGS is None:
        try:
            _SKIN_TAGS = json.loads(_DEFAULT_SKIN_TAGS_PATH.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _SKIN_TAGS = {}
    return _SKIN_TAGS


def _skin_lang_sets() -> tuple[set[str], set[str]]:
    """从新格式构建 (中文词集合, 英文词集合)；英文词统一小写。"""
    global _SKIN_LANG_CACHE
    if _SKIN_LANG_CACHE is None:
        zh: set[str] = set()
        en: set[str] = set()
        for t in _skin_tags().values():
            name = t.get('name') or {}
            if name.get('zh'):
                zh.add(str(name['zh']))
            if name.get('en'):
                en.add(str(name['en']).lower())
            for a in t.get('aliases') or []:
                a = str(a)
                if has_cjk(a):
                    zh.add(a)
                else:
                    en.add(a.lower())
        _SKIN_LANG_CACHE = (zh, en)
    return _SKIN_LANG_CACHE


def _work_skin_set(work: str | None, field: str) -> set[str]:
    """皮肤词集合（新格式全局通用，work 参数仅兼容旧签名）。"""
    zh, en = _skin_lang_sets()
    return zh if field == 'zh' else en


def _common_skin_set(field: str) -> set[str]:
    """皮肤词集合（全局，不再区分 common/作品）。"""
    zh, en = _skin_lang_sets()
    return zh if field == 'zh' else en


def is_skin_cn(tag: str, work: str | None = None,
               work_skins: dict | None = None) -> bool:
    """是否为中文皮肤标签（全局标签 + 该作品角色 skin 键聚合）。

    work_skins 由 build_work_skins(roles) 生成（皮肤词下沉到角色 skin 键）；
    未传时退回全局 skin_tags（兼容旧数据/测试注入）。
    """
    if tag in _common_skin_set('zh'):
        return True
    if work_skins:
        ws = work_skins.get(work) or {}
        return tag in set(str(x) for x in ws.get('zh') or [])
    return tag in _work_skin_set(work, 'zh')


def is_skin_en(tag: str, work: str | None = None,
               work_skins: dict | None = None) -> bool:
    """是否为英文皮肤标签（全局标签 + 该作品角色 skin 键聚合）。"""
    low = tag.lower()
    if low in _common_skin_set('en'):
        return True
    if work_skins:
        ws = work_skins.get(work) or {}
        return low in set(str(x).lower() for x in ws.get('en') or [])
    return low in _work_skin_set(work, 'en')



