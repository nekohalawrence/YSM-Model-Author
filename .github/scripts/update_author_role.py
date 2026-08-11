import sys
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent
MODELS_DIR = WORKSPACE_ROOT / 'Models'

TARGET_ROLE = "#模型 #动作 #动画 | #Model #Motion #Animation"

def repair_and_update_author_block(content: str) -> tuple[str, bool]:
    """修复 SocialPlatform 丢失问题，规范缩进并更新 Role"""
    # 1. 隔离匹配 ## Author 区块
    author_match = re.search(r'(##\s*Author\b.*?)(?=\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
    if not author_match:
        return content, False

    author_block = author_match.group(1)
    original_block = author_block

    # 2. 自动修复被误删的 SocialPlatform 节点
    if not re.search(r'-\s*\*\*SocialPlatform\*\*', author_block, re.IGNORECASE):
        # 查找被孤立的社交子平台节点 (如 Bilibili, YouTube 等)
        sub_platform_match = re.search(
            r'(\n[ \t]*-[ \t]*\*\*(?:Bilibili|YouTube|Sketchfab|Twitter|X)\*\*:.*)',
            author_block,
            re.IGNORECASE
        )
        if sub_platform_match:
            # 根据子节点自动推导标签
            tags = []
            if re.search(r'\*\*Bilibili\*\*', author_block, re.I): tags.append('#Bilibili')
            if re.search(r'\*\*YouTube\*\*', author_block, re.I): tags.append('#YouTube')
            if re.search(r'\*\*Sketchfab\*\*', author_block, re.I): tags.append('#Sketchfab')
            if re.search(r'\*\*(?:Twitter|X)\*\*', author_block, re.I): tags.append('#Twitter')
            tag_str = ' '.join(tags) if tags else '#Bilibili'

            # 补充补全 - **SocialPlatform**:
            inserted_text = f'\n  - **SocialPlatform**: {tag_str}' + sub_platform_match.group(1)
            author_block = author_block[:sub_platform_match.start(1)] + inserted_text + author_block[sub_platform_match.end(1):]

    # 3. 安全更新 Role 内容 (精确止于下一个 - ** 节点)
    role_pattern = r'([ \t]*-[ \t]*\*\*Role\*\*\s*:)[^\n\r]*(?:[\r\n]+[ \t]*(?!-[ \t]*\*\*|##)[^\n\r]*)*'
    if re.search(role_pattern, author_block, re.IGNORECASE):
        author_block = re.sub(
            role_pattern,
            f'  - **Role**: {TARGET_ROLE}',
            author_block,
            count=1,
            flags=re.IGNORECASE
        )

    # 4. 统一标准化缩进 (按模板: 一级 0 空格，二级 2 空格，三级 4 空格)
    author_block = re.sub(r'^[ \t]*-[ \t]*\*\*(Role|SocialPlatform|SupportPlatform|GroupChat)\*\*', r'  - **\1**', author_block, flags=re.MULTILINE)
    author_block = re.sub(r'^[ \t]*-[ \t]*\*\*(Bilibili|YouTube|Sketchfab|Twitter|X|Afdian|ko-fi|QQ)\*\*', r'    - **\1**', author_block, flags=re.MULTILINE)

    if author_block != original_block:
        updated_content = content[:author_match.start(1)] + author_block + content[author_match.end(1):]
        return updated_content, True

    return content, False


def process_single_file(readme_path: Path):
    if not readme_path.is_file():
        print(f"Error: File not found: {readme_path}")
        return

    content = readme_path.read_text(encoding='utf-8', errors='ignore')
    updated_content, is_modified = repair_and_update_author_block(content)

    if is_modified and updated_content != content:
        readme_path.write_text(updated_content, encoding='utf-8')
        print(f"Fixed & Updated: {readme_path.relative_to(WORKSPACE_ROOT)}")
    else:
        print(f"Skipped (No change needed): {readme_path.relative_to(WORKSPACE_ROOT)}")


def process_all_authors():
    if not MODELS_DIR.is_dir():
        print(f"Error: {MODELS_DIR} directory does not exist.")
        return

    updated_count = 0
    for author_dir in sorted(MODELS_DIR.iterdir()):
        if author_dir.is_dir() and author_dir.name.isdigit() and len(author_dir.name) == 4:
            for fname in ['README.md', 'readme.md']:
                readme_path = author_dir / fname
                if readme_path.is_file():
                    content = readme_path.read_text(encoding='utf-8', errors='ignore')
                    updated_content, is_modified = repair_and_update_author_block(content)
                    if is_modified and updated_content != content:
                        readme_path.write_text(updated_content, encoding='utf-8')
                        print(f"Fixed & Updated: {readme_path.relative_to(WORKSPACE_ROOT)}")
                        updated_count += 1
                    break

    print(f"\nBatch process completed. Total fixed/updated: {updated_count}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        folder_id = sys.argv[1].zfill(4)
        target_readme = MODELS_DIR / folder_id / 'README.md'
        print(f"Running fix for author folder: {folder_id}")
        process_single_file(target_readme)
    else:
        print("Running batch fix and update for all authors...")
        process_all_authors()