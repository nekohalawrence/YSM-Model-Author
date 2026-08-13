# -*- coding: utf-8 -*-
"""
多作者归档 + generate_model_readmes 联动端到端测试。

场景：
  ysm1 多作者模型：A作者(role=模型) 主 + B作者(role=动画) co-creator
  ysm2 双模型作者：A作者(role=模型) + B作者(role=模型) -> 主作者移动 + 其他复制
预期：
  1) ysm1 移入 Models/0001/，models_meta 记录 co-creator B（含平台信息）
  2) ysm2 同时出现在 Models/0001/ 与 Models/0002/（move + copy）
  3) 联动生成模型 README：含 Co-creator Details；无预览图也有 README
"""
import json
import pathlib
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = pathlib.Path(r"C:\Users\hx\AppData\Local\Temp\ysm_org_multi")
REPO = pathlib.Path(__file__).resolve().parents[2]   # .github/test -> 仓库根
SCRIPTS = REPO / ".github" / "scripts"


def make_ysm(name, stem, authors):
    """构造新版块结构 ysm。authors: [(name, role, {contact: val}), ...]"""
    head = "YSGP\r\n\r\n----------------------- [ Metadata ] -----------------------\r\n\r\n"
    head += f"<name> {name}\r\n"
    for aname, role, contacts in authors:
        head += f"<author> \r\n    <name> {aname}\r\n"
        if role:
            head += f"    <role> {role}\r\n"
        for key, val in contacts.items():
            head += f"    <contact-{key}> {val}\r\n"
    head += "<license> All Rights Reserved\r\n\r\n"
    head += "------------------------ [ Export ] ------------------------\r\n\r\n"
    (ROOT / "inbox" / stem).write_bytes(head.encode("utf-8") + b"\x00" * 50)


