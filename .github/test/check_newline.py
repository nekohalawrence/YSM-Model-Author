# -*- coding: utf-8 -*-
"""检查模型 README 换行符（临时脚本，放 .github/test 下可保留）。"""
import pathlib
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

samples = [
    "Models/0095/VOC_初音-兔子洞_Miku-Rabbithole_sfw_LA/README.md",
    "Models/0194/小神吞/README.md",
    "Other-YSM-Models/5Toubun_Itsuki-Nakano/README.md",
]
for f in samples:
    p = pathlib.Path(f)
    if not p.exists():
        print(f, '不存在')
        continue
    b = p.read_bytes()
    crlf = b.count(b'\r\n')
    lf = b.count(b'\n')
    print(f, 'CRLF:', crlf, '纯LF:', lf - crlf)
