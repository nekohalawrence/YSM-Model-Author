import sys
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = WORKSPACE_ROOT / 'Models'

TARGET_ROLE = "#模型 #动作 #动画 | #Model #Motion #Animation"

def update_role_in_content(content: str) -> tuple[str, bool]:
    """仅在 ## Author 区块内替换 Role 内容，并清除错位换行与异常空格"""
    # 1. 隔离匹配 ## Author 区块（防止影响 ## Co-creator）
    author_match = re.search(r'(##\s*Author\b.*?)(?=\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
    if not author_match:
        return content, False

    author_block = author_match.group(1)

    # 2. 匹配从 "- **Role**:" 开始到下一个属性（如 "- **SocialPlatform**:"）之间的所有内容（包含错位换行）
    # 直接将其全量重写为标准的单行格式
    new_author_block, count = re.subn(
        r'(-\s*\*\*Role\*\*\s*:)[^\n\r]*[\r\n\s\xa0]*(?:#模型.*?)?(?=\n\s*-\s*\*\*|\n##|\Z)',
        f'  - **Role**: {TARGET_ROLE}',
        author_block,
        count=1,
        flags=re.IGNORECASE | re.DOTALL
    )

    if count == 0:
        return content, False

    updated_content = content[:author_match.start(1)] + new_author_block + content[author_match.end(1):]
    return updated_content, True


def process_single_file(readme_path: Path):
    """处理指定的单个 README 文件"""
    if not readme_path.is_file():
        print(f"Error: File not found: {readme_path}")
        return

    content = readme_path.read_text(encoding='utf-8', errors='ignore')
    updated_content, is_modified = update_role_in_content(content)

    if is_modified and updated_content != content:
        readme_path.write_text(updated_content, encoding='utf-8')
        print(f"Fixed/Updated: {readme_path.relative_to(WORKSPACE_ROOT)}")
    else:
        print(f"Skipped (No change needed): {readme_path.relative_to(WORKSPACE_ROOT)}")


def process_all_authors():
    """批量扫描并更新 Models 目录下所有作者 README"""
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
                    updated_content, is_modified = update_role_in_content(content)
                    if is_modified and updated_content != content:
                        readme_path.write_text(updated_content, encoding='utf-8')
                        print(f"Fixed/Updated: {readme_path.relative_to(WORKSPACE_ROOT)}")
                        updated_count += 1
                    break

    print(f"\nBatch process completed. Total updated: {updated_count}")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        folder_id = sys.argv[1].zfill(4)
        target_readme = MODELS_DIR / folder_id / 'README.md'
        print(f"Running for single author folder: {folder_id}")
        process_single_file(target_readme)
    else:
        print("No author ID specified. Running batch process for all authors...")
        process_all_authors()