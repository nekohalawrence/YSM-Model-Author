#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 lib/models.detect_work_prefix（作品前缀识别，配合 01_organize_models 按作品分类）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from lib.models import detect_work_prefix

# 模拟 character/*.json 文件名生成的作品键表（大写 -> 规范写法）
WMAP = {
    'AK': 'AK', 'BA': 'BA', 'UMAMUSUME': 'UmaMusume',
    '5TOUBUN': '5Toubun', 'DDLC': 'DDLC', 'UNKNOWN': 'Unknown',
}


def test_hit_standard():
    """规范「作品_角色_英文」前缀命中，返回规范写法。"""
    assert detect_work_prefix('AK_阿米娅_Amiya', WMAP) == 'AK'
    assert detect_work_prefix('BA_阿罗娜_Arona', WMAP) == 'BA'
    assert detect_work_prefix('UmaMusume_北部玄驹_Kitasan_Black', WMAP) == 'UmaMusume'
    assert detect_work_prefix('5Toubun_Itsuki-Nakano', WMAP) == '5Toubun'
    assert detect_work_prefix('DDLC_Natsuki', WMAP) == 'DDLC'
    assert detect_work_prefix('Unknown_艾卡', WMAP) == 'Unknown'


def test_miss():
    """前缀未命中 / 无下划线 / 空名 -> None。"""
    assert detect_work_prefix('NoSuchWork_角色', WMAP) is None
    assert detect_work_prefix('no_underscore', WMAP) is None
    assert detect_work_prefix('', WMAP) is None
    assert detect_work_prefix('_只含分隔', WMAP) is None


if __name__ == '__main__':
    test_hit_standard()
    test_miss()
    print('test_detect_work: OK')
