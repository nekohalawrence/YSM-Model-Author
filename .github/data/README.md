# .github/data — 共享数据规范

数据按**语义目录**组织，与脚本解耦（禁止以脚本名建子目录），多脚本共用。

## 目录规范

| 目录 | 用途 | 当前文件 |
| --- | --- | --- |
| `templates/` | 网站 / README 等模板文件 | `website_template.html` |
| `knowledge/` | 命名知识库（作品 / 角色 / 别名） | `works.json`、`aliases.json`、`roles/*.json` |
| `meta/` | 各脚本共享的元数据 | `authors.json`、`models_meta.json`、`platform_map.json` |
| `config/` | 配置（分类规则等） | `README.md` |

## 约定

- 脚本统一通过 `scripts/lib/paths.py` 的 `data_path(category, *parts)` 读写数据，不得硬编码路径。
- 新增数据先判断属于哪类语义，再放入对应目录；无法归类时先讨论，不要新建脚本名目录。

## 各数据文件的生成与调用

| 文件 | 写入方 | 读取方 | 说明 |
| --- | --- | --- | --- |
| `meta/authors.json` | `build_authors_index.py`（手动或 workflow Step1） | `organize_models.py`、`generate_model_readmes.py`、`format_author_readme.py`、`build_readme_authors.py`（经 `lib/readme.py`） | 集中作者数据：编号 → 名称数组 / README 路径 / 平台链接 |
| `meta/models_meta.json` | `organize_models.py`（`--apply` 归档时，幂等） | `generate_model_readmes.py`（`get_co_creators`） | 模型 → co-creator 作者列表（含平台信息） |
| `knowledge/works.json` | `kb_tool.py --build-kb`（自动从 README.md 同步，README 为作品名称权威源） | `kb_tool.py` → `rename_model_folders.py` | 作品表（en/cn/ja 名称 → 作品键） |
| `knowledge/aliases.json` | `kb_tool.py --alias` / `--suggest`（交互登记）、`--build-kb` 保存 | `kb_tool.py`（`build_indexes` 展开别名）→ `rename_model_folders.py` | 别名/变体表（别称、大小修饰、多英文名 → 规范名） |
| `knowledge/roles/*.json` | `kb_tool.py --build-kb`（按作品分文件） | `kb_tool.py`（`load_kb_json`）→ `rename_model_folders.py` | 角色对照（cn/en 数组，首项为规范名） |
| `meta/platform_map.json` | 手工维护 | `organize_models.py`（`map_platforms`） | 平台键 → 模型 README 字段映射 |

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
- 生成时自动清洗 Markdown 链接污染（如个别 README 把 Name 写成 `[#xx](../0058/README.md)`，只保留链接文本）。
- `generated` 为生成时间戳，仅作信息展示；幂等比较（`--check`）只比 `authors` 本体。
