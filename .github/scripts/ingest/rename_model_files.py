import sys
import re
from pathlib import Path
import sys
from pathlib import Path
# 脚本按流程阶段分类到 scripts/<类别>/ 子目录：把 .github/scripts 加回 sys.path，
# 保证 lib/ 与跨分类脚本可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from lib import models as lib_models

# 允许处理的文件后缀
ALLOWED_EXTS = {'.ysm', '.zip', '.7z', '.rar', '.tar', '.gz', '.bbmodel'}

def parse_file_stem(file_stem: str, folder_name: str) -> tuple[str, str, str]:
    """
    智能解析文件名，分离为：变体名、版本号、副本序号
    例如: "兔子洞Ver1.1" -> ("" , "_v1.1", "")
    """
    stem = file_stem

    # 1. 提取末尾的副本序号 (如 (1)、（1）、_1、-1)
    copy_tag = ""
    copy_match = re.search(r'[\s_-]*[\(（](\d+)[\)）]$|[\s_-]+(\d+)$', stem)
    if copy_match:
        num = copy_match.group(1) or copy_match.group(2)
        copy_tag = f"_{num}"
        stem = stem[:copy_match.start()].strip('-_ ')

    # 2. 提取版本号（支持 Ver / ver / Version / v / V 等版本修饰前缀）
    version_tag = ""
    version_match = re.search(
        r'(?:[_\s-]|(?<=[^\w]))*(?:ver(?:sion)?|v|r)?[\s._-]*(\d+(?:\.\d+)+)',
        stem,
        re.IGNORECASE
    )
    if version_match:
        version_num = version_match.group(1)
        version_tag = f"_v{version_num}"
        # 剔除整个匹配内容（包含 Ver/Version/v 等前缀）
        stem = (stem[:version_match.start()] + stem[version_match.end():]).strip('-_ ')

    # 3. 提取变体名称 (对比 folder_name，过滤已有的关键词)
    clean_stem = re.sub(r'[-—\s+]+', '_', stem)
    
    # 提取文件夹中的关键词库（忽略评级与常用版本词）
    folder_keywords = set(w.lower() for w in re.split(r'[-_\s]+', folder_name) if w)
    folder_keywords.update({'la', 'lb', 'lc', 'ld', 'ver', 'version'})

    file_words = [w for w in re.split(r'[-_\s]+', clean_stem) if w]
    variant_words = [w for w in file_words if w.lower() not in folder_keywords]

    variant_tag = f"_{'_'.join(variant_words)}" if variant_words else ""

    return variant_tag, version_tag, copy_tag


def clean_folder_name(folder_name: str) -> str:
    """去除文件夹名称末尾的评级标签（复用 lib/models.py 统一实现）"""
    return lib_models.clean_folder_name(folder_name)


def rename_to_folder_name(target_path: Path, apply_changes: bool = False):
    """重命名主函数"""
    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        files = [p for p in target_path.rglob('*') if p.is_file()]
    else:
        print(f"错误: 路径不存在 -> {target_path}")
        return

    renamed_count = 0
    skipped_count = 0

    print(f"{'='*20} {'执行模式: 真实修改 (--apply)' if apply_changes else '执行模式: 预览模式 (Dry-Run)'} {'='*20}\n")

    for file_path in sorted(files):
        if file_path.suffix.lower() not in ALLOWED_EXTS:
            continue

        folder_name = file_path.parent.name
        base_folder_name = clean_folder_name(folder_name)
        original_name = file_path.name
        ext = file_path.suffix

        # 解析文件名结构
        variant_tag, version_tag, copy_tag = parse_file_stem(file_path.stem, folder_name)

        # 拼接最终文件名并清理多余下划线
        new_stem = f"{base_folder_name}{variant_tag}{version_tag}{copy_tag}"
        new_stem = re.sub(r'_+', '_', new_stem).strip('_')
        new_name = f"{new_stem}{ext}"

        if original_name == new_name:
            skipped_count += 1
            continue

        new_file_path = file_path.parent / new_name

        # 同名冲突处理
        if apply_changes and new_file_path.exists():
            counter = 1
            while new_file_path.exists():
                new_file_path = file_path.parent / f"{new_stem}_{counter}{ext}"
                counter += 1
            new_name = new_file_path.name

        print(f"[匹配] 目录: {folder_name}/")
        print(f"  原名: {original_name}")
        print(f"  新名: {new_name}\n")

        if apply_changes:
            file_path.rename(new_file_path)

        renamed_count += 1

    print(f"{'='*50}")
    print(f"统计完成: 待修改/已修改 = {renamed_count}, 无需修改 = {skipped_count}")
    if not apply_changes and renamed_count > 0:
        print("\n提示: 当前为预览模式，磁盘文件未修改。如确认无误，请在命令末尾加上 --apply 执行！")


if __name__ == '__main__':
    default_dir = Path(__file__).resolve().parent / 'Models'
    
    apply_flag = '--apply' in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != '--apply']

    target = Path(args[0]) if args else default_dir
    rename_to_folder_name(target, apply_changes=apply_flag)
