# .github/scripts — 脚本知识库

本目录是仓库自动化与维护工具的集合。脚本按**流程阶段**分类到 3 个子目录，
共享 `.github/scripts/lib/` 公共库与 `.github/data/` 语义化数据（详见下文"数据规范"）。

```
.github/scripts/
├── lib/       公共库（paths / readme / models / previews）
├── ingest/    入库归档
├── naming/    命名与知识库
└── publish/   作者索引 / README 生成 / 翻译 / 网站
```

> 每个脚本顶部都带 sys.path 引导（把 `.github/scripts` 加回 import 路径），
> 因此脚本在任何分类子目录下都能 `from lib import ...` 或跨分类 import（如
> `rename_model_folders.py` → `from kb_tool import ...`）。

## 一、脚本功能分类

### ingest/ — 入库归档

| 脚本 | 职责 | 调用方式 |
| --- | --- | --- |
| **organize_models.py** | `.ysm` 归档：解析作者 → `Models/<编号>/`，未命中 → `Other-YSM-Models/`，新作者自动建目录；多作者/去重/同模型合并/附属文件跟随；`--apply` 后联动 authors → rename → readmes → authors 表 | `python .github/scripts/ingest/organize_models.py <文件/目录> [--apply] [--root]` |
| **organize_previews.py** | 预览图归入 `previews/` 并规范命名，之后重跑模型 README | `[--apply] [--rename] [--root]` |
| **rename_model_files.py** | 按"文件夹名+变体+版本+副本序号"重命名模型文件（去评级后缀） | `[--apply] <路径>` |

### naming/ — 命名与知识库

| 脚本 | 职责 | 调用方式 |
| --- | --- | --- |
| **kb_tool.py** | 命名知识库维护库：从文件夹名构建作品/角色/别名对照，读写 `data/knowledge/`；也是 rename_model_folders 的 import 核心库 | `--build-kb/--add/--alias/--del/--check/--suggest/--merge/--list` |
| **rename_model_folders.py** | 按知识库把模型文件夹重命名为 `<作品>_<中文角色>[-皮肤]_<英文角色>_<评级>`；`from kb_tool import` 复用知识库逻辑 | `[--apply] [--path]` |

### publish/ — 作者索引 / README 生成 / 翻译 / 网站

| 脚本 | 职责 | 调用方式 |
| --- | --- | --- |
| **build_authors_index.py** | 生成集中作者数据 `.github/data/meta/authors.json`（编号→名称数组/平台），供各脚本统一读取 | `python .github/scripts/publish/build_authors_index.py [--check]` |
| **generate_model_readmes.py** | 为三个模型根下每个模型目录生成/重写英文模型 README（作者名读 authors.json，Co-creator 读 models_meta.json） | 无参运行 |
| **build_readme_authors.py** | 重建根 README.md + README-EN.md 的作者表格（作者名读 authors.json） | 无参运行 |
| **format_author_readme.py** | 格式化作者级 README（Author/Co-creator 段规范化、Name 交叉链接、容器层级修复、重复 Author 段合并；Name 索引读 authors.json） | `[--check] <文件/目录/编号>`，无参=全量 |
| **translate_readme.py** | 用 DeepSeek/OpenAI 增量翻译根 README → README-EN（保护作者表格区块） | 无参运行（需 API key） |
| **build_site.py** | 生成静态模型浏览站 `index.html` + 缩略图（依赖 jinja2/Pillow） | 无参运行 |

## 二、公共库 `lib/`（消除脚本间冗余）

| 模块 | 提供 | 替代了原脚本中的重复实现 |
| --- | --- | --- |
| `lib/paths.py` | 仓库根定位、`.github/data` 语义路径 `data_path(category, ...)`、JSON/文本读写、安全相对路径 | 各脚本的 `find_workspace_root`、`load_json`、`read_text_utf8`、`get_safe_relpath` |
| `lib/readme.py` | 作者名提取（避开 Co-creator）、作者名/别名 → 编号索引、别名归一化、平台账号提取、**集中作者数据**（`build_authors_data` / `load_authors_index` / `split_author_names`） | 四处作者名解析 + 作者索引构建 |
| `lib/models.py` | `same_model` 同模型容错匹配、评级后缀 `_LA~_LD` 清理、名称规范化 | organize_models 与 generate_model_readmes 的 `same_model`；rename_model_files / organize_models / kb_tool 的评级清理 |
| `lib/previews.py` | preview 图片识别与收集（根目录 `preview*` + `previews/` 目录） | generate_model_readmes 与 organize_previews 的预览图规则 |

## 三、数据规范（`.github/data/`）

数据按**语义目录**组织，与脚本解耦（禁止按脚本名建子目录）：

| 目录 | 用途 | 文件 | 读写方 |
| --- | --- | --- | --- |
| `templates/` | 网站 / README 模板 | `website_template.html` | build_site.py |
| `knowledge/` | 命名知识库 | `works.json`、`aliases.json`、`roles/*.json` | kb_tool.py（写）、rename_model_folders.py（经 kb_tool 读） |
| `meta/` | 共享元数据 | `authors.json`（build_authors_index 写，5 个脚本读）、`models_meta.json`（organize_models 写 / generate_model_readmes 读）、`platform_map.json`（organize_models 读） | build_authors_index / organize_models / generate_model_readmes / format_author_readme / build_readme_authors |
| `config/` | 配置（分类规则等） | `README.md`（占位） | 规划中 |

**作者数据规范**：`meta/authors.json` 是作者信息的唯一事实来源，结构为
`{version, generated, authors: {编号: {name: [规范名, ...别名], readme, platforms}}}`；
`name` 为数组，首项为规范名；由 `build_authors_index.py` 生成（自动清洗 Name 中的
Markdown 链接污染），其他脚本一律经 `lib.readme.load_authors_index()` 读取
（缺失时回退到各自旧扫描逻辑）。

脚本统一通过 `lib.paths.data_path('meta', 'xxx.json')` 等读写，不得硬编码路径；
存在 `root` 参数（如 `organize_models --root`）时数据路径优先跟随 root（测试/临时仓库场景）。

## 四、调用关系

```
auto-update-models.yml (workflow)
  ├─ Step0(仅 _Model-Inbox 推送时) ingest/organize_models.py --apply --no-*
  │      # 归档 inbox 里的 .ysm，联动交给后续步骤统一跑
  ├─ Step1 publish/build_authors_index.py        # 重建作者数据
  ├─ Step2 publish/generate_model_readmes.py     # 读 authors.json + models_meta.json
  ├─ Step3 publish/build_readme_authors.py       # 读 authors.json
  └─ Step4 publish/translate_readme.py

organize_models.py (--apply 后串联)
  ├─ publish/build_authors_index.py              # 新作者入库
  ├─ naming/rename_model_folders.py ──→ naming/kb_tool.py (import 复用) ──→ lib/*
  ├─ publish/generate_model_readmes.py
  └─ publish/build_readme_authors.py

organize_previews.py (--apply 后) ──→ publish/generate_model_readmes.py
全部脚本 ──→ lib/*（公共库）
```

## 五、遗留待办（不阻塞当前使用）

1. **build_site.py** 已修复模板路径，但未被 workflow 调用，产出 `index.html` 未自动化。
2. `.github/data` 整体尚未纳入 git 跟踪（`git add .github/data` 后提交一次）。
3. workflow 的 Step0 目前用 `--no-rename` 跳过文件夹重命名（重命名需人工确认）；
   若希望 inbox 推送后全自动重命名，可去掉 `--no-rename`，但请先 review
   `rename_model_folders.py --show KB` 的输出。
