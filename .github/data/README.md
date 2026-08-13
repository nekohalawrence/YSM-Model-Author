# .github/data — 共享数据规范

数据按**语义目录**组织，与脚本解耦（禁止以脚本名建子目录），多脚本共用。

## 目录规范

| 目录 | 用途 | 当前文件 |
| --- | --- | --- |
| `templates/` | 网站 / README 等模板文件 | `website_template.html`、`model_readme.template.json` |
| `knowledge/` | 命名知识库（作品 / 角色 / 别名 / 大类 / 角色术语） | `works.json`、`aliases.json`、`roles/*.json`、`merge_skips.json`、`category_map.json`、`role_terms.json` |
| `meta/` | 各脚本共享的元数据 | `authors.json`、`models_meta.json`（按需生成）、`platform_map.json` |
| `schemas/` | 数据契约（JSON Schema） | 9 个 `.schema.json`（新增数据须同步补契约） |

## 数据契约（schemas/）

- 每份共享数据都有对应的 JSON Schema（`schemas/<数据名>.schema.json`），作为结构契约；
  新增/修改数据文件须同步维护契约。
- 用 `python .github/scripts/cli.py check`（内部经 `lib/validate.py`）校验全部数据；
  schema 是数据格式的版本载体——结构变更时更新对应 `.schema.json` 并递增其语义版本。
- `models_meta.json` 按需生成：无任何 co-creator 记录时文件不存在（读取方默认 `{}`），
  `organize_models --apply` 归档到多作者模型时才写入。

## 约定

- 脚本统一通过 `scripts/lib/paths.py` 的 `data_path(category, *parts)` 读写数据，不得硬编码路径。
- 新增数据先判断属于哪类语义，再放入对应目录；无法归类时先讨论，不要新建脚本名目录。

## 各数据文件的生成与调用

| 文件 | 写入方 | 读取方 | 说明 |
| --- | --- | --- | --- |
| `meta/authors.json` | `build_authors_index.py`（手动或 workflow Step1） | `organize_models.py`、`generate_model_readmes.py`、`format_author_readme.py`、`build_readme_authors.py`（经 `lib/readme.py`） | 集中作者数据：编号 → 名称数组 / README 路径 / Role / 平台链接 |
| `meta/models_meta.json` | `organize_models.py`（`--apply` 归档时，幂等） | `generate_model_readmes.py`（`get_co_creators`） | 模型 → co-creator 作者列表（含平台信息） |
| `knowledge/works.json` | `kb_tool.py --build-kb`（自动从 README.md 同步，README 为作品名称权威源） | `kb_tool.py` → `rename_model_folders.py` | 作品表（en/cn/ja 名称 → 作品键） |
| `knowledge/aliases.json` | `kb_tool.py --alias` / `--suggest`（交互登记）、`--build-kb` 保存 | `kb_tool.py`（`build_indexes` 展开别名）→ `rename_model_folders.py` | 别名/变体表（别称、大小修饰、多英文名 → 规范名） |
| `knowledge/roles/*.json` | `kb_tool.py --build-kb`（按作品分文件） | `kb_tool.py`（`load_kb_json`）→ `rename_model_folders.py` | 角色对照（cn/en 数组，首项为规范名） |
| `knowledge/category_map.json` | 手工维护 | `generate_model_readmes.py`（`get_category_tag`） | 作品缩写 → 大类（Game/Anime/Music/Original/Other），模型 README 的 **Category** 标签 |
| `knowledge/role_terms.json` | 手工维护（可按需补充别名） | `lib/terms.py`（`normalize_role`）→ `generate_model_readmes.py` | 角色术语表：.ysm 原始 Role 的异表达 → 标准中英术语 |
| `meta/platform_map.json` | 手工维护 | `lib/ysm.py`（`map_platforms`）→ `organize_models.py` / `generate_model_readmes.py` | 平台分类映射：**分类（键）→ 平台键列表（值）**，反查归类，未命中归 OtherPlatform |

## authors.json 结构

```json
{
  "version": 1,
  "generated": "2026-08-13T06:40:43+00:00",
  "authors": {
    "0001": {
      "name": ["#02Bunny", "#蓝玫瑰"],
      "readme": "Models/0001/README.md",
      "role": "#模型 #动作 #动画 | #Model #Motion #Animation",
      "platforms": { "Bilibili": "https://space.bilibili.com/11814817", "QQ": "584570528" }
    }
  }
}
```

- 键为 4 位作者编号（稳定标识，所有脚本按编号寻址）。
- `name` 为数组：首项为规范名（README 显示、模型 README 作者名用），其余为别名；数组顺序保留源 README 的写法。
- `role` 为作者 Role 标签（从作者 README 的 `**Role**` 行提取，标准中英格式），可选。
- 生成时自动清洗 Markdown 链接污染（如个别 README 把 Name 写成 `[#xx](../0058/README.md)`，只保留链接文本）。
- `generated` 为生成时间戳，仅作信息展示；幂等比较（`--check`）只比 `authors` 本体。

## 模型 README 新格式（`templates/model_readme.template.json`）

由 `_Template/`（作者元信息 + 平台分类 + Role）转化的结构化模板驱动，`generate_model_readmes.py` 渲染：

- `# <模型名>` → `## Model Details`（`<details>` 内）
  - `- **Category**: #大类`（`knowledge/category_map.json`，Game/Anime/Music/Original/Other）
  - `  - **Game**: #作品标签`（主 README 模型分类区块，缩进为 Category 子项）
  - `## Author`：Name（authors.json 全别名 `|` 连接）/ Role（作者 README 标准格式）/ 平台分类段（authors.json platforms 经 platform_map 反查分类，链接子行）
  - `## Co-creator`：同 Author 结构；数据来自 models_meta.json，无记录时解析 .ysm 兜底；Role 经 `lib/terms.py` 术语表归一（如 `动画`→`#动画 | #Animation`）
- `## Preview Images`（独立 `<details open>`，预览图区块标记保持不变）
