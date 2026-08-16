# .github/data — 共享数据规范

数据按**语义目录**组织，与脚本解耦（禁止以脚本名建子目录），多脚本共用。

## 目录规范

| 目录 | 用途 | 当前文件 |
| --- | --- | --- |
| `templates/` | 网站 / README 等模板文件 | `website_template.html`、`model_readme.template.json` |
| `author-info/` | 作者信息（作者数据 / 平台映射 / 角色术语） | `authors.json`、`platform_map.json`、`role_terms.json`、`co_creators.json`（按需生成） |
| `model-info/` | 模型信息（作品知识库 / 皮肤词表 / 合并跳过） | `character/*.json`（合并格式：作品元数据 + 角色）、`merge_skips.json`、`skin_tags.json` |
| `schemas/` | 数据契约（JSON Schema） | 8 个 `.schema.json`（新增数据须同步补契约） |

## 数据契约（schemas/）

- 每份共享数据都有对应的 JSON Schema（`schemas/<数据名>.schema.json`），作为结构契约；
  新增/修改数据文件须同步维护契约。
- 用 `python .github/scripts/cli.py check`（内部经 `lib/validate.py`）校验全部数据；
  schema 是数据格式的版本载体——结构变更时更新对应 `.schema.json` 并递增其语义版本。
- `author-info/co_creators.json` 按需生成：无任何 co-creator 记录时文件不存在（读取方默认 `{}`），
  `organize_models --apply` 归档到多作者模型时才写入。

## 约定

- 脚本统一通过 `scripts/lib/paths.py` 的 `data_path(category, *parts)` 读写数据，不得硬编码路径。
  类别名即目录名：`data_path('author-info', 'authors.json')`、`data_path('model-info', 'character', 'BA.json')`
  （= `model-info/character/BA.json`）。
- 新增数据先判断属于哪类语义，再放入对应目录；无法归类时先讨论，不要新建脚本名目录。

## 各数据文件的生成与调用

| 文件 | 写入方 | 读取方 | 说明 |
| --- | --- | --- | --- |
| `author-info/authors.json` | `author_index.py --data`（手动或 workflow Step1） | `organize_models.py`、`generate_model_readmes.py`、`check&fix/format_author_readme.py`、`03_generate_root_readme.py --author`（经 `lib/readme.py`） | 集中作者数据：编号 → 名称数组 / README 路径 / 平台链接 |
| `author-info/co_creators.json` | `organize_models.py`（`--apply` 归档时，幂等） | `generate_model_readmes.py`（`get_co_creators`）、`audit_models.py`（合并作者时迁移键） | 模型 → co-creator 作者列表（含平台信息） |
| `model-info/character/*.json` | `kb_tool.py`（`--roles`/`--add-work` 交互维护，纯手工，无 source 键） | `02_model_rename.py`（经 lib/kb `load_kb_json`）、`generate_model_readmes.py`（Game 标签 + Category 现算）、`audit_models.py`（无分类报告） | **合并格式**：作品键 = `work.abbr`（缩写）；`work.name` = 标准名（zh/en/ja 各一个）；`work.aliases` = 别名（分语言数组）；`work.category` = 大类（字符串=单分类 / 数组=多分类）；`roles`（zh/en 数组，首项为规范名；**无自动构建**）；作品数据权威源，**无独立 works.json** |
| `author-info/role_terms.json` | 手工维护（可按需补充别名） | `lib/terms.py`（`normalize_role`）→ `generate_model_readmes.py` | 角色术语表：.ysm 原始 Role 的异表达 → 标准中英术语 |
| `author-info/platform_map.json` | 手工维护 | `lib/ysm.py`（`map_platforms`）→ `organize_models.py` / `generate_model_readmes.py` | 平台分类映射：**分类（键）→ 平台键列表（值）**，反查归类，未命中归 OtherPlatform |

## authors.json 结构

```json
{
  "version": 1,
  "generated": "2026-08-13T06:40:43+00:00",
  "authors": {
    "0001": {
      "name": ["#02Bunny", "#蓝玫瑰"],
      "readme": "Models/0001/README.md",
      "platforms": { "Bilibili": "https://space.bilibili.com/11814817", "QQ": "584570528" }
    }
  }
}
```

- 键为 4 位作者编号（稳定标识，所有脚本按编号寻址）。
- `name` 为数组：首项为规范名（README 显示、模型 README 作者名用），其余为别名；数组顺序保留源 README 的写法。
- 作者级 Role 已废弃（作者在不同模型里负责功能不一致），角色只记录在模型级 co_creators.json / .ysm 作者块。
- 生成时自动清洗 Markdown 链接污染（如个别 README 把 Name 写成 `[#xx](../0058/README.md)`，只保留链接文本）。
- `generated` 为生成时间戳，仅作信息展示；幂等比较（`--check`）只比 `authors` 本体。

## 模型 README 新格式（`templates/model_readme.template.json`）

由 `_Template/`（作者元信息 + 平台分类）转化的结构化模板驱动，`generate_model_readmes.py` 渲染：

- `# <模型名>` → `## Model Details`（`<details>` 内）
  - `- **Category**: #大类`（从 `model-info/character/*.json` 的 category 现算，支持多分类多标签如 `#Anime #Manga #Novel`；不再有 category_map.json）
  - `  - **Game**: #作品标签`（`model-info/character/*.json`，自动生成；不再读取根 README 模型分类区块）
  - `## Author`：Name（authors.json 全别名 `|` 连接）/ 平台分类段（authors.json platforms 经 platform_map 反查分类，链接子行）
  - `## Co-creator`：同 Author 结构；数据来自 author-info/co_creators.json，无记录时解析 .ysm 兜底；Role 经 `lib/terms.py` 术语表归一（如 `动画`→`#动画 | #Animation`）
- `## Preview Images`（独立 `<details open>`，预览图区块标记保持不变）
