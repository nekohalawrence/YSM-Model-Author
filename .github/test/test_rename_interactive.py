# -*- coding: utf-8 -*-
"""
02_rename_model_files&folders.py --apply 的交互学习 e2e 测试（两个场景）。

场景 1 跨作品同名冲突：
  - 数据库预置 GF_夏安 / GF2_夏安（纯手工条目，无自动构建）
  - 夏安_Chian（无前缀 -> 反查命中 GF、GF2 两个作品 -> 冲突）
  --apply 展示候选「0=GF 1=GF2」，输入 "0" 选 GF 后：
    收录进数据库 + 补全重命名为 "GF_夏安_Chian"。

场景 2 Windows 大小写修正：
  - Avemujica_丰川祥子_LB（前缀大小写不规范，works 键是 AveMujica）
  --apply 应执行大小写修正重命名为 "AveMujica_丰川祥子_LB"，
    而不是误报「目标已存在」（Windows 大小写不敏感）。

场景 3 皮肤入库：
  - 未收录带皮肤角色（阿米娅_泳装）-> --learn 收录时皮肤写入皮肤表（AK 专属）。

场景 4 仅 --apply 冲突选择：
  - 不带 --learn 只跑 --apply，遇跨作品同名冲突（夏安 -> GF/GF2）：
    逐项询问归属，输入 "0" 选 GF -> 收录数据库 + 补前缀重命名为 "GF_夏安_Chian"。

场景 5 --apply --skip-conflict：
  - --apply 加 --skip-conflict：跳过冲突选择、不处理，保持原文件夹名，
    不生成 Unknown_ 前缀（防止无人值守卡住）。

运行：python .github/test/test_rename_interactive.py（0=通过，1=失败）
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(tempfile.gettempdir()) / "ysm_rename_interactive"
REPO = pathlib.Path(__file__).resolve().parents[2]   # .github/test -> 仓库根
SCRIPTS = REPO / ".github" / "scripts"
SCRIPT = SCRIPTS / "models_organize" / "02_rename_model_files&folders.py"


def setup(works: dict, folders: list[str]) -> None:
    """构建最小临时仓库：Models/0001/<folders> + 复制 scripts/data（works 可定制）。"""
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / "Models" / "0001").mkdir(parents=True)
    (ROOT / "Other-YSM-Models").mkdir(parents=True)
    (ROOT / "Models" / "0001" / "README.md").write_text(
        "# 0001\n\n## Author\n\n- **Name**: #A作者 | #AuthorA\n"
        "  - **Role**: #模型 | #Model\n",
        encoding="utf-8")
    for name in folders:
        d = ROOT / "Models" / "0001" / name
        d.mkdir(parents=True)
        (d / f"{name}.ysm").write_bytes(
            "YSGP\r\n<name> 测试\r\n[ Export ]\r\n\x00".encode("utf-8"))
    (ROOT / "README.md").write_text("临时仓库 README\n", encoding="utf-8")
    (ROOT / "README-EN.md").write_text("Temp README\n", encoding="utf-8")

    (ROOT / ".github" / "scripts" / "models_organize").mkdir(parents=True)
    shutil.copy(SCRIPT, ROOT / ".github" / "scripts" / "models_organize"
                / "02_rename_model_files&folders.py")
    if (SCRIPTS / "lib").is_dir():
        shutil.copytree(SCRIPTS / "lib", ROOT / ".github" / "scripts" / "lib")
    data_dir = ROOT / ".github" / "data" / "model-info"
    data_dir.mkdir(parents=True)
    # 新格式：work + roles 合并到 character/<作品>.json（作品键由 work.name 决定）
    (data_dir / "character").mkdir(parents=True)
    for wk, entry in works.items():
        (data_dir / "character" / f"{wk}.json").write_text(
            json.dumps({"work": {"name": wk, **entry}, "roles": []},
                       ensure_ascii=False),
            encoding="utf-8")
    # 皮肤表复制到临时仓库（text.py 从仓库 data 加载；缺失则写含泳装的 common 兜底）
    src_skin = REPO / ".github" / "data" / "model-info" / "skin_tags.json"
    if src_skin.is_file():
        shutil.copy(src_skin, data_dir / "skin_tags.json")
    else:
        (data_dir / "skin_tags.json").write_text(
            json.dumps({"common": {"zh": ["泳装"], "en": ["swimsuit"]}},
                       ensure_ascii=False), encoding="utf-8")


def run_rename(stdin_text: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """在临时仓库运行 rename-folders --learn --apply（可追加额外参数），返回结果。"""
    args = ["--learn", "--apply"] + (extra_args or [])
    return subprocess.run(
        [sys.executable, str(ROOT / ".github" / "scripts" / "models_organize"
                          / "02_rename_model_files&folders.py")] + args,
        input=stdin_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(ROOT))


def case_skin_conflict() -> list[tuple[str, bool]]:
    """场景 1：跨作品同名冲突 -> 展示候选 -> 编号选择 -> 收录 + 补全重命名。"""
    setup({"GF": {"en": ["Girls Frontline"]},
           "GF2": {"en": ["Girls Frontline 2"]}},
          ["夏安_Chian"])
    # 纯手工维护：预置数据库角色条目（GF/GF2 都有「夏安」），供跨作品冲突检测
    char_dir = ROOT / ".github/data/model-info/character"
    (char_dir / "GF.json").write_text(json.dumps({
        "work": {"name": "GF", "en": ["Girls Frontline"]},
        "roles": [{"zh": ["夏安"], "en": ["xiaan"]}],
    }, ensure_ascii=False), encoding="utf-8")
    (char_dir / "GF2.json").write_text(json.dumps({
        "work": {"name": "GF2", "en": ["Girls Frontline 2"]},
        "roles": [{"zh": ["夏安"], "en": ["xiaan-gf2"]}],
    }, ensure_ascii=False), encoding="utf-8")
    r = run_rename("0\n")
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)

    checks: list[tuple[str, bool]] = [
        ("退出码 0", r.returncode == 0),
        ("冲突候选展示", "同名角色存在于多个作品" in r.stdout and "0=GF" in r.stdout),
        ("补全重命名", (ROOT / "Models/0001/GF_夏安_Chian").is_dir()),
        ("旧名已移除", not (ROOT / "Models/0001/夏安_Chian").exists()),
        ("收录到数据库",
         (ROOT / ".github/data/model-info/character/GF.json").is_file()),
    ]
    if checks[4][1]:
        data = json.loads((ROOT / ".github/data/model-info/character/GF.json")
                          .read_text(encoding="utf-8"))
        # 新格式：角色在顶层 roles 数组（条目不存 work，归属由 work.name 决定）
        roles = data.get("roles", []) if isinstance(data, dict) else data
        has_entry = any("夏安" in (e.get("zh") or []) for e in roles)
        checks.append(("数据库条目写入", has_entry))
    else:
        checks.append(("数据库条目写入", False))
    return checks


def case_casefix() -> list[tuple[str, bool]]:
    """场景 2：Windows 大小写修正（Avemujica -> AveMujica），不应误报已存在。"""
    setup({"AveMujica": {"en": ["AveMujica"]}}, ["Avemujica_丰川祥子_LB"])
    r = run_rename("")  # 无 unknown，不询问
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)
    # Windows 大小写不敏感：用目录实际名（区分大小写）判断，而非 exists()
    actual = [p.name for p in (ROOT / "Models" / "0001").iterdir()]
    return [
        ("退出码 0", r.returncode == 0),
        ("大小写修正成功", "AveMujica_丰川祥子_LB" in actual),
        ("旧名已移除", "Avemujica_丰川祥子_LB" not in actual),
        ("无目标已存在误报", "目标已存在" not in (r.stderr or "")),
    ]


def case_skin_learn() -> list[tuple[str, bool]]:
    """场景 3：未收录带皮肤角色 -> 收录时把皮肤写入数据库 skin 字段。"""
    setup({}, ["阿米娅_泳装"])
    r = run_rename("AK\n")
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)
    checks: list[tuple[str, bool]] = [
        ("退出码 0", r.returncode == 0),
        ("补全重命名", (ROOT / "Models/0001/AK_阿米娅_泳装").is_dir()),
    ]
    skf = ROOT / ".github/data/model-info/skin_tags.json"
    if skf.is_file():
        tags = json.loads(skf.read_text(encoding="utf-8"))
        has_skin = "泳装" in (tags.get("AK") or {}).get("zh", [])
        checks.append(("皮肤写入皮肤表", has_skin))
    else:
        checks.append(("皮肤写入皮肤表", False))
    return checks


def _write_conflict_kb() -> None:
    """预置 GF/GF2 都含「夏安」的数据库（跨作品同名冲突场景）。"""
    char_dir = ROOT / ".github/data/model-info/character"
    (char_dir / "GF.json").write_text(json.dumps({
        "work": {"name": "GF", "en": ["Girls Frontline"]},
        "roles": [{"zh": ["夏安"], "en": ["xiaan"]}],
    }, ensure_ascii=False), encoding="utf-8")
    (char_dir / "GF2.json").write_text(json.dumps({
        "work": {"name": "GF2", "en": ["Girls Frontline 2"]},
        "roles": [{"zh": ["夏安"], "en": ["xiaan-gf2"]}],
    }, ensure_ascii=False), encoding="utf-8")


def case_apply_conflict() -> list[tuple[str, bool]]:
    """场景 4：仅 --apply（不带 --learn）遇跨作品同名冲突 -> 交互选择归属并收录。"""
    setup({"GF": {"en": ["Girls Frontline"]},
           "GF2": {"en": ["Girls Frontline 2"]}},
          ["夏安_Chian"])
    _write_conflict_kb()
    # 仅 --apply（无 --learn）：遇冲突仍应让用户选择归属
    r = subprocess.run(
        [sys.executable, str(ROOT / ".github/scripts/models_organize"
                          / "02_rename_model_files&folders.py"), "--apply"],
        input="0\n", capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(ROOT))
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)
    checks: list[tuple[str, bool]] = [
        ("退出码 0", r.returncode == 0),
        ("--apply 冲突选择提示", "选择归属作品" in r.stdout and "0=GF" in r.stdout),
        ("选择后补全重命名", (ROOT / "Models/0001/GF_夏安_Chian").is_dir()),
        ("旧名已移除", not (ROOT / "Models/0001/夏安_Chian").exists()),
        ("收录到数据库", (ROOT / ".github/data/model-info/character/GF.json").is_file()),
    ]
    return checks


def case_apply_skip_conflict() -> list[tuple[str, bool]]:
    """场景 5：--apply --skip-conflict -> 跳过选择、不处理，保持原文件夹名。"""
    setup({"GF": {"en": ["Girls Frontline"]},
           "GF2": {"en": ["Girls Frontline 2"]}},
          ["夏安_Chian"])
    _write_conflict_kb()
    r = subprocess.run(
        [sys.executable, str(ROOT / ".github/scripts/models_organize"
                          / "02_rename_model_files&folders.py"),
         "--apply", "--skip-conflict"],
        input="", capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(ROOT))
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)
    checks: list[tuple[str, bool]] = [
        ("退出码 0", r.returncode == 0),
        ("跳过提示", "--skip-conflict: 跳过" in r.stdout),
        ("保持原文件夹名", (ROOT / "Models/0001/夏安_Chian").is_dir()),
        ("未生成 Unknown 前缀", not any(
            p.name.startswith("Unknown_") for p in (ROOT / "Models/0001").iterdir())),
    ]
    return checks


def main() -> int:
    all_ok = True
    total = 0
    for title, checks in [("跨作品冲突(learn)", case_skin_conflict()),
                          ("大小写修正", case_casefix()),
                          ("皮肤入库", case_skin_learn()),
                          ("仅apply冲突选择", case_apply_conflict()),
                          ("apply跳过冲突", case_apply_skip_conflict())]:
        print("=" * 50)
        print(f"== {title} ==")
        for i, (name, ok) in enumerate(checks, 1):
            print(f"  检查 {i}: {'PASS' if ok else 'FAIL'}  {name}")
            all_ok = all_ok and ok
            total += 1
    shutil.rmtree(ROOT, ignore_errors=True)
    print("=" * 50)
    print(f"交互学习测试: {'全部通过' if all_ok else '存在失败'}（{total} 项）")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
