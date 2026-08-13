#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为所有模型目录生成标准化的英文模型 README（不要求存在预览图）。

数据（外置，可手工维护，位于 .github/data/）：
  meta/authors.json         作者集中数据（name 数组 / role / platforms），author_index.py --data 生成
  meta/platform_map.json    平台分类映射 {分类: [平台键...]}（分类为键、平台键列表为值）
  meta/models_meta.json     模型 -> co-creator 作者列表（按需生成，无记录时文件不存在）
  knowledge/category_map.json  作品缩写 -> 大类（Game/Anime/Music/Original/Other）
  templates/model_readme.template.json  模型 README 结构模板（由 _Template/ 转化）

模型 README 结构（按模板渲染）：
  # <模型名>
  ## Model Details（<details> 内）
    - **Category**: 大类标签（category_map）
    - **Game**: 作品标签（主 README 分类区块）
    ## Author Details
      Name / Role / 平台分类段（authors.json + platform_map 分类）
    ## Co-creator Details
      同 Author 结构；数据来自 models_meta.json，无记录时解析 .ysm 兜底
  ## Preview Images（独立 <details open>）
"""
import argparse
import re
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import paths as lib_paths
from lib import readme as lib_readme
from lib import models as lib_models
from lib import previews as lib_previews
from lib import terms as lib_terms
from lib import ysm as lib_ysm

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

# 模板与数据（惰性加载 + 模块级缓存，全量扫描只读一次）
_TEMPLATE: dict = {}
_CATEGORY_MAP: dict[str, str] = {}
_PLATFORM_MAP: dict | None = None
_MODELS_META: dict | None = None


def load_template() -> dict:
    """读取模型 README 模板（.github/data/templates/model_readme.template.json）并缓存。"""
    if not _TEMPLATE:
        data = lib_paths.load_json(
            lib_paths.data_path('templates', 'model_readme.template.json'), {})
        _TEMPLATE.update(data)
    return _TEMPLATE


def load_category_map() -> dict[str, str]:
    """读取作品大类映射（knowledge/category_map.json），展平为 作品缩写(小写) -> 大类。"""
    if not _CATEGORY_MAP:
        data = lib_paths.load_json(
            lib_paths.data_path('knowledge', 'category_map.json'), {})
        for category, works in data.items():
            for w in works:
                _CATEGORY_MAP[str(w).lower()] = str(category)
    return _CATEGORY_MAP


def get_platform_map() -> dict:
    """读取平台分类映射（lib/ysm 实现，反查用）并缓存。"""
    global _PLATFORM_MAP
    if _PLATFORM_MAP is None:
        _PLATFORM_MAP = lib_ysm.load_platform_map()
    return _PLATFORM_MAP


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
    """根据模型文件夹名称前缀匹配作品标签，未匹配到则默认为 #Unknown"""
    prefix = model_folder_name.split('_')[0].strip().lower()

    if prefix in category_map:
        return ' '.join(category_map[prefix])

    return "#Unknown"


def get_category_tag(model_folder_name: str, work_category_map: dict[str, str]) -> str:
    """按模型文件夹前缀查作品大类（category_map.json）；未命中返回 #Unknown。"""
    prefix = model_folder_name.split('_')[0].strip().lower()
    return f"#{work_category_map.get(prefix, 'Unknown')}"


