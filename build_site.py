import os
import json
import re

# 配置
ROOT_DIR = 'models'
OUTPUT_FILE = 'index.html'

# 網頁模板
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Model Repository</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background: #f4f6f8; color: #333; height: 100vh; overflow: hidden; }
        .app-container { display: grid; grid-template-columns: 260px 1fr; height: 100vh; }
        .sidebar { background: white; border-right: 1px solid #e1e4e8; overflow-y: auto; display: flex; flex-direction: column; padding: 20px 10px; }
        .sidebar-title { font-size: 1.1em; font-weight: bold; padding: 0 10px 15px; border-bottom: 1px solid #eee; margin-bottom: 10px; }
        .author-list { list-style: none; padding: 0; margin: 0; }
        .author-item { display: block; padding: 10px; border-radius: 6px; cursor: pointer; color: #555; transition: background 0.2s; font-size: 0.95em; }
        .author-item:hover, .author-item.active { background: #f0f2f5; color: #0366d6; }
        .author-item small { color: #999; font-size: 0.85em; margin-left: 5px; }
        .main-content { padding: 30px; overflow-y: auto; position: relative; }
        .search-container { margin-bottom: 25px; max-width: 800px; }
        .search-box { width: 100%; padding: 12px 15px; font-size: 16px; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); outline: none; }
        .search-box:focus { border-color: #007bff; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        .card { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); display: flex; flex-direction: column; }
        .card-img-container { width: 100%; height: 180px; background: #eee; }
        .card-img-container img { width: 100%; height: 100%; object-fit: cover; }
        .card-body { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; }
        .model-name { margin: 0 0 5px; font-size: 1.15em; font-weight: 600; }
        .author-info { font-size: 0.9em; color: #666; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; }
        .author-name { font-weight: 600; color: #444; }
        .social-links { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
        .social-link { text-decoration: none; font-size: 0.75em; padding: 3px 8px; border-radius: 4px; background: #f0f2f5; color: #555; border: 1px solid #e1e4e8; }
        .social-link:hover { background: #e1ecf4; color: #0366d6; }
        .social-link.bilibili { color: #fb7299; background: #fff0f6; border-color: #ffcce0; }
        .tags { margin-bottom: auto; }
        .tag { display: inline-block; background: #e8f0fe; color: #1967d2; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; margin-bottom: 5px; }
        .downloads { margin-top: 15px; padding-top: 10px; border-top: 1px solid #eee; }
        .download-btn { display: block; text-decoration: none; color: #24292e; font-size: 0.9em; padding: 6px 10px; background: #fafbfc; border: 1px solid #d1d5da; border-radius: 6px; text-align: center; margin-top: 5px; }
        .download-btn:hover { background: #f3f4f6; }
        @media (max-width: 768px) { .app-container { grid-template-columns: 1fr; } .sidebar { display: none; } .main-content { padding: 15px; } }
    </style>
</head>
<body>
    <div class="app-container">
        <aside class="sidebar">
            <div class="sidebar-title">作者列表</div>
            <ul class="author-list">
                <li class="author-item" onclick="filterByAuthor('')">全部顯示</li>
                AUTHORS_PLACEHOLDER
            </ul>
        </aside>
        <main class="main-content">
            <div class="search-container">
                <input type="text" id="search" class="search-box" placeholder="搜尋模型、作者或標籤...">
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
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #666; padding: 40px;">沒有找到符合條件的模型</div>';
                return;
            }
            grid.innerHTML = items.map(item => `
                <div class="card">
                    <div class="card-img-container"><img src="${item.preview}" loading="lazy" onerror="this.src='https://via.placeholder.com/300x180?text=No+Preview'"></div>
                    <div class="card-body">
                        <h3 class="model-name">${item.name}</h3>
                        <div class="author-info">
                            作者: <span class="author-name">${item.author_name}</span>
                            <span style="font-family:monospace; color:#999; font-size:0.8em;">#${item.author_id}</span>
                        </div>
                        ${item.socials.length > 0 ? `<div class="social-links">${item.socials.map(s => `<a href="${s.url}" target="_blank" class="social-link ${s.platform}">${s.platform}</a>`).join('')}</div>` : ''}
                        <div class="tags">${item.tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>
                        <div class="downloads">${item.files.map(f => `<a href="${f.path}" class="download-btn" download>📥 ${f.name}</a>`).join('')}</div>
                    </div>
                </div>
            `).join('');
        }

        window.filterByAuthor = function(authorId) {
            searchInput.value = authorId;
            searchInput.dispatchEvent(new Event('input'));
        }

        render(data);

        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            const filtered = data.filter(item => 
                item.name.toLowerCase().includes(term) || 
                item.author_name.toLowerCase().includes(term) ||
                item.author_id.includes(term) ||
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
    if not os.path.exists(file_path): 
        print(f"  [DEBUG] No readme found for {default_id}")
        return info

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # --- 解析作者名稱 (修正版: 支援簡體/繁體/英文) ---
            for line in lines:
                clean_line = line.strip()
                # 正則解釋: 
                # [\*\-]?   -> 允許開頭有 * 或 -
                # \s* -> 允許空格
                # (?: ... ) -> 關鍵字群組
                # 作者[名名稱]* -> 匹配 "作者", "作者名", "作者名称", "作者名稱"
                # Author(?:\s*Name)? -> 匹配 "Author" 或 "Author Name"
                match = re.search(r'[\*\-]?\s*(?:作者[名名称]*|Author(?:\s*Name)?)[:：]\s*(.*)', clean_line, re.IGNORECASE)
                
                if match:
                    extracted_name = match.group(1).strip()
                    # 去除可能殘留的Markdown符號
                    extracted_name = extracted_name.replace('*', '').replace('`', '').strip()
                    if extracted_name:
                        info['name'] = extracted_name
                        print(f"  [DEBUG] Found Name for {default_id}: {extracted_name}")
                        break # 找到名字就停止掃描名稱

            # --- 解析社交連結 ---
            platforms = ['bilibili', 'youtube', 'afdian', 'patreon', 'ko-fi', 'twitter', 'pixiv', 'sketchfab']
            for line in lines:
                clean_line = line.strip()
                found_platform = next((p for p in platforms if p.lower() in clean_line.lower()), None)
                if found_platform:
                    link_match = re.search(r'\[(.*?)\]\((https?://.*?)\)', clean_line) or re.search(r'(https?://[^\s]+)', clean_line)
                    if link_match:
                        url = link_match.group(2) if len(link_match.groups()) > 1 else link_match.group(1)
                        # 去掉括號等髒數據
                        url = url.rstrip(')')
                        info['socials'].append({ "platform": found_platform, "url": url })

    except Exception as e:
        print(f"  [ERROR] Parsing readme for {default_id}: {e}")
        
    return info

models_data = []
authors_set = {}

print("=== START BUILDING SITE ===")
if not os.path.exists(ROOT_DIR):
    print(f"Error: Directory '{ROOT_DIR}' not found.")
    exit(1)

for author_id in os.listdir(ROOT_DIR):
    author_path = os.path.join(ROOT_DIR, author_id)
    if not os.path.isdir(author_path): continue
    
    # 尋找 Readme
    readme_path = None
    for name in ['README.txt', 'readme.txt', 'README.md', 'readme.md']:
        p = os.path.join(author_path, name)
        if os.path.exists(p):
            readme_path = p
            break
            
    # 解析
    author_meta = parse_readme(readme_path, author_id)
    authors_set[author_id] = author_meta['name'] # 記錄 ID -> Name 對應關係

    # 遍歷模型
    for model in os.listdir(author_path):
        model_path = os.path.join(author_path, model)
        if not os.path.isdir(model_path): continue
        if model.lower().startswith('readme'): continue
        
        preview_img = ""
        tags = []
        files = []
        
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

# 生成作者列表 (側邊欄) - 顯示名字而非 ID
authors_html = ""
# 按作者 ID 排序，或改用 sorted(authors_set.items(), key=lambda x: x[1]) 按名字排序
for aid in sorted(authors_set.keys()): 
    aname = authors_set[aid]
    # 如果名字就是 ID，就只顯示 ID，否則顯示 "名字 #ID"
    display_text = aname if aname == aid else f"{aname} <small>#{aid}</small>"
    authors_html += f'<li class="author-item" onclick="filterByAuthor(\'{aname}\')">{display_text}</li>\n'

# 替換模板
final_html = html_template.replace('DATA_PLACEHOLDER', json.dumps(models_data, ensure_ascii=False))
final_html = final_html.replace('AUTHORS_PLACEHOLDER', authors_html)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(final_html)

print(f"Build successful. Total authors: {len(authors_set)}")
