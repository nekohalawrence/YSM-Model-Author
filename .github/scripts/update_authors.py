import os
import re

readme_path = "README.md"
readme_en_path = "README-EN.md"
models_dir = "models"

if not os.path.isdir(models_dir):
    print(f"Error: {models_dir} directory not found.")
    exit(1)

if not os.path.isfile(readme_en_path):
    print(f"Error: {readme_en_path} not found.")
    exit(1)

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

    if not readme_file:
        author_name = "暂无"
        model_count = 0
        rows.append((folder, author_name, model_count, link))
        continue

    with open(readme_file, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r"-\s*作者名称[:：]\s*(.+?)(?:\n|$)", content, re.DOTALL | re.MULTILINE)
    author_name = match.group(1).strip() if match else "暂无"

    model_count = sum(
        1
        for entry in os.scandir(full_folder_path)
        if entry.is_dir() and not entry.name.startswith('.')
    )
    rows.append((folder, author_name, model_count, link))

def build_table(is_en):
    if is_en:
        header = "| ID | Author Name | Model Count |"
        separator = "| --- | --- | ---: |"
        empty_row = "| - | None | 0 |"
    else:
        header = "| 编号 | 作者名称 | 模型数量 |"
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