def get_author_info(model_dir: Path) -> tuple[str, dict]:
    """返回 (author_id, 作者信息 {name, role, platforms})。

    优先集中数据 authors.json（author_index.py --data 生成，含 role）；缺失时回退解析作者
    README。无编号目录（Blockbench/Other-YSM 根）返回空信息。
    """
    author_dir = model_dir.parent
    if not author_dir.is_dir() or not author_dir.name.isdigit() or len(author_dir.name) != 4:
        return '', {'name': [], 'role': '', 'platforms': {}}

    author_id = author_dir.name
    authors = lib_readme.load_authors_index().get('authors') or {}
    entry = authors.get(author_id)
    if entry:
        return author_id, entry

    # 回退：作者 README 未收录时现场解析
    for candidate in ['README.md', 'readme.md', 'Readme.md']:
        candidate_path = author_dir / candidate
        if candidate_path.is_file():
            content = candidate_path.read_text(encoding='utf-8', errors='ignore')
            return author_id, {
                'name': lib_readme.split_author_names(lib_readme.parse_author_name_value(content)),
                'role': lib_readme.extract_author_role(content),
                'platforms': lib_readme.extract_platforms(content),
            }
    return author_id, {'name': [], 'role': '', 'platforms': {}}


def collect_preview_images(model_dir: Path) -> list[Path]:
    """收集模型目录下的预览图（复用 lib/previews.py 统一规则）"""
    return lib_previews.collect_preview_images(model_dir)


# ---------------------------------------------------------------------------
# co-creator 数据（models_meta.json 优先，.ysm 解析兜底）
# ---------------------------------------------------------------------------
def load_models_meta() -> dict:
    """读取 co-creator 元数据（.github/data/meta/models_meta.json），惰性缓存——
    全量扫描 1400+ 模型时避免每次调用都重复读文件。"""
    global _MODELS_META
    if _MODELS_META is None:
        _MODELS_META = lib_paths.load_json(lib_paths.data_path('meta', 'models_meta.json'), {})
    return _MODELS_META


def same_model(a: str, b: str) -> bool:
    """判断两个名称是否属于同一模型（复用 lib/models.py 统一容错匹配）"""
    return lib_models.same_model(a, b)


def get_co_creators(model_dir: Path) -> list[dict]:
    """按 "<作者编号>/<文件夹名>" 精确匹配 models_meta；文件夹被 rename_model_folders 改名时
    用 same_model 容错匹配（Unknown_ 前缀、规范化命名等变形）。

    models_meta 无记录（旧归档/手动放置的模型）时回退解析模型目录下 .ysm 的作者块，
    识别 co-creator —— .ysm 是作者信息的源头，覆盖 models_meta 未收录的情况。
    """
    author_id = model_dir.parent.name
    meta = load_models_meta()
    exact = meta.get(f'{author_id}/{model_dir.name}')
    if exact is not None:
        return exact.get('co_creators', [])
    for key, entry in meta.items():
        kid, _, kfolder = key.partition('/')
        if kid == author_id and same_model(kfolder, model_dir.name):
            return entry.get('co_creators', [])
    return co_creators_from_ysm(model_dir)


def co_creators_from_ysm(model_dir: Path) -> list[dict]:
    """解析模型目录下全部 .ysm，把非主作者块合并成 co-creator 记录（models_meta 兜底）。

    主作者 = role 含"模型"的第一个块（与归档分类 classify_authors 一致）；其余块即
    co-creator。多 .ysm 目录（同一模型的多个版本/变体）会**扫描全部文件并去重合并**，
    避免只取第一个文件而漏掉其他版本的合作作者。返回格式与 models_meta 的
    co_creators 相同：[{'name', 'role', 'platforms': {字段: [值]}}]。
    """
    ysm_files = sorted(model_dir.glob('*.ysm')) + sorted(model_dir.glob('*.YSM'))
    platform_map = get_platform_map()
    merged: list[dict] = []
    seen: set[str] = set()
    for f in ysm_files:
        meta = lib_ysm.extract_metadata(f, quiet=True)
        blocks = meta.get('author_blocks') or []
        if len(blocks) < 2:
            # 单作者 .ysm 没有 co-creator，继续看下一个文件
            continue
        _, _, co_blocks = lib_ysm.classify_authors(blocks)
        for b in co_blocks:
            name = b['name']
            if name in seen:
                continue
            seen.add(name)
            merged.append({'name': name, 'role': b.get('role', ''),
                           'platforms': lib_ysm.map_platforms(b.get('contacts') or {}, platform_map)})
    return merged


