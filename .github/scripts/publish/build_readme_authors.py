import os
import re
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import readme as lib_readme

readme_path = "README.md"
readme_en_path = "README-EN.md"
models_dir = "Models"

if not os.path.isdir(models_dir):
    print(f"Error: {models_dir} directory not found.")
    exit(1)

if not os.path.isfile(readme_en_path):
    print(f"Error: {readme_en_path} not found.")
    exit(1)

def extract_primary_author_name(content: str) -> str:
    """提取主作者名称，避开 Co-creator 区块（复用 lib/readme.py 统一实现）"""
    return lib_readme.extract_primary_author_name(content)

# 作者名称优先取自集中数据 authors.json（避免逐个扫描作者 README）
authors_index = lib_readme.load_authors_index().get('authors') or {}

folder_pattern = re.compile(r"^(\d{4})$")
rows = []

for folder in sorted(os.listdir(models_dir)):
    full_folder_path = os.path.join(models_dir, folder)
    if not (os.path.isdir(full_folder_path) and folder_pattern.match(folder)):
        continue

    readme_file = None
    for fname in ["README.md", "readme.md", "Readme.md"]:
        path = os.path.join(full_folder_path, fname)
        if os.path.isfile(path):
            readme_file = path
            break

    link = f".../../{models_dir}/{folder}"

    # 集中数据优先；未收录或缺失时回退读 README（name 为数组，取规范名）
    entry = authors_index.get(folder) or {}
    names = entry.get('name', '') if isinstance(entry.get('name'), list) else (
        lib_readme.split_author_names(entry.get('name', '')) if entry.get('name') else [])
    author_name = names[0] if names else ''

    if readme_file and not author_name:
        with open(readme_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        author_name = extract_primary_author_name(content)

    if not author_name:
        author_name = "暂无"

    model_count = sum(
        1
        for entry in os.scandir(full_folder_path)
        if entry.is_dir() and not entry.name.startswith('.')
    )
    rows.append((folder, author_name, model_count, link))

def build_table(is_en):
    if is_en:
        header = "| ID | Author Name | Total Models |"  # Model Count -> Total Models
        separator = "| --- | --- | ---: |"
        empty_row = "| - | None | 0 |"
    else:
        header = "| 编号 | 作者名称 | 收录数量 |"     # 模型数量 -> 收录数量
        separator = "| --- | --- | ---: |"
        empty_row = "| - | 暂无 | 0 |"

    lines = [header, separator]
    for folder, author_name, model_count, link in rows:
        safe_author_name = author_name.replace("|", "\\|")
        if is_en:
            author_label = safe_author_name if safe_author_name != "暂无" else "None"
            lines.append(f"| {folder} | [{author_label}]({link}) | {model_count} |")
        else:
            lines.append(f"| {folder} | [{safe_author_name}]({link}) | {model_count} |")

    return "\n".join(lines) if rows else f"{header}\n{separator}\n{empty_row}"

def update_readme(path, is_en):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    start = "<!-- AUTHORS_LIST_START -->"
    end = "<!-- AUTHORS_LIST_END -->"

    if start not in content or end not in content:
        print(f"Error: Markers not found in {path}")
        exit(1)

    before = content.split(start, 1)[0] + start + "\n"
    after = "\n" + end + content.split(end, 1)[1]

    new_list = build_table(is_en)
    updated = before + new_list + after

    if updated != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"Updated {path} with {len(rows)} rows.")
        return True
    else:
        print(f"No changes in {path}")
        return False

update_readme(readme_path, False)
update_readme(readme_en_path, True)
