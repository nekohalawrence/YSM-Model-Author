# -*- coding: utf-8 -*-
"""真实样本 author_blocks 提取与多作者分类验证（放 .github/test 保留）。"""
import importlib.util
import pathlib
import sys

sys.stdout.reconfigure(encoding='utf-8')

spec = importlib.util.spec_from_file_location(
    'org', pathlib.Path(__file__).resolve().parents[2] / '.github' / 'scripts' / 'organize_models.py')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / '.github' / 'scripts'))
org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(org)

for f in [
    'Models/0195/明日方舟_可露希尔/明日方舟_可露希尔.ysm',
    'Models/0194/神明吞噬者/神吞.ysm',
    'Models/0095/VOC_初音-兔子洞_Miku-Rabbithole_sfw_LA/兔子洞.ysm',
]:
    meta = org.extract_metadata(pathlib.Path(f))
    print('=' * 20, f, '=' * 20)
    print('name:', repr(meta.get('name')))
    print('authors:', repr(meta.get('authors')))
    for b in meta.get('author_blocks') or []:
        print('  block:', repr(b['name']), '| role:', repr(b.get('role')), '| contacts:', b.get('contacts'))
    primary, models, cos = org.classify_authors(meta.get('author_blocks') or [])
    print('  主作者:', primary['name'] if primary else None,
          '| 归档目标:', [b['name'] for b in models],
          '| co-creator:', [b['name'] for b in cos])
