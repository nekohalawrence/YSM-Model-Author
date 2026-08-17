# -*- coding: utf-8 -*-
"""
02_rename_model_folders.py --apply 纯重命名 e2e 测试（知识库维护已分离到 kb_tool）。

02 只负责重命名、不收录数据库：Unknown / 跨作品同名冲突 直接标 SKIP 保持原文件夹名。

场景 1 Windows 大小写修正：
  - Avemujica_丰川祥子_LB（前缀大小写不规范，works 键是 AveMujica）
  --apply 应执行大小写修正重命名为 "AveMujica_丰川祥子_LB"，
    而不是误报「目标已存在」（Windows 大小写不敏感）。

场景 2 跨作品同名冲突跳过：
  - 数据库预置 GF_夏安 / GF2_夏安；夏安_Chian（无前缀 -> 命中两个作品 -> 冲突）
  --apply 不收录、不询问：保持原文件夹名，不生成 Unknown_ 前缀。

场景 3 Unknown 加前缀：
  - 阿米娅_泳装（无作品前缀、知识库未收录）-> --apply 加 Unknown_ 前缀重命名，不收录数据库。

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
SCRIPT = SCRIPTS / "models_organize" / "02_rename_model_folders.py"


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
                / "02_rename_model_folders.py")
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
    """在临时仓库运行 rename-folders --apply（可追加额外参数），返回结果。"""
    args = ["--apply"] + (extra_args or [])
    return subprocess.run(
        [sys.executable, str(ROOT / ".github" / "scripts" / "models_organize"
                          / "02_rename_model_folders.py")] + args,
        input=stdin_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(ROOT))


def case_casefix() -> list[tuple[str, bool]]:
    """场景 2：Windows 大小写修正（Avemujica -> AveMujica），不应误报已存在。"""
    setup({"AveMujica": {"en": ["AveMujica"]}}, ["Avemujica_丰川祥子_LB"])
    # 预置丰川祥子角色（en 留空避免自动补全英文名）：parse2 6.5b 前缀校验要求
    # 角色命中数据库，否则会把 AveMujica 前缀降级为 Unknown，大小写修正无从验证。
    # 预置后角色命中、前缀保留，仍验证「大小写不敏感不误报已存在」。
    char_dir = ROOT / ".github/data/model-info/character"
    (char_dir / "AveMujica.json").write_text(json.dumps({
        "work": {"name": "AveMujica", "en": ["AveMujica"]},
        "roles": [{"zh": ["丰川祥子"], "en": []}],
    }, ensure_ascii=False), encoding="utf-8")
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


def case_conflict_skip() -> list[tuple[str, bool]]:
    """场景 2：跨作品同名冲突 -> --apply 不收录、不询问，保持原文件夹名。"""
    setup({"GF": {"en": ["Girls Frontline"]},
           "GF2": {"en": ["Girls Frontline 2"]}},
          ["夏安_Chian"])
    _write_conflict_kb()
    r = run_rename("")
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)
    checks: list[tuple[str, bool]] = [
        ("退出码 0", r.returncode == 0),
        ("冲突保持提示", "跨作品同名冲突" in r.stdout),
        ("保持原文件夹名", (ROOT / "Models/0001/夏安_Chian").is_dir()),
        ("未生成 Unknown 前缀", not any(
            p.name.startswith("Unknown_") for p in (ROOT / "Models/0001").iterdir())),
    ]
    return checks


def case_unknown_skip() -> list[tuple[str, bool]]:
    """场景 3：Unknown 无作品 -> --apply 加 Unknown_ 前缀重命名，不收录数据库。"""
    setup({}, ["阿米娅_泳装"])
    r = run_rename("")
    print(r.stdout)
    if r.stderr:
        print("STDERR:", r.stderr, file=sys.stderr)
    checks: list[tuple[str, bool]] = [
        ("退出码 0", r.returncode == 0),
        ("已加 Unknown 前缀", (ROOT / "Models/0001/Unknown_阿米娅_泳装").is_dir()),
        ("原名已移除", not (ROOT / "Models/0001/阿米娅_泳装").is_dir()),
    ]
    return checks


def main() -> int:
    all_ok = True
    total = 0
    for title, checks in [("大小写修正", case_casefix()),
                          ("跨作品冲突跳过", case_conflict_skip()),
                          ("Unknown跳过", case_unknown_skip())]:
        print("=" * 50)
        print(f"== {title} ==")
        for i, (name, ok) in enumerate(checks, 1):
            print(f"  检查 {i}: {'PASS' if ok else 'FAIL'}  {name}")
            all_ok = all_ok and ok
            total += 1
    shutil.rmtree(ROOT, ignore_errors=True)
    print("=" * 50)
    print(f"重命名测试: {'全部通过' if all_ok else '存在失败'}（{total} 项）")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
