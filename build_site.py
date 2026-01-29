import os
import json
import re

# 配置
ROOT_DIR = 'models'
OUTPUT_FILE = 'index.html'

# 网页模板
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Model Repository</title>
    <style>
        body { font-family: -apple-system, "Microsoft YaHei", "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background: #f4f6f8; color: #333; height: 100vh; overflow: hidden; }
        .app-container { display: grid; grid-template-columns: 260px 1fr; height: 100vh; }
        
        /* --- 侧边栏样式 (优化阅读体验) --- */
        .sidebar { background: white; border-right: 1px solid #e1e4e8; overflow-y: auto; display: flex; flex-direction: column; padding: 20px 10px; }
        .sidebar-title { font-size: 1.1em; font-weight: bold; padding: 0 10px 15px; border-bottom: 1px solid #eee; margin-bottom: 10px; }
        .author-list { list-style: none; padding: 0; margin: 0; }
        
        .author-item { 
            display: flex; 
            align-items: center; /* 垂直居中 */
            padding: 8px 12px; 
            border-radius: 6px; 
            cursor: pointer; 
            transition: background 0.2s; 
            margin-bottom: 2px;
            color: #444;
        }
        .author-item:hover { background: #f0f2f5; color: #0366d6; }
        
        /* ID 样式：辅助视觉，灰色，等宽 */
        .author-id-tag {
            font-family: Consolas, monospace;
            font-size: 0.85em;
            color: #999;
            background: #f6f8fa;
            padding: 2px 6px;
            border-radius: 4px;
            margin-right: 10px;
            min-width: 35px; /* 保持对齐 */
            text-align: center;
        }
        
        /* 名字样式：主要视觉，加粗 */
        .author-name-text {
            font-size: 0.95em;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        /* hover 时让 ID 颜色也变深一点 */
        .author-item:hover .author-id-tag {
            background: #e1ecf4;
            color: #0366d6;
        }

        /* --- 主内容区样式 --- */
        .main-content { padding: 30px; overflow-y: auto; position: relative; }
        .search-container { margin-bottom: 25px; max-width: 800px; }
        .search-box { width: 100%; padding: 12px 15px; font-size: 16px; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); outline: none; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        
        .card { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); display: flex; flex-direction: column; }
        .card-img-container { width: 100%; height: 180px; background: #eee; position: relative; }
        .card-img-container img { width: 100%; height: 100%; object-fit: cover; }
        
        .card-body { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; }
        .model-name { margin: 0 0 5px; font-size: 1.15em; font-weight: 600; }
        
        .author-info { font-size: 0.9em; color: #666; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; }
        .author-name { font-weight: 600; color: #444; }
        
        .social-section { margin-bottom: 8px; }
        .social-label { font-size: 0.75em; color: #999; margin-bottom: 4px; display: block; }
        .social-links { display: flex; flex-wrap: wrap; gap: 6px; }
        .social-link { text-decoration: none; font-size: 0.75em; padding: 3px 8px; border-radius: 4px; background: #f0f2f5; color: #555; border: 1px solid #e1e4e8; display: flex; align-items: center; }
        .social-link:hover { transform: translateY(-1px); }
        
        .bilibili { color: #fb7299; background: #fff0f6; border-color: #ffcce0; }
        .youtube { color: #ff0000; background: #fff0f0; border-color: #ffcccc; }
        .afdian { color: #946ce6; background: #f6f0ff; border-color: #e6ccff; }
        .patreon { color: #f96854; background: #fff0ee; border-color: #ffccbc; }
        .ko-fi { color: #13C3FF; background: #e0f7ff; border-color: #b3e5fc; }
        .sketchfab { color: #1caad9; background: #e6f7fc; border-color: #b3e5fc; }

        .tags { margin-top: auto; margin-bottom: 10px; }
        .tag { display: inline-block; background: #e8f0fe; color: #1967d2; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; margin-bottom: 5px; }
        
        details.file-list { margin-top: 10px; border: 1px solid #eee; border-radius: 6px; }
        details.file-list summary { padding: 8px 12px; cursor: pointer; font-size: 0.9em; color: #555; background: #fafbfc; list-style: none; user-select: none; }
        details.file-list summary:hover { background: #f0f2f5; }
        details.file-list summary::after { content: " ▼"; font-size: 0.8em; float: right; }
        details.file-list[open] summary::after { content: " ▲"; }
        .file-items { padding: 8px; border-top: 1px solid #eee; }
        
        .download-btn { display: block; text-decoration: none; color: #24292e; font-size: 0.9em; padding: 6px 8px; margin-bottom: 4px; border-radius: 4px; }
        .download-btn:hover { background: #f6f8fa; color: #0366d6; }

        @media (max-width: 768px) { .app-container { grid-template-columns: 1fr; } .sidebar { display: none; } .main-content { padding: 15px; } }
    </style>
</head>
<body>
    <div class="app-container">
        <aside class="sidebar">
            <div class="sidebar-title">作者列表</div>
            <ul class="author-list">
                <li class="author-item" onclick="filterByAuthor('')">
                    <span class="author-id-tag">ALL</span>
                    <span class="author-name-text">全部显示</span>
                </li>
                AUTHORS_PLACEHOLDER
            </ul>
        </aside>
        <main class="main-content">
            <div class="search-container">
                <input type="text" id="search" class="search-box" placeholder="搜索模型、作者或标签...">
            </div>
            <div id="grid" class="grid"></div>
        </main>
    </div>
    <script>
        const data = DATA_PLACEHOLDER;
        const grid = document.getElementById('grid');
        const searchInput = document.getElementById('search');

        function render(items) {
            if (items.length === 0) {
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #666; padding: 40px;">没有找到符合条件的模型</div>';
                return;
            }
            grid.innerHTML = items.map(item => `
                <div class="card">
                    <div class="card-img-container">
                        <img src="${item.preview}" loading="lazy" onerror="this.src='https://via.placeholder.com/300x180?text=No+Preview'">
                    </div>
                    <div class="card-body">
                        <h3 class="model-name">${item.name}</h3>
                        <div class="author-info">
                            作者: <span class="author-name">${item.author_name}</span>
                        </div>
                        ${renderSocials(item.socials)}
                        <div class="tags">${item.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
                        <details class="file-list">
                            <summary>显示下载文件 (${item.files.length})</summary>
                            <div class="file-items">
                                ${item.files.map(f => `<a href="${f.path}" class="download-btn" download>📥 ${f.name}</a>`).join('')}
                            </div>
                        </details>
                    </div>
                </div>
            `).join('');
        }

        function renderSocials(socials) {
            let html = '';
            const makeLink = (s) => `<a href="${s.url}" target="_blank" class="social-link ${s.platform}">${s.platform}</a>`;
            const contacts = socials.filter(s => ['bilibili', 'youtube', 'twitter', 'pixiv'].includes(s.platform));
            if (contacts.length > 0) html += `<div class="social-section"><span class="social-label">联系</span><div class="social-links">${contacts.map(makeLink).join('')}</div></div>`;
            const sponsors = socials.filter(s => ['afdian', 'patreon', 'ko-fi'].includes(s.platform));
            if (sponsors.length > 0) html += `<div class="social-section"><span class="social-label">赞助</span><div class="social-links">${sponsors.map(makeLink).join('')}</div></div>`;
            const others = socials.filter(s => ['sketchfab', 'other'].includes(s.platform));
            if (others.length > 0) html += `<div class="social-section"><span class="social-label">其他</span><div class="social-links">${others.map(makeLink).join('')}</div></div>`;
            return html;
        }

        window.filterByAuthor = function(name) {
            searchInput.value = name;
            searchInput.dispatchEvent(new Event('input'));
        }

        render(data);

        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            const filtered = data.filter(item => 
                item.name.toLowerCase().includes(term) || 
                item.author_name.toLowerCase().includes(term) ||
                item.tags.some(t => t.toLowerCase().includes(term))
            );
            render(filtered);
        });
    </script>
</body>
</html>
"""

def parse_readme(file_path, default_id):
    info = { "name": default_id, "socials": [] }
    if not os.path.exists(file_path): return info

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
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

if not os.path.exists(ROOT_DIR):
    print(f"Error: Directory '{ROOT_DIR}' not found.")
    exit(1)

for author_id in os.listdir(ROOT_DIR):
    author_path = os.path.join(ROOT_DIR, author_id)
    if not os.path.isdir(author_path): continue
    
    readme_path = None
    for name in ['README.txt', 'readme.txt', 'README.md', 'readme.md']:
        p = os.path.join(author_path, name)
        if os.path.exists(p):
            readme_path = p
            break
            
    author_meta = parse_readme(readme_path, author_id)
    authors_set[author_id] = author_meta['name']

    for model in os.listdir(author_path):
        model_path = os.path.join(author_path, model)
        if not os.path.isdir(model_path): continue
        if model.lower().startswith('readme'): continue
        
        preview_img, tags, files = "", [], []
        for f in os.listdir(model_path):
            file_path = os.path.join(model_path, f)
            if f.lower().startswith('preview') and f.lower().endswith(('.jpg', '.png', '.jpeg', '.webp')):
                preview_img = f"{ROOT_DIR}/{author_id}/{model}/{f}"
            elif f.lower() == 'tags.md':
                try:
                    with open(file_path, 'r', encoding='utf-8') as tf:
                        tags = [t.strip() for t in tf.read().replace('\n', ',').split(',') if t.strip()]
                except: pass
            elif not f.endswith(('.html', '.py', '.txt', '.md', '.json')) and not f.startswith('.'):
                files.append({"name": f, "path": f"{ROOT_DIR}/{author_id}/{model}/{f}"})
        
        models_data.append({
            "author_id": author_id,
            "author_name": author_meta['name'],
            "socials": author_meta['socials'],
            "name": model,
            "preview": preview_img,
            "tags": tags,
            "files": files
        })

# --- 作者列表生成逻辑 ---
authors_html = ""
# 保持按 ID 排序
sorted_authors = sorted(authors_set.items(), key=lambda item: item[0])

for aid, aname in sorted_authors:
    # 左右结构：左边是小badge，右边是名字
    authors_html += f'''
    <li class="author-item" onclick="filterByAuthor('{aname}')">
        <span class="author-id-tag">{aid}</span>
        <span class="author-name-text">{aname}</span>
    </li>
    '''

final_html = html_template.replace('DATA_PLACEHOLDER', json.dumps(models_data, ensure_ascii=False))
final_html = final_html.replace('AUTHORS_PLACEHOLDER', authors_html)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(final_html)

print(f"Build successful.")
