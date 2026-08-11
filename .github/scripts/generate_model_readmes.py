#!/usr/bin/env python3
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
MAIN_README_PATH = WORKSPACE_ROOT / 'README.md'

ROOT_DIRS = [
    WORKSPACE_ROOT / 'Models',
    WORKSPACE_ROOT / 'Blockbench-Models',
    WORKSPACE_ROOT / 'Other-YSM-Models',
]
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
PREVIEW_MARKER = re.compile(r'preview', re.I)
START_MARKER = '<!-- GENERATED MODEL PREVIEW README START -->'
END_MARKER = '<!-- GENERATED MODEL PREVIEW README END -->'


def parse_categories_from_main_readme() -> dict[str, list[str]]:
    """从主 README.md 的模型分类区块解析作品缩写与对应的标签列表（支持 | 和 , 混合分隔）"""
    category_map: dict[str, list[str]] = {}
    if not MAIN_README_PATH.exists():
        return category_map

    content = MAIN_README_PATH.read_text(encoding='utf-8', errors='ignore')
    
    match = re.search(r'<summary>\s*模型分类\s*</summary>(.*?)</details>', content, re.DOTALL)
    if not match:
        return category_map

    category_block = match.group(1)
    
    for line in category_block.splitlines():
        line = line.strip()
        if not line.startswith('- '):
            continue
        
        raw_text = line[2:].replace('|', ',')
        raw_items = [item.strip() for item in raw_text.split(',') if item.strip()]
        
        if not raw_items:
            continue
        
        tags = [f"#{item}" for item in raw_items]
        
        for item in raw_items:
            category_map[item.lower()] = tags

    return category_map


def get_tags_for_model(model_folder_name: str, category_map: dict[str, list[str]]) -> str:
    """根据模型文件夹名称前缀匹配标签，未匹配到则默认为 #Unknown"""
    prefix = model_folder_name.split('_')[0].strip().lower()
    
    if prefix in category_map:
        return ' '.join(category_map[prefix])
    
    return "#Unknown"


def get_author_info(model_dir: Path) -> tuple[str, str]:
    """从作者目录 README 中提取作者名称与 ID（避开 Co-creator）"""
    author_dir = model_dir.parent
    if not author_dir.is_dir() or not author_dir.name.isdigit() or len(author_dir.name) != 4:
        return '', ''

    author_name = author_dir.name
    for candidate in ['README.md', 'readme.md', 'Readme.md']:
        candidate_path = author_dir / candidate
        if candidate_path.is_file():
            text = candidate_path.read_text(encoding='utf-8', errors='ignore')
            
            author_section_match = re.search(r'##\s*Author\b(.*?)(?=\n##|\Z)', text, re.DOTALL | re.IGNORECASE)
            target_text = author_section_match.group(1) if author_section_match else text

            match = re.search(r'-\s*\*\*Name\*\*\s*[:：]\s*(.+?)(?:\n|$)', target_text, re.IGNORECASE)
            if not match:
                match = re.search(r'-\s*作者名称\s*[:：]\s*(.+?)(?:\n|$)', target_text, re.IGNORECASE)
            if match:
                author_name = match.group(1).strip()
            break

    return author_dir.name, author_name


def collect_preview_images(model_dir: Path) -> list[Path]:
    """收集模型目录下的预览图（支持 previews 文件夹与根目录图片）"""
    images = []

    # 1. 扫描模型根目录下的符合 preview 命名的图片
    for file_path in sorted(model_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTS:
            if PREVIEW_MARKER.search(file_path.stem):
                images.append(file_path)

    # 2. 扫描 previews 文件夹（不区分大小写，如 previews, Previews）
    # 位于 previews 文件夹内的图片无需文件名包含 preview
    for sub_dir in model_dir.iterdir():
        if sub_dir.is_dir() and sub_dir.name.lower() == 'previews':
            for file_path in sorted(sub_dir.iterdir()):
                if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTS:
                    if file_path not in images:
                        images.append(file_path)

    return images


def build_meta_and_preview_content(model_dir: Path, image_paths: list[Path], category_map: dict[str, list[str]]) -> str:
    """构建标准化的英文模型 README 内容"""
    title = model_dir.name
    tags = get_tags_for_model(title, category_map)
    author_id, author_name = get_author_info(model_dir)

    lines = [f'# {title}', '']

    # Model Details（模型详情）
    lines.extend([
        '<details>',
        '<summary>Model Details</summary>',
        '',
        f'- **Franchise / Category**: {tags}',
        '',
        '</details>',
        ''
    ])

    # Author Details（作者信息与跳转链接）
    if author_id:
        lines.extend([
            '<details>',
            '<summary>Author Details</summary>',
            '',
            f'- **Author**: [#{author_id} - {author_name}](../)',
            f'- **Author ID**: `{author_id}`',
            '',
            '</details>',
            ''
        ])

    # Preview Images（预览图，默认展开）
    lines.extend([
        '<details open>',
        '<summary>Preview Images</summary>',
        '',
        START_MARKER,
        ''
    ])

    for image_path in image_paths:
        rel_path = image_path.relative_to(model_dir).as_posix()
        lines.append(f'![{image_path.name}]({rel_path})')
        lines.append('')

    lines.extend([
        END_MARKER,
        '',
        '</details>',
        ''
    ])

    return '\n'.join(lines).rstrip() + '\n'


def is_author_dir(path: Path) -> bool:
    return path.is_dir() and path.name.isdigit() and len(path.name) == 4


def iter_model_dirs(root_dir: Path):
    if root_dir.name == 'Models':
        for author_dir in sorted(root_dir.iterdir()):
            if not is_author_dir(author_dir):
                continue
            for model_dir in sorted(author_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                if model_dir.name.startswith('.') or model_dir.name.lower() == 'previews':
                    continue
                yield model_dir
    else:
        for model_dir in sorted(root_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            if model_dir.name.startswith('.') or model_dir.name.lower() == 'previews':
                continue
            yield model_dir


def main() -> int:
    updated = 0
    created = 0

    category_map = parse_categories_from_main_readme()

    for root_dir in ROOT_DIRS:
        if not root_dir.is_dir():
            continue

        for model_dir in iter_model_dirs(root_dir):
            preview_images = collect_preview_images(model_dir)
            if not preview_images:
                continue

            readme_path = model_dir / 'README.md'
            existing_content = readme_path.read_text(encoding='utf-8', errors='ignore') if readme_path.exists() else None

            new_content = build_meta_and_preview_content(model_dir, preview_images, category_map)

            if readme_path.exists():
                if existing_content == new_content:
                    continue
                action = 'Updated'
                updated += 1
            else:
                action = 'Created'
                created += 1

            readme_path.write_text(new_content, encoding='utf-8')
            print(f"{action} {readme_path.relative_to(root_dir.parent)}")

    print(f"Summary: created={created}, updated={updated}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())