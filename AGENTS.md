# YSM-Model-Author 项目规则

> 本文件为项目常驻指令，Reasonix 每次会话自动加载。
> 编辑后保存即可生效。

## 项目背景

- 按作者收集整理的 YSM 模型库，含 TACZ 枪包、TLM 女仆包。
- 每个作者一个目录：`Models/0000` ~ `Models/0195`（编号 = 作者编号）。
- README 作者索引由脚本生成，不要手改表格区域。

## 仓库结构说明

| 目录 / 文件 | 用途 |
| --- | --- |
| `Models/0000`~`0195` | 按作者编号分类的模型主目录 |
| `_Model-Inbox/` | 新收到、尚未整理归位的模型暂存区 |
| `Skins/` | 皮肤资源 |
| `TACZ-Gun-Packs/` | TACZ 枪包（.zip 等） |
| `TLM-Maid-Packs/` | TLM 女仆包 |
| `Blockbench-Models/` | .bbmodel 源文件 |
| `Other-YSM-Models/` | 其他 YSM 模型 |
| `First-Person-Mods/`、`Armourer's-Workshop/` | 第一人称 / 装甲工作台相关 |
| `.github/scripts/` | 仓库处理脚本（见下方） |
| `.github/test/` | 测试脚本（check_newline / test_multi_author_e2e / verify_real_samples） |
| `README.md` / `README-EN.md` | 中英双语索引，作者列表区由脚本生成 |

`.github/scripts/` 常用脚本（统一经 `cli.py <子命令>` 调用，参数原样转发）：

- `cli.py` — 统一入口（organize / audit / previews / rename-files / rename-folders / authors / readmes / authors-list / category-map / format / translate / site / flow / check）；`flow` 子命令内联原 pipeline.py 的流程编排（PIPELINE_STEPS）
- `models_organize/01_organize_models.py` — 归档 .ysm 到 `Models/<编号>/`（--with-* 联动后续脚本）
- `models_organize/01_organize_previews.py` — 预览图归入 previews/ 并规范命名
- `models_organize/02_rename_model_files&folders.py` — 模型文件夹改名 + 命名知识库维护（`--build-kb/--add/--del/--check/--suggest/--merge/--list`；`--apply` 对未收录角色交互学习收录；`--rename-files` 改模型文件；实现拆在 `lib/kb/`）
- `models_organize/03_generate&update_model_readmes.py` — 生成模型 README
- `models_organize/03_generate&update_author_readme.py` — 格式化作者级 README（新作者 README 生成统一在此；共享逻辑 `lib/author_readme.py`）
- `models_organize/04_generate&update_root_readme.py` — 根 README 展示生成：集中作者数据 `author-info/authors.json` + 根 README 作者表 + 模型分类区块（`--build-category-map`，收纳自 02）
- `models_organize/05_translate_rpo_readme.py` — README 翻译
- `check&fix/check&fix.py` — 库整理（重新分类 / 合并重复作者 / 空壳报告 / 缺失报告）
- `deployments/build_site.py` — 静态站生成
- `lib/validate.py`（`cli.py check`）— 数据契约校验（schemas/）

## 硬性规则

1. **先做合理性分析（最高优先级）**：我的任何需求（包括后续所有需求）都必须先做合理性分析再动手：
   - 先判断需求/当前方案是否合理：有无更优做法、更简单的替代、副作用或潜在问题；
   - 发现需求表述不清、有误、自相矛盾或实现代价不合理时，先说明原因并给出替代方案，经用户确认后再执行；
   - 不因"用户要求"而无条件照做——先分析合理性，再谈实现。
2. **用户立场（编程小白）**：用户是编程小白，需求可能表述不清、有错误或自相矛盾。请勿完全照做：
   - 发现错误或更优的实现方式时，主动指出并简单说明原因；
   - 实现时兼顾代码可维护性，不只为满足当下需求；
   - 涉及较大改动时，先给方案，经用户确认后再动手。
3. **模糊需求必须确认**：用户提示词模糊时，先复述需求 + 自己的理解，经用户确认后再动手，不要直接开做。
4. **脚本写操作先 dry-run**：使用 `.github/scripts/` 下任何会改文件、改名、移动、写回磁盘的脚本，必须先 dry-run 或展示预览结果，用户确认后才真正执行。
5. **代码质量**：生成/修改代码时，函数要有类型标注和 docstring，变量命名表意，注释解释「为什么」而非「是什么」。
6. **语言偏好**：对用户的回复用简体中文；git 提交信息用英文。
7. **git 提交格式**：Conventional Commits 格式（`feat:` / `fix:` / `docs:` / `chore:` 等）。
8. **文件命名**：沿用仓库现有脚本的命名约定（如 previews/ 子目录、作者编号前缀等）；如用户后续调整约定，以最新为准。
9. **测试脚本位置**：新添加的测试脚本统一放在 `.github/test/` 目录下（与 `check_newline.py`、`test_multi_author_e2e.py`、`verify_real_samples.py` 并列），不要在仓库其他位置新建测试目录；新增测试须配套覆盖 `lib/` 公共库与对应脚本的改动。

## 流程提醒

- 涉及批量改名/移动前，先 dry-run 并展示结果给用户确认。
- 大范围改动先小步验证，再铺开。
- 未整理文件（zip/rar 等）默认先进 `_Model-Inbox`，整理归位后再入对应目录。