# ---------------------------------------------------------------------------
# 渲染（按 templates/model_readme.template.json 的 author_block 格式）
# ---------------------------------------------------------------------------
def normalize_platforms(platforms: dict,
                        platform_map: dict) -> dict[str, list[tuple[str, str]]]:
    """把平台数据统一为 {分类: [(平台键, 值)]}，供 render_platform_block 渲染。

    兼容两种输入结构：
      - 扁平 {平台键: 值}（authors.json 的 platforms）→ 反查 platform_map 分类
      - 已分类 {分类: [值行]}（models_meta / ysm 解析的 co-creator platforms）
    """
    out: dict[str, list[tuple[str, str]]] = {}
    if not platforms:
        return out
    sample = next(iter(platforms.values()))
    if isinstance(sample, list):
        # 已分类：值行为 'Bilibili: https://...' 形式
        for field, lines in platforms.items():
            for line in lines:
                key, _, value = str(line).partition(':')
                out.setdefault(field, []).append((key.strip(), value.strip()))
    else:
        # 扁平：反查 platform_map（{分类: [平台键...]}）得到所属分类
        reverse: dict[str, str] = {}
        for field, aliases in platform_map.items():
            for alias in aliases:
                reverse.setdefault(alias, field)
        for key, value in platforms.items():
            field = reverse.get(str(key).strip().lower(), 'OtherPlatform')
            out.setdefault(field, []).append((str(key).strip(), str(value)))
    return out


def render_platform_block(platforms: dict, tpl: dict, label: str) -> list[str]:
    """渲染平台字段块：分类行（`**SocialPlatform**: #Bilibili #YouTube`）+ 平台子行。

    label 为平台链接的显示文本（作者规范名）；非 URL 值（QQ 号等）走纯文本子行。
    """
    items = normalize_platforms(platforms, get_platform_map())
    lines: list[str] = []
    for field in tpl.get('platform_order', []):
        pairs = items.get(field) or []
        if not pairs:
            continue
        tags = ' #'.join(key for key, _ in pairs)
        lines.append(tpl['platform_header'].format(field=field, tags=tags))
        for key, value in pairs:
            if value.startswith('http'):
                lines.append(tpl['platform_item'].format(platform=key, label=label, url=value))
            else:
                lines.append(tpl['platform_plain_item'].format(platform=key, value=value))
    return lines


def render_person_block(entry: dict, author_id: str = '') -> list[str]:
    """渲染作者/co-creator 信息块：Name + Role + 平台分类段。

    entry: {'name': 数组或字符串, 'role': str, 'platforms': {...}}（两种平台结构均可）。
    """
    tpl = load_template().get('author_block', {})
    names = entry.get('name') or []
    if isinstance(names, str):
        names = lib_readme.split_author_names(names)
    names = [str(n) for n in names if str(n)]
    name_str = ' | '.join(names) if names else '暂无'
    label = str(names[0]).lstrip('#＃') if names else name_str

    lines = [tpl.get('name_line', '- **Name**: {names}').format(names=name_str)]
    role = entry.get('role') or ''
    if role:
        # Role 值经术语表归一化：把 .ysm 的不同表达（Model author/动画/動作）
        # 统一为标准中英术语；已是标签格式（含 #/|）的原样保留。
        role = lib_terms.normalize_role(role)
        lines.append(tpl.get('role_line', '  - **Role**: {role}').format(role=role))
    lines.extend(render_platform_block(entry.get('platforms') or {}, tpl, label))
    if author_id:
        lines.append(tpl.get('id_line', '- **Author ID**: `{author_id}`').format(author_id=author_id))
    return lines


def build_co_creator_section(co_creators: list[dict]) -> str:
    """Co-creator Details 内容（多个人块，空行分隔）；无记录返回空串。"""
    if not co_creators:
        return ''
    lines: list[str] = []
    for c in co_creators:
        lines.extend(render_person_block(c))
        lines.append('')
    return '\n'.join(lines).rstrip()


