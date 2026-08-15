# -*- coding: utf-8 -*-
"""
kb_tool.py 名称解析与知识库构建核心逻辑测试（拆分 kb_tool 前的安全网）。

覆盖：
  1) resolve_name：前缀作品 / Unknown 前缀 / Touhou 前缀 / ASCII+中文作品段 /
     角色反查作品(kb) / 多作品冲突(Unknown+conflict) / 评级清理 / 知识库补全 / 纯数字 SKIP
  2) init_caps / normalize_en_key：英文名规范化
  3) build_kb：同中文名不同英文名合并、英文名交集合并、跨作品不合并
  4) role_key：条目去重键

运行：python .github/test/test_kb_resolve.py（退出码 0=全过，1=有失败）
"""
import importlib.util
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding='utf-8')

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / ".github" / "scripts"

# kb_tool.py 已并入 rename_model_folders，统一从 lib.kb 子包导入
sys.path.insert(0, str(SCRIPTS))
import lib.kb as kb

WORKS = {
    "BA": {"zh": ["碧蓝档案"], "en": ["Blue Archive"]},
    "AL": {"zh": ["碧蓝航线"], "en": ["Azur Lane", "Azurlane"]},
    "AKE": {"zh": ["尘白禁区"], "en": ["Snowbreak"]},
    "AK": {"zh": ["明日方舟"], "en": ["Arknights"]},
    "Ash-Arms": {"zh": ["灰烬战线"], "en": ["Ash Arms", "Ash-Arms"]},
    "AveMujica": {"zh": ["Ave Mujica"], "en": ["AveMujica"]},
    # 作品别名归一相关（AIRI/NEO/YogYard 收录别名，MNT 只留全称以测 fuzzy 前缀兜底）
    "AIRI": {"zh": ["亚托莉"], "en": ["ATRI -My Dear Moments-", "ATRI", "AIRI"]},
    "MNT": {"zh": ["魔女之旅"], "en": ["Wandering Witch: The Journey of Elaina", "Majo no Tabitabi"]},
    "NEO": {"zh": ["主播女孩重度依赖"], "en": ["Needy Girl Overdos", "Needy Girl Overdose", "NEO", "NGO"]},
    "YogYard": {"zh": ["犹格索托斯的庭院"], "en": ["Yog-Sothoth's Yard", "YogYard", "YGYST"]},
    "RA2": {"zh": ["命令与征服：红色警戒 2"], "en": ["Red Alert 2", "RA2"]},
    "RA3": {"zh": ["命令与征服：红色警戒 3"], "en": ["Red Alert 3", "RA3"]},
    "ROH": {"zh": ["回复术士的重启人生"], "en": ["Redo of Healer", "ROH"]},
    "PCR": {"zh": ["公主连结"], "en": ["Princess Connect! Re:Dive", "PCR"]},
}
# 两个作品都有"夏安"（跨作品冲突场景）；BA 白子带别名
ROLES = [
    {"work": "BA", "zh": ["白子", "砂狼白子"], "en": ["shiroko", "sunasaki-shiroko"], "source": "manual"},
    {"work": "BA", "zh": ["伊吕波"], "en": ["iroha"], "source": "manual"},
    {"work": "AL", "zh": ["柴郡"], "en": ["cheshire"], "source": "manual"},
    {"work": "AK", "zh": ["阿米娅"], "en": ["amiya", "amyia"], "source": "manual"},
    {"work": "VOC", "zh": ["初音", "初音未来"], "en": ["miku"], "source": "manual"},
    {"work": "GF", "zh": ["夏安"], "en": ["xiaan"], "source": "manual"},
    {"work": "GF2", "zh": ["夏安"], "en": ["xiaan-gf2"], "source": "manual"},
]

# 构建索引（works -> EXTRA_WORK_ALIASES 前缀识别；roles -> 名称索引）
kb.build_work_index({"works": WORKS, "roles": []})
CN_IDX, EN_IDX, EN_TO_CN, CN_TO_EN = kb.build_indexes(ROLES)


def resolve(name: str):
    """便捷包装：resolve_name 只取需要字段。"""
    return kb.resolve_name(name, CN_IDX, EN_IDX, EN_TO_CN, CN_TO_EN)


