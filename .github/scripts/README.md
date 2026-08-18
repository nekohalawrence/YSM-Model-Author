# .github/scripts — 脚本知识库

本目录是仓库自动化与维护工具的集合。脚本按**流程阶段**分类到子目录，
共享 `.github/scripts/lib/` 公共库与 `.github/data/` 语义化数据（详见下文"数据规范"）。

```
.github/scripts/
├── cli.py            统一命令行入口（子命令转发到各脚本；flow 子命令内联流程编排）
├── lib/              公共库（paths / readme / models / previews / validate / author_readme / kb）
├── models_organize/  模型整理流程（01 归档 → 02 重命名 → 03 README → 04 作者索引 → 05 翻译）
├── check&fix/        库内整理维护（原 ingest/audit_models.py）
└── deployments/      部署（静态网站生成）
```

> 人工操作推荐统一走 `python .github/scripts/cli.py <子命令> [参数...]`（子命令见文末
> "统一入口"），不用记脚本路径；`cli.py` 只做薄转发，行为与直接运行脚本一致。
> 每个脚本顶部都带 sys.path 引导（把 `.github/scripts` 加回 import 路径），
> 因此脚本在任何分类子目录下都能 `from lib import ...` 或跨分类 import（如
> `02_rename_model_folders.py` → `from lib.kb import ...`）。

## 一、脚本功能分类

### models_organize/ — 模型整理流程（按步骤编号排序）

