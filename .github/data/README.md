# .github/data — 共享数据规范

数据按**语义目录**组织，与脚本解耦（禁止以脚本名建子目录），多脚本共用。

## 目录规范

| 目录 | 用途 | 当前文件 |
| --- | --- | --- |
| `templates/` | 网站 / README 等模板文件 | `website_template.html` |
| `knowledge/` | 命名知识库（作品 / 角色 / 别名） | `works.json`、`aliases.json`、`roles/*.json` |
| `meta/` | 各脚本共享的元数据 | `models_meta.json`、`platform_map.json` |
| `config/` | 配置（分类规则等） | `README.md` |

## 约定

- 脚本统一通过 `scripts/lib/paths.py` 的 `data_path(category, *parts)` 读写数据，不得硬编码路径。
- 新增数据先判断属于哪类语义，再放入对应目录；无法归类时先讨论，不要新建脚本名目录。
- 知识库（`knowledge/`）由 `ysm_kb.py` 统一维护；`meta/models_meta.json` 由 `organize_models.py` 写入、`generate_model_readmes.py` 读取。
