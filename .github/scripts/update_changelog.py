import os
import re
import subprocess
from datetime import date

readme_path = 'README.md'
models_dir = 'models'
start_marker = '<!-- CHANGELOG_AUTOGEN_START -->'
end_marker = '<!-- CHANGELOG_AUTOGEN_END -->'
auto_marker = '<!-- AUTO_LOGS_START -->'
manual_marker = '<!-- MANUAL_LOGS_START -->'

if not os.path.isfile(readme_path):
    raise SystemExit(f'Readme not found: {readme_path}')

def file_category(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in {'.ysm', '.zip', '.7z', '.rar', '.tar', '.gz'}:
        return 'model'
    if ext in {'.md'}:
        return 'readme'
    if ext in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}:
        return 'image'
    return 'other'

today_str = date.today().isoformat()
since_time = f"{today_str} 00:00:00"

try:
    cmd = ['git', 'log', f'--since={since_time}', '--name-status', '--pretty=format:COMMIT_START']
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    git_output = result.stdout
except Exception as e:
    print(f"Failed to execute git log: {e}")
    raise SystemExit(1)

changed_authors = {}

for line in git_output.splitlines():
    line = line.strip()
    if not line or line == 'COMMIT_START':
        continue
    
    parts = line.split('\t')
    if len(parts) < 2:
        continue
    
    status = parts[0]
    path = parts[-1].replace('\\', '/')
    path_parts = path.split('/')
    
    if len(path_parts) >= 2 and path_parts[0] == models_dir and re.fullmatch(r'\d{4}', path_parts[1]):
        folder = path_parts[1]
        info = changed_authors.setdefault(folder, {
            'added': 0, 'modified': 0, 'deleted': 0,
            'model': 0, 'readme': 0, 'image': 0, 'other': 0,
        })
        
        if status.startswith('A'):
            info['added'] += 1
        elif status.startswith('D'):
            info['deleted'] += 1
        else:
            info['modified'] += 1
            
        info[file_category(path)] += 1

if not changed_authors:
    print('No changes detected in models directory for today. Nothing to update.')
    raise SystemExit(0)

def find_author_name(folder):
    folder_path = os.path.join(models_dir, folder)
    if not os.path.isdir(folder_path):
        return None
    for candidate in ['README.md', 'readme.md', 'Readme.md']:
        candidate_path = os.path.join(folder_path, candidate)
        if os.path.isfile(candidate_path):
            with open(candidate_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            match = re.search(r'-\s*作者名称\s*[:：]\s*(.+?)(?:\n|$)', text)
            if match:
                return match.group(1).strip()
            break
    return None

new_entries_zh = []

for folder in sorted(changed_authors):
    author_name = find_author_name(folder) or folder
    author_text = author_name.replace('|', '\\|')
    stats = changed_authors[folder]

    zh_details = []
    if stats['model']:
        zh_details.append(f"{stats['model']} 个模型文件")
    if stats['image']:
        zh_details.append(f"{stats['image']} 张预览图")
    if stats['readme']:
        zh_details.append(f"{stats['readme']} 个 README")
    if stats['other']:
        zh_details.append(f"{stats['other']} 个其他文件")

    zh_status = []
    if stats['added']:
        zh_status.append(f"新增 {stats['added']}")
    if stats['modified']:
        zh_status.append(f"更新 {stats['modified']}")
    if stats['deleted']:
        zh_status.append(f"删除 {stats['deleted']}")

    zh_summary = '、'.join(zh_details) if zh_details else '若干文件'
    if zh_status:
        zh_summary += f"（{'，'.join(zh_status)}）"

    entry_base = f"- chore: models/{folder}: [#{folder} - {author_text}](.../../{models_dir}/{folder})"
    new_entries_zh.append(f"{entry_base} - 更新了 {zh_summary}")

with open(readme_path, 'r', encoding='utf-8') as f:
    content = f.read()

if start_marker not in content or end_marker not in content:
    raise SystemExit(f'Change log markers not found in {readme_path}')

prefix, rest = content.split(start_marker, 1)
block, suffix = rest.split(end_marker, 1)

def parse_sections(block_text):
    pre_heading_lines = []
    sections = []
    current_heading = None
    current_lines = []
    for line in block_text.splitlines():
        if line.startswith('# '):
            if current_heading is not None:
                sections.append((current_heading, current_lines))
            else:
                if current_lines:
                    pre_heading_lines.extend(current_lines)
            current_heading = line.strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)
            else:
                pre_heading_lines.append(line)
    if current_heading is not None:
        sections.append((current_heading, current_lines))

    merged = []
    heading_to_index = {}
    for heading, lines in sections:
        if heading in heading_to_index:
            idx = heading_to_index[heading]
            if merged[idx][1] and lines:
                merged[idx][1].append('')
            merged[idx][1].extend(lines)
        else:
            heading_to_index[heading] = len(merged)
            merged.append([heading, list(lines)])
    return pre_heading_lines, [(heading, lines) for heading, lines in merged]

def split_section_lines(lines):
    auto_lines, manual_lines = [], []
    state = 'manual'
    for line in lines:
        if line.strip() == auto_marker:
            state = 'auto'
            continue
        if line.strip() == manual_marker:
            state = 'manual'
            continue
        if state == 'auto':
            auto_lines.append(line)
        else:
            manual_lines.append(line)
    return auto_lines, manual_lines

pre_heading_lines, sections = parse_sections(block)
new_sections = []
today_found = False
today_heading = f'# {today_str}'

for heading, lines in sections:
    if heading == today_heading:
        _, manual_lines = split_section_lines(lines)
        new_lines = [auto_marker] + new_entries_zh + ['', manual_marker]
        if manual_lines:
            new_lines.extend(manual_lines)
        new_sections.append((heading, new_lines))
        today_found = True
    else:
        new_sections.append((heading, lines))

if not today_found:
    new_sections.append((today_heading, [auto_marker] + new_entries_zh + ['', manual_marker]))

new_sections.sort(key=lambda item: item[0], reverse=True)

def render_sections(sections_list, pre_lines):
    lines = []
    if pre_lines:
        lines.extend(pre_lines)
        lines.append('')
    for heading, section_lines in sections_list:
        lines.extend([heading, ''])
        if section_lines:
            lines.extend(section_lines)
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'

new_block = render_sections(new_sections, pre_heading_lines)
updated_content = prefix + start_marker + '\n' + new_block + end_marker + suffix

if updated_content != content:
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    print(f'Updated {readme_path} changelog for today.')