| 脚本 | 职责 | 调用方式 |
| --- | --- | --- |
| **01_organize_models.py** | `.ysm` 归档：解析作者 → 登记/合并 `authors.json` → `Models/<编号>/`（新作者补洞编号 + 建目录），未命中作者 → 按作品前缀分类到 `Other-YSM-Models/<作品>/`（未匹配 → `Unknown/`）；命名先合并内部名+文件名再 resolve_name3 格式化；去重/同模型合并/附属文件跟随；co-creator 丢弃；`--apply` 后联动 readmes → authors 表 | `python .github/scripts/models_organize/01_organize_models.py <文件/目录> [--apply] [--root] [--with-gen-readmes] [--with-readme-table]` |
| **organize_previews.py**（check&fix/） | 预览图归入 `previews/` 并规范命名，之后重跑模型 README | `[--apply] [--rename] [<路径>...]` |
| **02_rename_model_folders.py** | 模型文件夹**纯重命名**（原 naming/rename_model_folders.py）：按知识库把模型文件夹重命名为 `<作品>_<中文角色>[-皮肤]_<英文角色>_<评级>`；Unknown / 跨作品同名冲突**只标记跳过**（不收录数据库）；同名冲突自动加 `-数字` 副本序号。知识库维护已分离到 check&fix/kb_tool.py，实现复用于 `lib/kb/` | `[--apply] [--show*]` |
| **02_rename_model_files.py** | 模型文件重命名（自 02 拆出）：`<文件夹名(去评级)>[变体][_v版本][_副本序号]<后缀>`，变体词经 skin_tags.json 标准化表规范化；默认 dry-run | `[--apply] [路径...]` |
| **kb_tool.py**（check&fix/） | 知识库维护（原 02/03 分离）：`--roles` 角色综合菜单 / `--add`/`--del`/`--list`/`--check`/`--merge`/`--set-default`/`--rename`/`--suggest`（操作 × 对象 role/work）；`--rename-work` 重命名作品键；`--authors-data` 重建 authors.json（原 03 --data）；`--sync-authors` 从模型 .ysm 推导作者并入 authors.json | `python .github/scripts/check&fix/kb_tool.py [--roles/--add/--del/--authors-data/--sync-authors]` |
| **03_generate_model_readmes.py** | 为三个模型根下每个模型目录生成/重写英文模型 README（作者名读 authors.json，Co-creator 读 co_creators.json；Category 标签从 character/*.json 现算） | 无参运行 |
| **format_author_readme.py**（check&fix/） | 格式化作者级 README（原 format_author_readme.py，新作者 README 生成也统一在此；共享逻辑在 lib/author_readme.py）。作者推导已移至 kb_tool --sync-authors | `[--check] <文件/目录/编号>`，无参=全量 |
| **03_generate_root_readme.py** | 根 README 展示生成（原 04_author_index.py + 02 的 --build-category-map）：`--author` 重建根 README 作者表；`--build-category-map` 更新根 README 模型分类区块（authors.json 已移至 kb_tool --authors-data） | `python .github/scripts/models_organize/03_generate_root_readme.py [--author|--build-category-map]` |
| **05_translate_readme.py** | 用 DeepSeek/OpenAI 增量翻译根 README → README-EN（保护作者表格区块） | 无参运行（需 API key） |

### check&fix/ — 库内整理维护（原 ingest/audit_models.py）

| 脚本 | 职责 | 调用方式 |
| --- | --- | --- |
| **check&fix.py** | 库整理：重新分类 / 合并重复作者 / 空壳报告 / 缺失报告（无分类 + 无预览图） | `python .github/scripts/cli.py audit [--reclassify|--merge-authors|--report-*] [--apply]` |

### deployments/ — 部署

| 脚本 | 职责 | 调用方式 |
| --- | --- | --- |
| **build_site.py** | 生成静态模型浏览站 `index.html` + 缩略图（依赖 jinja2/Pillow） | 无参运行 |

## 二、公共库 `lib/`（消除脚本间冗余）

| 模块 | 提供 | 替代了原脚本中的重复实现 |
| --- | --- | --- |
| `lib/paths.py` | 仓库根定位、`.github/data` 语义路径 `data_path(category, ...)`、JSON/文本读写、安全相对路径 | 各脚本的 `find_workspace_root`、`load_json`、`read_text_utf8`、`get_safe_relpath` |
| `lib/readme.py` | 作者名提取（避开 Co-creator）、作者名/别名 → 编号索引、别名归一化、平台账号提取、**集中作者数据**（`build_authors_data` / `load_authors_index` / `split_author_names`） | 四处作者名解析 + 作者索引构建 |
| `lib/models.py` | `same_model` 同模型容错匹配、评级后缀 `_LA~_LD` 清理、名称规范化 | organize_models 与 generate_model_readmes 的 `same_model`；rename_model_folders --rename-files / organize_models / lib.kb 的评级清理 |
| `lib/previews.py` | preview 图片识别与收集（根目录 `preview*` + `previews/` 目录） | generate_model_readmes 与 organize_previews 的预览图规则 |lib.kb

## 三、数据规范（`.github/data/`）

数据按**语义目录**组织，与脚本解耦（禁止按脚本名建子目录）：

| 目录 | 用途 | 文件 | 读写方 |
| --- | --- | --- | --- |
| `templates/` | 网站 / README 模板 | `website_template.html`、`model_readme.template.json`（模型 README 结构，由 _Template/ 转化） | build_site.py / generate_model_readmes.py |
| `author-info/` | 作者信息 | `authors.json`（编号→名称/平台）、`platform_map.json`（**分类为键 → 平台键列表为值**，lib/ysm 反查归类）、`role_terms.json`（角色术语）、`co_creators.json`（按需生成） | author_index.py --data（写 authors.json）、organize_models.py（写 co_creators）、lib/readme.py / lib/terms.py / lib/ysm.py（读） |
| `model-info/` | 模型信息 | `character/*.json`（**合并格式**：作品键 = `work.abbr`，`work.name` 标准名（zh/en/ja），`work.aliases` 别名，`work.category` 大类：字符串=单分类 / 数组=多分类；+ 角色 roles，权威源，无独立 works.json）、`merge_skips.json`、`skin_tags.json` | 02_rename_model_folders.py / kb_tool.py（经 lib/kb 写读）、generate_model_readmes.py / audit_models.py（读 character/*.json 现算分类） |
| `schemas/` | 数据契约（JSON Schema） | 8 个 `.schema.json` | lib/validate.py（校验，经 `cli.py check`） |

> `config/` 已删除（曾为空占位目录，无真实配置；将来需要配置层时再建）。

**作者数据规范**：`author-info/authors.json` 是作者信息的唯一事实来源，结构为
`{version, generated, authors: {编号: {name: [规范名, ...别名], readme, platforms}}}`；
`name` 为数组，首项为规范名；作者级 Role 已废弃（角色只在模型级 co_creators.json）；由
`author_index.py --data` 生成（自动清洗 Name 中的 Markdown 链接污染），其他脚本一律经
`lib.readme.load_authors_index()` 读取（缺失时回退到各自旧扫描逻辑）。

脚本统一通过 `lib.paths.data_path('author-info'/'model-info', 'xxx.json')` 等读写，不得硬编码路径；
存在 `root` 参数（如 `organize_models --root`）时数据路径优先跟随 root（测试/临时仓库场景）。

## 四、调用关系

```
cli.py（统一入口，薄转发）
  ├─ organize / previews / rename-files / rename-folders / authors
  ├─ readmes / authors-list / format / translate / site / flow / check
  └─ check ─→ lib/validate.py（数据契约校验）

cli.py flow（流程编排，内联自原 pipeline.py；workflow 与本地共用）
  ├─ inbox   01_organize_models.py(_Model-Inbox --apply)
  │            → kb_tool.py --authors-data → 03_generate_model_readmes.py
  │            → check&fix/format_author_readme.py → 03_generate_root_readme.py --author
  │            → 05_translate_readme.py
  ├─ full    前 4 步（无新模型时的日常刷新）
  └─ rename / authors / readmes / authors-list / translate（单步）

01_organize_models.py（--with-* 显式叠加，默认只归档）
  ├─ --with-gen-readmes   → 03_generate_model_readmes.py
  └─ --with-readme-table  → 03_generate_root_readme.py --author

check&fix/organize_previews.py (--apply 后) ──→ 03_generate_model_readmes.py
全部脚本 ──→ lib/*（公共库）
```

## 五、统一入口（cli.py）

```
python .github/scripts/cli.py --list              # 查看全部子命令
python .github/scripts/cli.py <子命令> [参数...]   # 参数原样转发给目标脚本
```

| 子命令 | 目标脚本 |
| --- | --- |
| `organize` | models_organize/01_organize_models.py |
| `previews` | check&fix/organize_previews.py |
| `rename-files` | models_organize/02_rename_model_files.py（模型文件重命名） |
| `rename-folders` | models_organize/02_rename_model_folders.py（模型文件夹纯重命名） |
| `kb` | check&fix/kb_tool.py（知识库维护 / --authors-data / --sync-authors） |
| `authors` | check&fix/kb_tool.py --authors-data |
| `readmes` / `format` | models_organize/03_generate_*_readme*.py |
| `authors-list` / `category-map` | models_organize/03_generate_root_readme.py |
| `translate` | models_organize/05_translate_readme.py |
| `site` | deployments/build_site.py |
| `audit` | check&fix/model_check&fix.py（库整理） |
| `flow` | 内联（本文件 PIPELINE_STEPS） |
| `check` | lib/validate.py（数据契约校验） |

**库整理工具 `audit`**（`check&fix/model_check&fix.py`，处理已有库的整理，与 organize 的入库职责分离）：

- `cli.py audit`——全量审计报告（只读）：重新分类差异、重复作者候选；
- `cli.py audit --reclassify --apply`——重新分类：扫 Models 现有 .ysm 主作者与目录编号比对，
  归属错误**逐项确认**后移动（含 co_creators 键迁移）；
- `cli.py audit --merge-authors --apply`——合并重复作者：候选判定 = 平台账号相同 /
  规范化名字相等 / **规范化名字子串**（中文≥3字、英文≥4字符门槛），**逐对确认**后合并
  （移动模型、并 Name+平台行、迁移 co_creators、删除被合并目录、重建索引）；
- `cli.py audit --report-empty`——空壳报告（无 .ysm 的模型文件夹 / 无模型作者目录）。

## 六、遗留待办（不阻塞当前使用）

1. **build_site.py** 模板路径已修复，但未被 workflow 调用，产出 `index.html` 未自动化；
   需要时手动 `python .github/scripts/cli.py site`。
2. workflow 的 `cli.py flow inbox` 不含文件夹重命名（重命名需人工 review）；
   需要时手动 `python .github/scripts/cli.py rename-folders`（先看 `--show KB` 输出）。
3. **数据契约校验（`cli.py check`）** 建议纳入 workflow（在发布前跑一次）或定期手动执行，
   防止数据字段漂移；CI 已安装 jsonschema 依赖。

## 七、参数命名规范（Param Naming Convention）

本仓库所有带 CLI 参数的脚本遵循以下约定。**新增/改动参数必须遵守；旧脚本按优先级渐进迁移，不一次性大改。**

### 1. 写盘标志：一律 `--apply`

- 会写盘/移动/删除的脚本，统一用 `--apply` 表示「真正执行」，默认 dry-run 只预览。
- 不用 `--dry-run` 作为执行开关（反义易混）；纯只读脚本不需要 `--apply`。
- ✅ `--apply`　❌ `--dry-run`（作执行开关时）

### 2. 通用参数（跨脚本同名同义）

| 参数 | 含义 |
| --- | --- |
| `--apply` | 真正执行写盘 |
| `--root PATH` | 仓库根目录（数据路径跟随 root） |
| `--kb DIR` | 知识库目录 |
| `--only PATH` | 只处理指定路径 |
| `--verbose` | 详细输出 |

### 3. 动作类：动词-对象（kebab-case）

- 直接动作一律「动词-对象」：`--rename-files`、`--rename-folders`、`--reclassify`、`--dedupe`、`--merge-authors`、`--build-category-map`。
- `--with-*` 仅表示「顺带联动后续步骤」（如 `--with-rename` = 归档后顺带重命名），与直接动作区分。

### 4. 报告 vs 展示

- `--report-*`：生成报告/统计（`--report-empty`、`--report-no-category`）。
- `--show-*`：查看某项结果（`--show-skip`、`--show-fix`）。
- 二者语义不混用。

### 5. 命名形式

- 统一 kebab-case（连字符），不用下划线/驼峰。
- 可选/取值参数用 `--flag VALUE`；必填主输入用位置参数（`inputs`、`paths`）。
- 避免同一名字既是取值参数又是前缀（`--report FILE` 与 `--report-*` 冲突）。
- 交互式维护工具（对象×动作矩阵清晰，如 kb_tool）用子命令「对象 动作」；一次性批处理脚本用 `--flag`。

### 迁移对照（旧 → 新，渐进进行）

| 旧写法 | 新写法 |
| --- | --- |
| `--dry-run`（作执行开关） | 默认 dry-run，`--apply` 才执行 |
| `--rename` / `--with-rename` 作直接动作 | `--rename-files` / `--rename-folders` |
| `--show*` 与 `--report*` 混用 | 按语义分归 `--report-*` / `--show-*` |
| kb_tool 旧 flag（`--add`/`--del`/`--roles` 等） | 子命令 `role\|work\|author <动作>`（已完成） |