def build_meta_and_preview_content(model_dir: Path, image_paths: list[Path],
                                   category_tag: str, game_tags: str,
                                   co_creators: list[dict],
                                   author_entry: dict, author_id: str) -> str:
    """按模板渲染模型 README：Model Details（含 Author/Co-creator 二级标题）+ Preview。"""
    tpl = load_template()
    title = model_dir.name
    lines = [tpl.get('title', '# {model_name}').format(model_name=title), '']

    for section in tpl.get('sections', []):
        key = section.get('key')
        if key == 'model_details':
            # 大 details 块：Model Details 字段（按模板 indent 缩进）+ 内部两个二级标题 section
            lines += [section['heading'], '<details>',
                      f"<summary>{section['summary']}</summary>", '']
            for field in section.get('fields', []):
                indent = '  ' * field.get('indent', 0)
                if field.get('key') == 'category':
                    lines.append(f"{indent}- {field['label']}: {category_tag}")
                elif field.get('key') == 'game':
                    lines.append(f"{indent}- {field['label']}: {game_tags}")
            lines.append('')
        elif key == 'author_details':
            lines += [section['heading'], '']
            lines += render_person_block(author_entry, author_id=author_id)
            lines.append('')
        elif key == 'co_creator_details':
            # 无 co-creator 时连标题也不输出（避免空 section 占位）
            co_section = build_co_creator_section(co_creators)
            if co_section:
                lines += [section['heading'], '', co_section, '']
        elif key == 'preview_images':
            # 关闭 Model Details 的大 details，再开 Preview 的独立 details
            lines += ['</details>', '', section['heading'],
                      '<details open>', f"<summary>{section['summary']}</summary>", '',
                      START_MARKER, '']
            for image_path in image_paths:
                rel_path = image_path.relative_to(model_dir).as_posix()
                lines.append(f'![{image_path.name}]({rel_path})')
                lines.append('')
            lines += [END_MARKER, '', '</details>', '']

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
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', metavar='PATH', default=None,
                        help='只处理指定模型目录（相对仓库根，如 Models/0056/xxx）；缺省全量')
    args = parser.parse_args()

    updated = 0
    created = 0

    category_map = parse_categories_from_main_readme()
    work_category_map = load_category_map()

    if args.only:
        target = WORKSPACE_ROOT / args.only
        model_dirs = [target] if target.is_dir() else []
        if not model_dirs:
            print(f"[错误] 目录不存在: {target}", file=sys.stderr)
            return 2
    else:
        model_dirs = [md for root_dir in ROOT_DIRS if root_dir.is_dir()
                      for md in iter_model_dirs(root_dir)]

    for model_dir in model_dirs:
        # 全部模型目录都生成 README（不要求存在预览图）
        preview_images = collect_preview_images(model_dir)
        co_creators = get_co_creators(model_dir)
        author_id, author_entry = get_author_info(model_dir)
        if not author_entry.get('name') and not author_entry.get('role'):
            author_entry = {'name': [], 'role': '', 'platforms': {}}
        category_tag = get_category_tag(model_dir.name, work_category_map)
        game_tags = get_tags_for_model(model_dir.name, category_map)

        readme_path = model_dir / 'README.md'
        existing_content = readme_path.read_text(
            encoding='utf-8', errors='ignore') if readme_path.exists() else None

        new_content = build_meta_and_preview_content(
            model_dir, preview_images, category_tag, game_tags,
            co_creators, author_entry, author_id)

        if readme_path.exists():
            if existing_content == new_content:
                continue
            action = 'Updated'
            updated += 1
        else:
            action = 'Created'
            created += 1

        readme_path.write_text(new_content, encoding='utf-8')
        print(f"{action} {readme_path.relative_to(WORKSPACE_ROOT)}")

    print(f"Summary: created={created}, updated={updated}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