def main() -> int:
    checks: list[tuple[bool, str]] = []

    def ck(cond: bool, msg: str) -> None:
        checks.append((cond, msg))

    # 1. 前缀作品识别 + 评级清理 + init_caps
    r = resolve("BA_白子_Shiroko_LA")
    ck(r["work"] == "BA", f"BA_白子_Shiroko_LA work={r['work']!r} (期望 BA)")
    ck(r["zh"] == "白子", f"cn={r['zh']!r} (期望 白子)")
    ck(r["en"] == "Shiroko", f"en={r['en']!r} (期望 Shiroko, init_caps)")
    ck(r["grade"] == "LA", f"grade={r['grade']!r} (期望 LA)")

    # 2. 英文全称前缀归一为规范缩写（Snowbreak -> AKE）
    r = resolve("Snowbreak_里芙_Lyfe")
    ck(r["work"] == "AKE", f"Snowbreak_里芙 work={r['work']!r} (期望 AKE, 全称转缩写)")
    ck(r["zh"] == "里芙" and r["en"] == "Lyfe",
       f"cn={r['zh']!r} en={r['en']!r} (期望 里芙/Lyfe)")

    # 2b. 多段英文全称（Azur_Lane 按 _ 拆开）-> 拼接连续 ASCII 段归一为缩写 AL
    r = resolve("Azur_Lane_柴郡_Cheshire_LB")
    ck(r["work"] == "AL", f"Azur_Lane_柴郡 work={r['work']!r} (期望 AL, 拼接归缩写)")
    ck(r["zh"] == "柴郡", f"cn={r['zh']!r} (期望 柴郡)")

    # 2c. 全英文作品名（Ash_Arms -> 拼接查 works 的 "Ash-Arms"）
    r = resolve("Ash_Arms")
    ck(r["work"] == "Ash-Arms", f"Ash_Arms work={r['work']!r} (期望 Ash-Arms)")
    r = resolve("Ash_Arms_夏安")
    ck(r["work"] == "Ash-Arms" and r["zh"] == "夏安",
       f"Ash_Arms_夏安 work={r['work']!r}/cn={r['zh']!r}")

    # 3. Unknown 前缀 + 作品缩写段（Unknown_AKE_xxx -> work=AKE）
    r = resolve("Unknown_AKE_Endministrator_Female")
    ck(r["work"] == "AKE", f"Unknown_AKE_... work={r['work']!r} (期望 AKE)")
    ck(r["zh"] == "" and r["en"] == "Endministrator-Female",
       f"en={r['en']!r} (期望 Endministrator-Female, 同一英文名用 - 连接)")

    # 4. Touhou 前缀（Touhou + 中文 -> work=Touhou）
    r = resolve("Touhou灵梦_Reimu_LC")
    ck(r["work"] == "Touhou", f"Touhou灵梦 work={r['work']!r} (期望 Touhou)")
    ck(r["zh"] == "灵梦", f"cn={r['zh']!r} (期望 灵梦)")

    # 5. 无前缀 + 角色反查作品（柴郡 -> AL, 知识库补作品）
    r = resolve("柴郡_Cheshire")
    ck(r["work"] == "AL" and r["work_source"] == "kb",
       f"柴郡_Cheshire work={r['work']!r}/{r['work_source']!r} (期望 AL/kb)")

    # 6. 跨作品同名冲突（夏安 在 GF 与 GF2 都有）-> Unknown + conflict + 候选作品
    r = resolve("夏安_XiaAn")
    ck(r["work"] == "Unknown" and r.get("conflict") is True,
       f"夏安 冲突 work={r['work']!r} conflict={r.get('conflict')!r} (期望 Unknown/True)")
    ck(sorted(r.get("conflict_works") or []) == ["GF", "GF2"],
       f"conflict_works={sorted(r.get('conflict_works') or [])} (期望 ['GF','GF2'])")

    # 7. 知识库补全：作品已定但缺英文名 -> 自动补 en（阿米娅 -> amiya）
    r = resolve("AK_阿米娅")
    ck(r["work"] == "AK", f"AK_阿米娅 work={r['work']!r}")
    ck(r["en"] == "Amiya", f"en={r['en']!r} (期望 Amiya, 补全+init_caps)")

    # 8. 纯数字英文名 -> SKIP（非角色信息）
    r = resolve("BA_1234")
    ck(r["status"] == "SKIP" and r["notes"] == "numeric EN only",
       f"BA_1234 status={r['status']!r} (期望 SKIP/numeric EN only)")

    # 8b. 大小写前缀归一为规范键（Avemujica -> AveMujica）
    r = resolve("Avemujica_丰川祥子_Togawa-Sakiko_LB")
    ck(r["work"] == "AveMujica", f"Avemujica work={r['work']!r} (期望 AveMujica)")
    ck(r["zh"] == "丰川祥子" and r["en"] == "Togawa-Sakiko",
       f"cn={r['zh']!r} en={r['en']!r}")

    # 8c. `_` 连接的中文皮肤（字段统一用 _ 分隔）-> 剥离为皮肤，输出也规范为 `_`
    r = resolve("AK_阿米娅_泳装")
    ck(r["work"] == "AK" and r["zh"] == "阿米娅",
       f"AK_阿米娅_泳装 work={r['work']!r}/cn={r['zh']!r} (皮肤已剥离)")
    ck(r["new"] == "AK_阿米娅_泳装_Amiya", f"new={r['new']!r} (期望 AK_阿米娅_泳装_Amiya)")
    ck(r.get("cn_skin") == "泳装", f"cn_skin={r.get('cn_skin')!r} (期望 泳装)")

    # 8d. en 多段用 - 连接（同一英文名，Rei_Ayanami -> Rei-Ayanami）
    r = resolve("Unknown_Rei_Ayanami_LD")
    ck(r["en"] == "Rei-Ayanami", f"en={r['en']!r} (期望 Rei-Ayanami)")

    # 8f. CJK 段含空格/冒号（旧命名）-> 知识库过滤未命中 token（枣）并补全 EN
    r = resolve("BA_枣 伊吕波：泳装")
    ck(r["work"] == "BA", f"BA_枣 伊吕波：泳装 work={r['work']!r} (期望 BA)")
    ck(r["zh"] == "伊吕波", f"cn={r['zh']!r} (期望 伊吕波, 未命中'枣'被丢弃)")
    ck(r.get("cn_skin") == "泳装", f"cn_skin={r.get('cn_skin')!r} (期望 泳装)")
    ck(r["en"] == "Iroha", f"en={r['en']!r} (期望 Iroha, 补全+init_caps)")
    ck(r["new"] == "BA_伊吕波_泳装_Iroha", f"new={r['new']!r} (期望 BA_伊吕波_泳装_Iroha)")
    ck("dropped 枣" in r["notes"], f"notes={r['notes']!r} (应含 dropped 枣)")

    # 8e. 中英混合拆分 + 版本剥离 + en 去重 + 反查归 VOC
    r = resolve("Unknown_初音miku_MikU1.0")
    ck(r["work"] == "VOC", f"初音miku work={r['work']!r} (期望 VOC)")
    ck(r["zh"] == "初音" and r["en"] == "Miku",
       f"cn={r['zh']!r} en={r['en']!r} (期望 初音/Miku)")
    ck(r["new"] == "VOC_初音_Miku", f"new={r['new']!r} (期望 VOC_初音_Miku)")

    # 8g. 拼音英文名标准化为数据库规范名（Chuyin -> Miku）
    r = resolve("VOC_初音_Chuyin")
    ck(r["work"] == "VOC", f"VOC_初音_Chuyin work={r['work']!r} (期望 VOC)")
    ck(r["en"] == "Miku", f"en={r['en']!r} (期望 Miku, 拼音标准化)")
    ck(r["new"] == "VOC_初音_Miku", f"new={r['new']!r} (期望 VOC_初音_Miku)")

    # 9. init_caps / normalize_en_key 基础行为
    ck(kb.init_caps("kipfel") == "Kipfel", f"init_caps('kipfel')={kb.init_caps('kipfel')!r}")
    ck(kb.init_caps("Ryou-Yamada") == "Ryou-Yamada",
       f"init_caps('Ryou-Yamada')={kb.init_caps('Ryou-Yamada')!r} (已含大写不动)")
    ck(kb.normalize_en_key("Sorasaki Shiroko") == "sorasakishiroko",
       f"normalize_en_key='{kb.normalize_en_key('Sorasaki Shiroko')}'")

    # 10. build_kb：同中文名不同英文名 -> 合并 en 数组；跨作品不合并
    built = kb.build_kb(["AK_阿米娅_amiya", "AK_阿米娅_amyia", "GF_夏安_xiaan", "GF2_夏安_xiaan2"])
    by_work = {}
    for r in built:
        by_work.setdefault(r["work"], []).append(r)
    amiya = next((r for r in built if r["work"] == "AK"), None)
    ck(amiya is not None and "amiya" in amiya["en"] and "amyia" in amiya["en"],
       f"build_kb AK 阿米娅 en={amiya['en'] if amiya else None} (期望合并 amiya/amyia)")
    # 跨作品"夏安"各自保留（不合并）
    xiaans = [r for r in built if r["zh"] == ["夏安"]]
    ck(len(xiaans) == 2, f"build_kb 跨作品夏安 条数={len(xiaans)} (期望 2，不合并)")

    # 11. role_key 唯一性（en 归一化为小写；同一拼写不同大小写应相等）
    a1 = {"work": "AK", "zh": ["阿米娅"], "en": ["amiya"]}
    a2 = {"work": "AK", "zh": ["阿米娅"], "en": ["AMIYA"]}
    ck(kb.role_key(a1) == kb.role_key(a2),
       f"role_key 大小写不敏感: {kb.role_key(a1)!r} == {kb.role_key(a2)!r}")

    # 12. 作品别名归一为标准键（works.json 顶层键）
    # 12a. 已收录别名精确命中（NGO -> NEO、YGYST -> YogYard）
    r = resolve("NGO_超天酱_KAngel-Nsfw")
    ck(r["work"] == "NEO", f"NGO_超天酱 work={r['work']!r} (期望 NEO, 别名归键)")
    r = resolve("YGYST_特莉波卡_Tlipoca")
    ck(r["work"] == "YogYard", f"YGYST_特莉波卡 work={r['work']!r} (期望 YogYard)")

    # 12b. 未收录别名（全称前缀）唯一命中 -> fuzzy 自动归一（WanderingWitch -> MNT）
    r = resolve("WanderingWitch_伊蕾娜_Elaina")
    ck(r["work"] == "MNT", f"WanderingWitch_伊蕾娜 work={r['work']!r} (期望 MNT, fuzzy 归键)")

    # 12c. ATRI 为作品名与角色名共用 -> work 归 AIRI，en 保留 ATRI
    r = resolve("ATRI_亚托莉_ATRI_LB")
    ck(r["work"] == "AIRI", f"ATRI_亚托莉 work={r['work']!r} (期望 AIRI)")
    ck(r["en"] == "ATRI", f"ATRI_亚托莉 en={r['en']!r} (期望 ATRI)")
    ck(r["new"] == "AIRI_亚托莉_ATRI_LB", f"new={r['new']!r} (期望 AIRI_亚托莉_ATRI_LB)")

    # 12d. 多候选别名（Red -> RA2/RA3/ROH/PCR）不自动归一，仅提示人工
    r = resolve("Red_步兵_Alert-3")
    ck(r["work"] != "RA3", f"Red_步兵_Alert-3 work 不应自动归一为 RA3，实际={r['work']!r}")
    ck("ambiguous work alias" in r["notes"],
       f"Red_步兵 应有 ambiguous work alias 提示，notes={r['notes']!r}")

    # 13. 符号格式化（2026-08-15 重构）：`·`/冒号 先归一为 `_` 再解析
    # 13a. `·` 间隔号 -> 分隔符：OC_泠鸢·登门喜鹊 -> 泠鸢(角色) + 登门喜鹊(皮肤)
    #      （需 OC 角色库有泠鸢；测试用临时注入角色）
    # 先注入 OC 泠鸢 角色用于皮肤识别验证
    test_roles = ROLES + [{"work": "OC", "zh": ["泠鸢"], "en": ["jk"]}]
    kb.build_work_index({"works": WORKS, "roles": []})
    C2, E2, E2C, C2E = kb.build_indexes(test_roles)
    r = kb.resolve_name("OC_泠鸢·登门喜鹊", C2, E2, E2C, C2E)
    ck(r["work"] == "OC", f"OC_泠鸢·登门喜鹊 work={r['work']!r} (期望 OC)")
    ck(r["zh"] == "泠鸢", f"cn={r['zh']!r} (期望 泠鸢, · 已拆分为分隔符)")
    ck(r.get("cn_skin") == "登门喜鹊",
       f"cn_skin={r.get('cn_skin')!r} (期望 登门喜鹊 识别为皮肤)")
    # 候选皮肤：登门喜鹊 若已在 skin_tags.json 则为已知皮肤（不重复收集候选）；
    # 否则出现在 candidate_skins。此处只断言"能识别为皮肤"，不强制候选非空。

    # 13b. 中英混合段 + 冒号分隔（用户例子）：初音Miku: 兔女郎
    #      -> 初音(中文) + Miku(英文) + 兔女郎(皮肤) -> 自动补全作品名
    #      测试 VOC 数据首项为 初音/miku，故补全为 VOC_初音_兔女郎_Miku
    #      （真实仓库首项为 初音未来/Hatsune-Miku，会补全为对应规范名）
    r = resolve("初音Miku: 兔女郎")
    ck(r["work"] == "VOC", f"初音Miku: 兔女郎 work={r['work']!r} (期望 VOC, 冒号已拆分)")
    ck(r["zh"] == "初音" and r["en"] == "Miku",
       f"cn={r['zh']!r} en={r['en']!r} (期望 中英混合段拆分 初音/Miku)")
    ck(r["new"] == "VOC_初音_兔女郎_Miku",
       f"new={r['new']!r} (期望 VOC_初音_兔女郎_Miku, 冒号段为皮肤)")

    # 13c. 连字符 `-` 连接且不在皮肤表 -> 整体（规则3）：Rei-Ayanami 姓氏-名字保持整体
    r = resolve("Unknown_Rei_Ayanami_LD")
    ck(r["en"] == "Rei-Ayanami", f"Rei-Ayanami en={r['en']!r} (姓氏-名字 - 保持整体)")

    print("=" * 50)
    all_ok = all(ok for ok, _ in checks)
    for i, (ok, msg) in enumerate(checks, 1):
        print(f"检查 {i}: {'PASS' if ok else 'FAIL'}  {msg}")
    print("kb_tool 解析测试:", "全部通过" if all_ok else "存在失败")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
