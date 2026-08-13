"""模型命名与去重通用逻辑（same_model、评级后缀清理、名称规范化）。"""
import re
import unicodedata

# 文件名/文件夹名里应剔除的评级后缀与版本号后缀（评级组用于提取等级）
GRADE_SUFFIX_RE = re.compile(r'_(LA|LB|LC|LD)$', re.IGNORECASE)
VERSION_SUFFIX_RE = re.compile(r'_[vV]?\d+(?:\.\d+)*$')


def has_cjk(s: str) -> bool:
    """是否包含中日韩统一表意文字。"""
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)


def normalize_name_for_cmp(s: str) -> str:
    """名称比较归一化：NFKC、去空白（含全角）、小写。"""
    return unicodedata.normalize('NFKC', s).replace(' ', '').replace('　', '').lower()


def clean_file_stem(stem: str) -> str:
    """清理文件名主干：去等级后缀(_LA~_LD)、版本号(_v1.0 等)与尾部杂符。"""
    s = stem.strip()
    s = GRADE_SUFFIX_RE.sub('', s)
    s = VERSION_SUFFIX_RE.sub('', s)
    s = s.rstrip('_-. ')
    return s


def clean_folder_name(folder_name: str) -> str:
    """去除文件夹名称末尾的评级标签 (_LA, _LB, _LC, _LD)（rename_model_files 用）。"""
    return GRADE_SUFFIX_RE.sub('', folder_name)


def same_model(a: str, b: str) -> bool:
    """判断两个名称是否属于同一模型（不同版本）。
    判定：完全相等（调用方已排除）、去【】/括号修饰后相等、或一方为另一方子串（>=3 字）。
    """
    na, nb = normalize_name_for_cmp(a), normalize_name_for_cmp(b)
    if not na or not nb or na == nb:
        return na == nb
    core_a = re.sub(r'[【\[（(].*?[】\]）)]', '', na)
    core_b = re.sub(r'[【\[（(].*?[】\]）)]', '', nb)
    if core_a and core_b and core_a == core_b:
        return True
    if len(na) >= 3 and len(nb) >= 3 and (na in nb or nb in na):
        return True
    return False
