#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为所有模型目录生成标准化的英文模型 README（不要求存在预览图）。

数据（外置，可手工维护，位于 .github/data/meta/）：
  models_meta.json  模型 -> co-creator 作者列表
      （由 organize_models.py 归档时写入；键为 "<作者编号>/<模型文件夹名>"）
  platform_map.json 平台键 -> README 字段映射

模型 README 结构：
  Model Details / Author Details / Co-creator Details / Preview Images
  Co-creator 段仅在 models_meta 中存在记录时输出；字段模板：
    - **Name**:
      - **Role**:
      - **SocialPlatform**:
      - **SupportPlatform**:
      - **OtherPlatform**:
      - **GroupChat**:
"""
import json
import re
from pathlib import Path
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import paths as lib_paths
from lib import readme as lib_readme
from lib import models as lib_models
from lib import previews as lib_previews

WORKSPACE_ROOT = lib_paths.WORKSPACE_ROOT
MAIN_README_PATH = WORKSPACE_ROOT / 'README.md'

ROOT_DIRS = [
    WORKSPACE_ROOT / 'Models',
    WORKSPACE_ROOT / 'Blockbench-Models',
    WORKSPACE_ROOT / 'Other-YSM-Models',
]
IMAGE_EXTS = lib_previews.IMAGE_EXTS
PREVIEW_MARKER = lib_previews.PREVIEW_MARKER
START_MARKER = '<!-- GENERATED MODEL PREVIEW README START -->'
END_MARKER = '<!-- GENERATED MODEL PREVIEW README END -->'

# co-creator 模板字段（有值才输出，Name 必有）
CO_CREATOR_FIELDS = ['SocialPlatform', 'SupportPlatform', 'OtherPlatform', 'GroupChat']


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
    """获取作者 ID 与名称（避开 Co-creator）。优先用集中数据 authors.json，缺失时回退读 README。"""
    author_dir = model_dir.parent
    if not author_dir.is_dir() or not author_dir.name.isdigit() or len(author_dir.name) != 4:
        return '', ''

    author_id = author_dir.name
    authors = lib_readme.load_authors_index().get('authors') or {}
    entry = authors.get(author_id)
    if entry:
        names = entry.get('name') or []
        if isinstance(names, str):
            # 兼容旧结构（name 为字符串）
            names = lib_readme.split_author_names(names)
        if names:
            return author_id, names[0]

    author_name = author_id
    for candidate in ['README.md', 'readme.md', 'Readme.md']:
        candidate_path = author_dir / candidate
        if candidate_path.is_file():
            text = candidate_path.read_text(encoding='utf-8', errors='ignore')
            name = lib_readme.parse_author_name_value(text)
            if name:
                author_name = name
            break

    return author_id, author_name


def collect_preview_images(model_dir: Path) -> list[Path]:
    """收集模型目录下的预览图（复用 lib/previews.py 统一规则）"""
    return lib_previews.collect_preview_images(model_dir)


# ---------------------------------------------------------------------------
# co-creator 数据（来自 models_meta.json）
# ---------------------------------------------------------------------------
def load_models_meta() -> dict:
    """读取 co-creator 元数据（.github/data/meta/models_meta.json）"""
    return lib_paths.load_json(lib_paths.data_path('meta', 'models_meta.json'), {})


def same_model(a: str, b: str) -> bool:
    """判断两个名称是否属于同一模型（复用 lib/models.py 统一容错匹配）"""
    return lib_models.same_model(a, b)


def get_co_creators(author_id: str, model_dir_name: str) -> list[dict]:
    """按 "<作者编号>/<文件夹名>" 精确匹配 models_meta；文件夹被 rename_model_folders 改名时
    用 same_model 容错匹配（Unknown_ 前缀、规范化命名等变形）。"""
    meta = load_models_meta()
    exact = meta.get(f'{author_id}/{model_dir_name}')
    if exact is not None:
        return exact.get('co_creators', [])
    for key, entry in meta.items():
        kid, _, kfolder = key.partition('/')
        if kid == author_id and same_model(kfolder, model_dir_name):
            return entry.get('co_creators', [])
    return []


def build_co_creator_section(co_creators: list[dict]) -> str:
    """Co-creator Details 段；字段按模板顺序，有值才输出。"""
    if not co_creators:
        return ''
    lines = ['<details>', '<summary>Co-creator Details</summary>', '']
    for c in co_creators:
        lines.append(f"- **Name**: {c.get('name', '')}")
        if c.get('role'):
            lines.append(f"  - **Role**: {c['role']}")
        platforms = c.get('platforms') or {}
        for field in CO_CREATOR_FIELDS:
            values = platforms.get(field) or []
            if values:
                lines.append(f"  - **{field}**: " + ' | '.join(values))
        lines.append('')
    lines.append('</details>')
    lines.append('')
    return '\n'.join(lines)


def build_meta_and_preview_content(model_dir: Path, image_paths: list[Path],
                                   category_map: dict[str, list[str]],
                                   co_creators: list[dict]) -> str:
    """构建标准化的英文模型 README 内容（含可选 Co-creator 段）"""
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

    # Co-creator Details（主要分类作者之外的创作者，数据来自 models_meta.json）
    co_section = build_co_creator_section(co_creators)
    if co_section:
        lines.extend([co_section.rstrip(), ''])

    # Preview Images（预览图，有图才输出，默认展开）
    if image_paths:
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
            # 全部模型目录都生成 README（不要求存在预览图）
            preview_images = collect_preview_images(model_dir)
            co_creators = get_co_creators(model_dir.parent.name, model_dir.name)

            readme_path = model_dir / 'README.md'
            existing_content = readme_path.read_text(encoding='utf-8', errors='ignore') if readme_path.exists() else None

            new_content = build_meta_and_preview_content(model_dir, preview_images,
                                                         category_map, co_creators)

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
