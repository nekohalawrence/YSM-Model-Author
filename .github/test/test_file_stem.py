# -*- coding: utf-8 -*-
"""验证 parse_file_stem 的变体对照表匹配（skin_tags.json 标准化表驱动）。"""
import importlib.util
import pathlib
import sys

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT = (pathlib.Path(__file__).resolve().parents[2] / '.github' / 'scripts'
          / 'models_organize' / '02_rename_model_files.py')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / '.github' / 'scripts'))
spec = importlib.util.spec_from_file_location('ren_stem', str(SCRIPT))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
parse_file_stem = mod.parse_file_stem

cases = [
    # (file_stem, folder_name, 期望 变体+版本+副本)
    ('BA_月雪宫子：RABBIT1', 'BA_月雪宫子_常服_Tsukiyuki-Miyako', ''),   # 用户案例：RABBIT1 不在表 -> 丢弃
    ('BA_月雪宫子_泳装', 'BA_月雪宫子', '_swimsuit'),                    # 中文词 -> 规范英文
    ('BA_月雪宫子_泳装版', 'BA_月雪宫子', '_swimsuit'),                  # 去"版"后缀匹配
    ('BA_月雪宫子_万圣节版', 'BA_月雪宫子', '_halloween'),               # 去"版"后缀匹配
    ('BA_月雪宫子_新', 'BA_月雪宫子', '_new'),                           # 新 -> new
    ('BA_月雪宫子_旧', 'BA_月雪宫子', '_old'),                           # 旧 -> old
    ('BA_月雪宫子_new', 'BA_月雪宫子', '_new'),                          # 英文词直接命中
    ('BA_月雪宫子_RABBIT', 'BA_月雪宫子_常服_Tsukiyuki-Miyako', '_rabbithole'),  # RABBIT 命中 rabbithole 别名 rabbit
    ('兔子洞', 'VOC_初音_兔子洞', ''),                                   # 文件=文件夹名：无变体
    ('兔子洞Ver1.1', 'VOC_初音_兔子洞', '_v1.1'),                        # 版本号保留
    ('兔子洞Ver1.1_2', 'VOC_初音_兔子洞', '_v1.1_2'),                    # 版本号+副本保留
    ('BA_普拉娜_v2', 'BA_普拉娜_Plana_LB', '_v2'),                       # 纯整数版本 v2
    ('ZZZ_星见雅_v1', 'ZZZ_星见雅_Hoshimi-Miyabi_LA', '_v1'),            # 纯整数版本 v1
    ('BA_七度雪乃-FOX1_v2', 'BA_七度雪乃_FOX_LA', '_v2'),                # FOX1 尾数不当版本
    ('BA_空崎日奈_new_v2', 'BA_空崎日奈_New-Sorasaki-Hina_LB', '_v2'),   # new 与文件夹重复、v2 保留
]
ok = True
for stem, folder, expect in cases:
    v, ver, c = parse_file_stem(stem, folder)
    got = v + ver + c
    status = 'PASS' if got == expect else 'FAIL'
    if got != expect:
        ok = False
    print(f'{status}  file={stem!r} folder={folder!r} -> {got!r} (期望 {expect!r})')
print('全部通过' if ok else '存在失败')
sys.exit(0 if ok else 1)