def setup():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    (ROOT / "Models" / "0001").mkdir(parents=True)
    (ROOT / "Models" / "0002").mkdir(parents=True)
    (ROOT / "Other-YSM-Models").mkdir()
    (ROOT / "inbox").mkdir()
    for aid, name in [("0001", "#A作者 | #AuthorA"), ("0002", "#B作者 | #AuthorB")]:
        (ROOT / "Models" / aid / "README.md").write_text(
            f"# {aid}\n\n## Author\n\n- **Name**: {name}\n  - **Role**: #模型 #动作 #动画 | #Model #Motion #Animation\n",
            encoding="utf-8")
    (ROOT / "README.md").write_text(
        "<!-- AUTHORS_LIST_START -->\n"
        "| 0001 | [#A作者](.../../Models/0001) | 1 |\n"
        "| 0002 | [#B作者](.../../Models/0002) | 1 |\n"
        "<!-- AUTHORS_LIST_END -->\n", encoding="utf-8")
    (ROOT / "README-EN.md").write_text(
        "<!-- AUTHORS_LIST_START -->\n| 0001 | [#A作者](.../../Models/0001) | 1 |\n"
        "| 0002 | [#B作者](.../../Models/0002) | 1 |\n<!-- AUTHORS_LIST_END -->\n", encoding="utf-8")
    # 复制联动脚本、公共库与数据（使其 WORKSPACE_ROOT 指向临时根，按分类子目录复制）
    COPY_SCRIPTS = {
        "ingest": ["organize_models.py"],
        "publish": ["generate_model_readmes.py", "build_readme_authors.py",
                    "build_authors_index.py"],
    }
    for cat, names in COPY_SCRIPTS.items():
        (ROOT / ".github" / "scripts" / cat).mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copy(SCRIPTS / cat / name, ROOT / ".github" / "scripts" / cat / name)
    if (SCRIPTS / "lib").is_dir():
        shutil.copytree(SCRIPTS / "lib", ROOT / ".github" / "scripts" / "lib")
    if (REPO / ".github" / "data").exists():
        shutil.copytree(REPO / ".github" / "data", ROOT / ".github" / "data")

    # 模拟作者库已与预置作者同步（集中数据 authors.json 是作者信息的唯一事实来源）
    meta_dir = ROOT / ".github" / "data" / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "authors.json").write_text(
        json.dumps({
            "version": 1,
            "generated": "test",
            "authors": {
                "0001": {"name": ["#A作者", "#AuthorA"],
                         "readme": "Models/0001/README.md", "platforms": {}},
                "0002": {"name": ["#B作者", "#AuthorB"],
                         "readme": "Models/0002/README.md", "platforms": {}},
            },
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")

    make_ysm("多作者模型", "多作者模型.ysm",
             [("A作者", "模型，动画", {"Bilibili": "https://bili.example/A", "QQ": "12345"}),
              ("B作者", "动画", {"Bilibili": "https://bili.example/B", "QQ": "88888"})])
    make_ysm("双模型作者", "双模型作者.ysm",
             [("A作者", "模型", {}),
              ("B作者", "模型", {})])


def main():
    setup()
    r = subprocess.run([sys.executable, str(SCRIPTS / "ingest" / "organize_models.py"),
                        str(ROOT / "inbox"), "--apply", "--root", str(ROOT),
                        "--with-authors-index", "--with-gen-readmes", "--with-readme-table",
                        "--verbose"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT))
    print(r.stdout)
    if r.returncode != 0:
        print("STDERR:", r.stderr)
        return 1

    checks = []
    # 1 ysm1 主作者 A 移动 -> Models/0001/多作者模型/
    checks.append((ROOT / "Models/0001/多作者模型/多作者模型.ysm").is_file())
    # 2 ysm2 复制到两个 model 作者目录（A 移动 + B 复制）
    checks.append((ROOT / "Models/0001/双模型作者/双模型作者.ysm").is_file())
    checks.append((ROOT / "Models/0002/双模型作者/双模型作者.ysm").is_file())
    # 3 models_meta 记录 co-creator（键 0001/多作者模型，B作者 带平台）
    meta = json.loads((ROOT / ".github/data/meta/models_meta.json").read_text(encoding="utf-8"))
    co1 = meta["0001/多作者模型"]["co_creators"]
    checks.append(any(c["name"] == "B作者" and c["role"] == "动画" for c in co1))
    b_platforms = next(c["platforms"] for c in co1 if c["name"] == "B作者")
    checks.append("SocialPlatform" in b_platforms and "GroupChat" in b_platforms)
    # 4 0002/双模型作者 的 co-creator 是 A作者
    co2 = meta["0002/双模型作者"]["co_creators"]
    checks.append(any(c["name"] == "A作者" for c in co2))
    # 5 联动生成了 README：无预览图也生成 + 含 Co-creator Details
    r1 = (ROOT / "Models/0001/多作者模型/README.md")
    checks.append(r1.is_file() and "Co-creator Details" in r1.read_text(encoding="utf-8"))
    r2 = (ROOT / "Models/0002/双模型作者/README.md")
    checks.append(r2.is_file() and "Co-creator Details" in r2.read_text(encoding="utf-8"))
    txt1 = r1.read_text(encoding="utf-8")
    checks.append("- **Name**: B作者" in txt1
                  and "**SocialPlatform**: Bilibili: https://bili.example/B" in txt1)
    # 6 联动更新根 README 索引
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    checks.append("| 0002 |" in root_readme)

    print("=" * 50)
    all_ok = all(checks)
    for i, ok in enumerate(checks, 1):
        print(f"检查 {i}: {'PASS' if ok else 'FAIL'}")
    print("端到端结果:", "全部通过" if all_ok else "存在失败")
    if not all_ok:
        print("--- 生成的多作者模型 README ---")
        print((ROOT / "Models/0001/多作者模型/README.md").read_text(encoding="utf-8"))
    shutil.rmtree(ROOT, ignore_errors=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
