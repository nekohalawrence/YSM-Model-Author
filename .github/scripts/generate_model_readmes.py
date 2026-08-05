#!/usr/bin/env python3
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
MAIN_README_PATH = WORKSPACE_ROOT / 'README.md'

ROOT_DIRS = [
    WORKSPACE_ROOT / 'models',
    WORKSPACE_ROOT / 'other-models',
    WORKSPACE_ROOT / 'other-ysm-models',
]
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
PREVIEW_MARKER = re.compile(r'preview', re.I)
START_MARKER = '<!-- GENERATED MODEL PREVIEW README START -->'
END_MARKER = '<!-- GENERATED MODEL PREVIEW README END -->'


def parse_categories_from_main_readme() -> dict[str, list[str]]:
    """从主 README.md 的模型分类区块解析作品缩写与对应的标签列表"""
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
        
        raw_items = line[2:].split(',')
        tags = [f"#{item.strip()}" for item in raw_items if item.strip()]
        
        if not tags:
            continue
        
        first_key = raw_items[0].strip().lower()
        category_map[first_key] = tags
        
        for item in raw_items:
            category_map[item.strip().lower()] = tags

    return category_map


def get_tags_for_model(model_folder_name: str, category_map: dict[str, list[str]]) -> str:
    """根据模型文件夹名称前缀匹配标签，未匹配到则默认为 #Unknown"""
    prefix = model_folder_name.split('_')[0].strip().lower()
    
    if prefix in category_map:
        return ' '.join(category_map[prefix])
    
    return "#Unknown"


def is_preview_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS and PREVIEW_MARKER.search(path.stem)


def collect_preview_images(model_dir: Path) -> list[Path]:
    images = []
    for candidate in [model_dir, model_dir / 'previews']:
        if candidate.is_dir():
            for file_path in sorted(candidate.iterdir()):
                if is_preview_image(file_path):
                    images.append(file_path)
    return images


def build_meta_and_preview_content(model_dir: Path, image_paths: list[Path], category_map: dict[str, list[str]]) -> str:
    """构建包含元信息与预览图的内容（预览图默认展开）"""
    title = model_dir.name
    tags = get_tags_for_model(title, category_map)

    lines = [f'# {title}', '']

    # 元信息折叠块（默认收起）
    lines.extend([
        '<details>',
        '<summary>模型信息</summary>',
        '',
        f'- 来源：{tags}',
        '',
        '</details>',
        ''
    ])

    # 预览图折叠块（默认展开）
    lines.extend([
        '<details open>',
        '<summary>预览图</summary>',
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
    if root_dir.name == 'models':
        for author_dir in sorted(root_dir.iterdir()):
            if not is_author_dir(author_dir):
                continue
            for model_dir in sorted(author_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                if model_dir.name.startswith('.') or model_dir.name == 'previews':
                    continue
                yield model_dir
    else:
        for model_dir in sorted(root_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            if model_dir.name.startswith('.') or model_dir.name == 'previews':
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