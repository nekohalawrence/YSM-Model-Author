import os
import json
import re
import time
from pathlib import Path

# --- 依赖检查 ---
try:
    from jinja2 import Template
except ImportError:
    print("Error: 缺少 'jinja2' 库。请运行: pip install jinja2")
    exit(1)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    print("Warning: 缺少 'Pillow' 库，将跳过缩略图生成。建议运行: pip install Pillow")
    HAS_PILLOW = False

# 配置
# 切换工作目录到项目根目录 (假设脚本位于 .github/scripts/)
os.chdir(Path(__file__).resolve().parents[2])

ROOT_DIR = Path('models')
OUTPUT_FILE = Path('index.html')
TEMPLATE_FILE = Path('.github/template/template.html')
THUMBNAIL_SIZE = (400, 400)

def generate_thumbnail(src_path: Path):
    """生成 WebP 缩略图，返回缩略图的相对路径"""
    if not HAS_PILLOW: return src_path
    
    thumb_path = src_path.with_name(f"thumb_{src_path.stem}.webp")
    
    # 如果缩略图已存在且比原图新，直接返回
    if thumb_path.exists() and thumb_path.stat().st_mtime > src_path.stat().st_mtime:
        return thumb_path

    try:
        with Image.open(src_path) as img:
            # 转换为 RGB (防止 RGBA 保存为 JPEG 报错，虽然我们用 WebP 但保持习惯)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new(img.mode[:-1], img.size, (255, 255, 255))
                background.paste(img, img.split()[-1])
                img = background
            
            img.thumbnail(THUMBNAIL_SIZE)
            img.save(thumb_path, 'WEBP', quality=85)
            print(f"Generated thumbnail: {thumb_path}")
            return thumb_path
    except Exception as e:
        print(f"Failed to generate thumbnail for {src_path}: {e}")
        return src_path

def parse_readme(file_path, default_id):
    info = { "name": default_id, "socials": [] }
    if not file_path or not file_path.exists(): return info

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for line in lines:
                clean_line = line.strip()
                if 'name' not in info or info['name'] == default_id:
                    match = re.search(r'[\*\-]?\s*(?:作者名称|作者|Author)[:：]\s*(.*)', clean_line)
                    if match:
                        raw = match.group(1).strip().replace('*', '').replace('`', '').replace('#', '')
                        if raw: info['name'] = raw
                
                platforms = ['bilibili', 'youtube', 'afdian', 'patreon', 'ko-fi', 'twitter', 'pixiv', 'sketchfab']
                found = next((p for p in platforms if p.lower() in clean_line.lower()), None)
                if found:
                    parts = re.split(r'[:：]', clean_line, 1)
                    if len(parts) > 1:
                        content = parts[1].strip()
                        link_match = re.search(r'\[.*?\]\((https?://.*?)\)', content) or re.search(r'(https?://[^\s]+)', content)
                        if link_match:
                            url = link_match.group(1).rstrip(')')
                            info['socials'].append({ "platform": found, "url": url })
    except: pass
    return info

models_data = []
authors_set = {}

if not ROOT_DIR.exists():
    print(f"Error: Directory '{ROOT_DIR}' not found.")
    exit(1)

for author_dir in ROOT_DIR.iterdir():
    if not author_dir.is_dir(): continue
    author_id = author_dir.name
    
    # 1. 尝试读取 info.json (元数据增强)
    info_json_path = author_dir / 'info.json'
    readme_path = None
    
    if info_json_path.exists():
        try:
            with open(info_json_path, 'r', encoding='utf-8') as f:
                author_meta = json.load(f)
                # 确保有基本字段
                if 'name' not in author_meta: author_meta['name'] = author_id
                if 'socials' not in author_meta: author_meta['socials'] = []
        except:
            author_meta = parse_readme(None, author_id)
    else:
        # 2. 回退到 README 解析
        for name in ['README.txt', 'readme.txt', 'README.md', 'readme.md']:
            p = author_dir / name
            if p.exists():
                readme_path = p
                break
        author_meta = parse_readme(readme_path, author_id)
    
    authors_set[author_id] = author_meta['name']

    for model_dir in author_dir.iterdir():
        if not model_dir.is_dir(): continue
        if model_dir.name.lower().startswith('readme'): continue
        
        preview_img, tags, files = "", [], []
        
        # 查找预览图
        for f in model_dir.iterdir():
            if f.name.lower().startswith('preview') and f.suffix.lower() in ['.jpg', '.png', '.jpeg', '.webp']:
                # 生成缩略图
                final_thumb = generate_thumbnail(f)
                # 转换为 POSIX 路径 (Web URL)
                preview_img = final_thumb.as_posix()
                break
        
        # 查找标签
        tag_file = model_dir / 'tags.md'
        if tag_file.exists():
                try:
                    with open(tag_file, 'r', encoding='utf-8') as tf:
                        tags = [t.strip() for t in tf.read().replace('\n', ',').split(',') if t.strip()]
                except: pass
        
        # 查找文件
        for f in model_dir.iterdir():
            if not f.suffix.lower() in ['.html', '.py', '.txt', '.md', '.json', '.webp'] and not f.name.startswith('.') and not f.name.startswith('preview'):
                files.append({"name": f.name, "path": f.as_posix()})
        
        models_data.append({
            "author_id": author_id,
            "author_name": author_meta['name'],
            "socials": author_meta['socials'],
            "name": model_dir.name,
            "preview": preview_img,
            "tags": tags,
            "files": files,
            "mtime": model_dir.stat().st_mtime # 添加修改时间用于排序
        })

# --- 渲染 ---
sorted_authors = [{"id": k, "name": v} for k, v in sorted(authors_set.items())]

if not TEMPLATE_FILE.exists():
    print(f"Error: Template file '{TEMPLATE_FILE}' not found.")
    exit(1)

with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    template_content = f.read()

template = Template(template_content)
final_html = template.render(
    models_json=json.dumps(models_data, ensure_ascii=False),
    authors_json=json.dumps(sorted_authors, ensure_ascii=False)
)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(final_html)

print(f"Build successful. Generated {len(models_data)} models.")
