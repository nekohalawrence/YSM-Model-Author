import sys
import re
from pathlib import Path

# 允许处理的文件后缀白名单
ALLOWED_EXTS = {'.ysm', '.zip', '.7z', '.rar', '.tar', '.gz', '.bbmodel'}

def extract_version_and_clean_stem(file_stem: str) -> tuple[str, str]:
    """提取版本号，并返回去除版本号后的干净 stem"""
    match = re.search(r'(?:_|[vV])?(\d+(?:\.\d+)+)$', file_stem)
    if match:
        version = f"_v{match.group(1)}"
        clean_stem = file_stem[:match.start()].rstrip('_')
        return version, clean_stem
    return "", file_stem

def extract_variant(clean_stem: str, folder_name: str) -> str:
    """智能提取变体名称（如：发光版、无帽子版、泳装等）"""
    # 1. 若文件名本身就包含了完整的文件夹名前缀，直接截取后面的变体部分
    if clean_stem.lower().startswith(folder_name.lower()):
        variant = clean_stem[len(folder_name):].strip('-_ ')
        return f"_{variant}" if variant else ""

    # 2. 若文件名与文件夹名不完全一致，比对词组提取不在文件夹名中的变体词
    folder_words = set(re.split(r'[-_\s]+', folder_name.lower()))
    file_words = [w for w in re.split(r'[-_\s]+', clean_stem) if w]
    
    variant_words = [word for word in file_words if word.lower() not in folder_words]
    
    if variant_words:
        return f"_{'_'.join(variant_words)}"
        
    return ""

def rename_to_folder_name(target_path: Path, apply_changes: bool = False):
    """重命名逻辑：文件夹名 + [变体名] + [版本号] + 后缀"""
    if target_path.is_file():
        files = [target_path]
    elif target_path.is_dir():
        files = [p for p in target_path.rglob('*') if p.is_file()]
    else:
        print(f"错误: 路径不存在 -> {target_path}")
        return

    renamed_count = 0
    skipped_count = 0

    print(f"{'='*20} {'执行模式: 真实重命名 (--apply)' if apply_changes else '执行模式: 预览模式 (Dry-Run)'} {'='*20}\n")

    for file_path in sorted(files):
        if file_path.suffix.lower() not in ALLOWED_EXTS:
            continue

        folder_name = file_path.parent.name
        original_name = file_path.name
        ext = file_path.suffix

        # 1. 提取版本号与干净 stem
        version_tag, clean_stem = extract_version_and_clean_stem(file_path.stem)

        # 2. 提取变体名称
        variant_tag = extract_variant(clean_stem, folder_name)

        # 3. 拼接新文件名：文件夹名 + 变体名 + 版本号 + 后缀
        new_stem = f"{folder_name}{variant_tag}{version_tag}"
        new_name = f"{new_stem}{ext}"

        if original_name == new_name:
            skipped_count += 1
            continue

        new_file_path = file_path.parent / new_name

        # 同名冲突防护
        if apply_changes and new_file_path.exists():
            counter = 1
            while new_file_path.exists():
                new_file_path = file_path.parent / f"{folder_name}{variant_tag}_{counter}{version_tag}{ext}"
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
        print("\n提示: 当前处于预览模式，没有修改任何磁盘文件。如需真正修改，请在命令末尾加上 --apply 参数！")


if __name__ == '__main__':
    default_dir = Path(__file__).resolve().parent / 'Models'
    
    apply_flag = '--apply' in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != '--apply']

    target = Path(args[0]) if args else default_dir
    rename_to_folder_name(target, apply_changes=apply_flag)