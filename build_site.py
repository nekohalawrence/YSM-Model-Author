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
        
        /* 侧边栏样式 */
        .sidebar { background: white; border-right: 1px solid #e1e4e8; overflow-y: auto; display: flex; flex-direction: column; padding: 20px 10px; }
        .sidebar-title { font-size: 1.1em; font-weight: bold; padding: 0 10px 15px; border-bottom: 1px solid #eee; margin-bottom: 10px; }
        .author-list { list-style: none; padding: 0; margin: 0; }
        .author-item { display: block; padding: 10px; border-radius: 6px; cursor: pointer; color: #555; transition: background 0.2s; font-size: 0.95em; }
        .author-item:hover { background: #f0f2f5; color: #0366d6; }
        
        /* 主内容区样式 */
        .main-content { padding: 30px; overflow-y: auto; position: relative; }
        .search-container { margin-bottom: 25px; max-width: 800px; }
        .search-box { width: 100%; padding: 12px 15px; font-size: 16px; border: 1px solid #ddd; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); outline: none; }
        
        /* 卡片网格 */
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        
        .card { background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); display: flex; flex-direction: column; }
        .card-img-container { width: 100%; height: 180px; background: #eee; position: relative; }
        .card-img-container img { width: 100%; height: 100%; object-fit: cover; }
        
        .card-body { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; }
        .model-name { margin: 0 0 5px; font-size: 1.15em; font-weight: 600; }
        
        .author-info { font-size: 0.9em; color: #666; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; }
        .author-name { font-weight: 600; color: #444; }
        
        /* 社交链接区域分类 */
        .social-section { margin-bottom: 8px; }
        .social-label { font-size: 0.75em; color: #999; margin-bottom: 4px; display: block; }
        .social-links { display: flex; flex-wrap: wrap; gap: 6px; }
        .social-link { text-decoration: none; font-size: 0.75em; padding: 3px 8px; border-radius: 4px; background: #f0f2f5; color: #555; border: 1px solid #e1e4e8; display: flex; align-items: center; }
        .social-link:hover { transform: translateY(-1px); }
        
        /* 平台颜色 */
        .bilibili { color: #fb7299; background: #fff0f6; border-color: #ffcce0; }
        .youtube { color: #ff0000; background: #fff0f0; border-color: #ffcccc; }
        .afdian { color: #946ce6; background: #f6f0ff; border-color: #e6ccff; }
        .patreon { color: #f96854; background: #fff0ee; border-color: #ffccbc; }
        .ko-fi { color: #13C3FF; background: #e0f7ff; border-color: #b3e5fc; }
        .sketchfab { color: #1caad9; background: #e6f7fc; border-color: #b3e5fc; }

        .tags { margin-top: auto; margin-bottom: 10px; }
        .tag { display: inline-block; background: #e8f0fe; color: #1967d2; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; margin-bottom: 5px; }
        
        /* 折叠的文件列表 */
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
                <li class="author-item" onclick="filterByAuthor('')">全部显示</li>
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
            
            // 辅助函数：生成链接HTML
            const makeLink = (s) => `<a href="${s.url}" target="_blank" class="social-link ${s.platform}">${s.platform}</a>`;
            
            // 1. 联系方式 (Contact)
            const contacts = socials.filter(s => ['bilibili', 'youtube', 'twitter', 'pixiv'].includes(s.platform));
            if (contacts.length > 0) {
                html += `<div class="social-section"><span class="social-label">联系</span><div class="social-links">${contacts.map(makeLink).join('')}</div></div>`;
            }

            // 2. 赞助 (Sponsor)
            const sponsors = socials.filter(s => ['afdian', 'patreon', 'ko-fi'].includes(s.platform));
            if (sponsors.length > 0) {
                html += `<div class="social-section"><span class="social-label">赞助</span><div class="social-links">${sponsors.map(makeLink).join('')}</div></div>`;
            }

            // 3. 其他 (Other)
            const others = socials.filter(s => ['sketchfab', 'other'].includes(s.platform));
            if (others.length > 0) {
                html += `<div class="social-section"><span class="social-label">其他</span><div class="social-links">${others.map(makeLink).join('')}</div></div>`;
            }

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
                
                # 1. 解析作者名称 (简体/繁体/英文)
                if 'name' not in info or info['name'] == default_id:
                    name_match = re.search(r'[\*\-]?\s*(?:作者名称|作者|Author)[:：]\s*(.*)', clean_line)
                    if name_match:
                        raw_name = name_match.group(1).strip().replace('*', '').replace('`', '').replace('#', '')
                        if raw_name: info['name'] = raw_name

                # 2. 解析社交链接
                # 逻辑：寻找包含平台关键字的行 -> 分割冒号 -> 检查冒号后面是否有链接
                platforms = ['bilibili', 'youtube', 'afdian', 'patreon', 'ko-fi', 'twitter', 'pixiv', 'sketchfab']
                
                # 检查这一行包含哪个平台
                found_platform = next((p for p in platforms if p.lower() in clean_line.lower()), None)
                
                if found_platform:
                    # 按照中文或英文冒号分割
                    parts = re.split(r'[:：]', clean_line, 1)
                    
                    if len(parts) > 1:
                        content_after_colon = parts[1].strip()
                        
                        # 在冒号后面寻找链接
                        # 优先找 Markdown 链接 [name](url)
                        link_match = re.search(r'\[.*?\]\((https?://.*?)\)', content_after_colon)
                        
                        # 如果找不到 Markdown 链接，找纯 URL
                        if not link_match:
                            link_match = re.search(r'(https?://[^\s]+)', content_after_colon)
                            
                        if link_match:
                            # 提取 URL (如果是 markdown 组2，如果是纯 url 组1)
                            url = link_match.group(1)
                            url = url.rstrip(')') # 清理可能残留的括号
                            
                            info['socials'].append({ 
                                "platform": found_platform, 
                                "url": url 
                            })

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        
    return info

models_data = []
authors_set = {}

if not os.path.exists(ROOT_DIR):
    print(f"Error: Directory '{ROOT_DIR}' not found.")
    exit(1)

for author_id in os.listdir(ROOT_DIR):
    author_path = os.path.join(ROOT_DIR, author_id)
    if not os.path.isdir(author_path): continue
    
    # 寻找 Readme
    readme_path = None
    for name in ['README.txt', 'readme.txt', 'README.md', 'readme.md']:
        p = os.path.join(author_path, name)
        if os.path.exists(p):
            readme_path = p
            break
            
    # 解析元数据
    author_meta = parse_readme(readme_path, author_id)
    authors_set[author_id] = author_meta['name']

    # 遍历模型
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
            elif f.lower() == 'tags.txt':
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

# 生成侧边栏作者列表
authors_html = ""
# 按作者名字排序
sorted_authors = sorted(authors_set.items(), key=lambda item: item[1])
for aid, aname in sorted_authors:
    display = aname if aname == aid else f"{aname} <small>#{aid}</small>"
    # 点击时传入名字进行搜索
    authors_html += f'<li class="author-item" onclick="filterByAuthor(\'{aname}\')">{display}</li>\n'

final_html = html_template.replace('DATA_PLACEHOLDER', json.dumps(models_data, ensure_ascii=False))
final_html = final_html.replace('AUTHORS_PLACEHOLDER', authors_html)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(final_html)

print(f"Build successful. Processed {len(models_data)} models.")
