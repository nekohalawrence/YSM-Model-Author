# .github/scripts — 脚本知识库

本目录是仓库自动化与维护工具的集合。所有脚本共享 `.github/scripts/lib/` 公共库与
`.github/data/` 语义化数据（详见下文"数据规范"）。

## 一、脚本功能分类

| 脚本 | 职责 | 调用方式 | 被谁调用 |
| --- | --- | --- | --- |
| **organize_models.py** | `.ysm` 归档：解析作者 → `Models/<编号>/`，未命中 → `Other-YSM-Models/`，新作者自动建目录；多作者/去重/同模型合并/附属文件跟随；`--apply` 后联动 authors → rename → readmes → authors 表 | `python organize_models.py <文件/目录> [--apply] [--root]` | 人工 |
| **build_authors_index.py** | 生成集中作者数据 `.github/data/meta/authors.json`（编号→名称/别名/平台），供各脚本统一读取，避免各自扫描作者 README | `python build_authors_index.py [--check]` | workflow、organize_models（--apply 联动） |
| **generate_model_readmes.py** | 为三个模型根下每个模型目录生成/重写英文模型 README（作者名读 authors.json，Co-creator 读 models_meta.json） | 无参运行 | workflow、organize_models、organize_previews |
| **build_readme_authors.py** | 重建根 README.md + README-EN.md 的作者表格（作者名读 authors.json） | 无参运行 | workflow、organize_models |
| **translate_readme.py** | 用 DeepSeek/OpenAI 增量翻译根 README → README-EN（保护作者表格区块） | 无参运行（需 API key） | workflow |
| **format_author_readme.py** | 格式化作者级 README（Author/Co-creator 段规范化、Name 交叉链接、容器层级修复、重复 Author 段合并；Name 索引读 authors.json） | `[--check] <文件/目录/编号>`，无参=全量 | 人工 |
| **kb_tool.py** | 命名知识库维护库：从文件夹名构建作品/角色/别名对照，读写 `data/knowledge/` | `--build-kb/--add/--alias/--check/--list` 等 | rename_model_folders（import） |
| **rename_model_folders.py** | 按知识库把模型文件夹重命名为 `<作品>_<中文角色>[-皮肤]_<英文角色>_<评级>` | `[--apply] [--path]` | organize_models |
| **organize_previews.py** | 预览图归入 `previews/` 并规范命名，之后重跑模型 README | `[--apply] [--rename] [--root]` | 人工 |
| **rename_model_files.py** | 按"文件夹名+变体+版本+副本序号"重命名模型文件（去评级后缀） | `[--apply] <路径>` | 人工 |
| **build_site.py** | 生成静态模型浏览站 `index.html` + 缩略图（依赖 jinja2/Pillow） | 无参运行 | 人工 |

## 二、公共库 `lib/`（消除脚本间冗余）

| 模块 | 提供 | 替代了原脚本中的重复实现 |
| --- | --- | --- |
| `lib/paths.py` | 仓库根定位、`.github/data` 语义路径 `data_path(category, ...)`、JSON/文本读写、安全相对路径 | 各脚本的 `find_workspace_root`、`load_json`、`read_text_utf8`、`get_safe_relpath` |
| `lib/readme.py` | 作者名提取（避开 Co-creator）、作者名/别名 → 编号索引、别名归一化、平台账号提取、**集中作者数据**（`build_authors_data` / `load_authors_index`） | 四处作者名解析 + 作者索引构建 |
| `lib/models.py` | `same_model` 同模型容错匹配、评级后缀 `_LA~_LD` 清理、名称规范化 | organize_models 与 generate_model_readmes 的 `same_model`；rename_model_files / organize_models / kb_tool 的评级清理 |
| `lib/previews.py` | preview 图片识别与收集（根目录 `preview*` + `previews/` 目录） | generate_model_readmes 与 organize_previews 的预览图规则 |

## 三、数据规范（`.github/data/`）

数据按**语义目录**组织，与脚本解耦（禁止按脚本名建子目录）：

| 目录 | 用途 | 文件 | 读写方 |
| --- | --- | --- | --- |
| `templates/` | 网站 / README 模板 | `website_template.html` | build_site.py |
| `knowledge/` | 命名知识库 | `works.json`、`aliases.json`、`roles/*.json` | kb_tool.py（写）、rename_model_folders.py（经 kb_tool 读） |
| `meta/` | 共享元数据 | `authors.json`（build_authors_index 写，5 个脚本读）、`models_meta.json`（organize_models 写 / generate_model_readmes 读）、`platform_map.json`（organize_models 读） | build_authors_index / organize_models / generate_model_readmes / format_author_readme / build_readme_authors |
| `config/` | 配置（分类规则等） | `README.md`（占位） | 规划中（Inbox 自动分类） |

**作者数据规范**：`meta/authors.json` 是作者信息的唯一事实来源，结构为
`{version, generated, authors: {编号: {name, aliases, readme, platforms}}}`；
由 `build_authors_index.py` 生成，其他脚本一律经 `lib.readme.load_authors_index()`
读取（缺失时回退到各自旧扫描逻辑）。平台字段（Bilibili/Afdian/QQ 等）供
generate_model_readmes 与 organize_models 使用。

脚本统一通过 `lib.paths.data_path('meta', 'xxx.json')` 等读写，不得硬编码路径；
存在 `root` 参数（如 `organize_models --root`）时数据路径优先跟随 root（测试/临时仓库场景）。

## 四、调用关系

```
auto-update-models.yml (workflow)
  ├─ Step1 build_authors_index.py        # 重建作者数据
  ├─ Step2 generate_model_readmes.py     # 读 authors.json + models_meta.json
  ├─ Step3 build_readme_authors.py       # 读 authors.json
  └─ Step4 translate_readme.py

organize_models.py (--apply 后串联)
  ├─ build_authors_index.py              # 新作者入库
  ├─ rename_model_folders.py ──→ kb_tool.py (import 复用) ──→ lib/*
  ├─ generate_model_readmes.py
  └─ build_readme_authors.py

organize_previews.py (--apply 后) ──→ generate_model_readmes.py
全部脚本 ──→ lib/*（公共库）
```

## 五、遗留待办（不阻塞当前使用）

1. **rename_model_folders.py 的知识库合并逻辑**（main 中 L112-155 附近）与
   `kb_tool.py --build-kb` 分支高度重复，尚未合并（涉及多作者/别名合并语义，改动风险高）。
2. **build_site.py** 已修复模板路径，但未被 workflow 调用，产出 `index.html` 未自动化。
3. **Inbox 自动分类**（`_Model-Inbox` → 自动归档）尚未实现，规划中（见 `data/config/README.md`）。
4. `.github/data` 整体尚未纳入 git 跟踪（`git add .github/data` 后提交一次）。
